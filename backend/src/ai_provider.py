"""
Multi-LLM AI Provider Abstraction Layer.
Cascades through providers in order until one succeeds:
  1. Anthropic Claude
  2. OpenAI GPT-4o
  3. Google Gemini
  4. Groq  (llama / compound — fast inference)
  5. Ollama (local)
  6. Rule-based template fallback (always works)

This ensures the system never fails due to a single AI provider issue.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class ProviderName(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    GROQ = "groq"
    NVIDIA_NIM = "nvidia_nim"
    MISTRAL = "mistral"
    OLLAMA = "ollama"
    TEMPLATE = "template_fallback"


@dataclass
class ProviderResponse:
    content: str
    provider: ProviderName
    model: str
    tokens_used: int = 0
    latency_ms: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema


class AIProvider:
    """
    Unified AI provider that cascades through multiple backends.
    Implements tool-calling for the buyer agent loop.
    """

    def __init__(self):
        self._providers_order = self._build_provider_order()
        self._clients: Dict[str, Any] = {}
        self._provider_cooldowns: Dict[ProviderName, float] = {}
        self._init_clients()

    def _build_provider_order(self) -> List[ProviderName]:
        """Build provider cascade order based on available API keys."""
        order = []
        if os.getenv("ANTHROPIC_API_KEY"):
            order.append(ProviderName.ANTHROPIC)
        openai_k = os.getenv("OPENAI_API_KEY", "")
        if openai_k and not openai_k.startswith("sk-dca"):
            order.append(ProviderName.OPENAI)
        if os.getenv("GEMINI_API_KEY"):
            order.append(ProviderName.GEMINI)
        if os.getenv("GROQ_API_KEY"):
            order.append(ProviderName.GROQ)
        if os.getenv("NVIDIA_NIM_API_KEY") or os.getenv("NIM_API_KEY"):
            order.append(ProviderName.NVIDIA_NIM)
        if os.getenv("MISTRAL_API_KEY"):
            order.append(ProviderName.MISTRAL)
        # Ollama: try if base URL configured or default localhost
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")  # noqa: F841
        order.append(ProviderName.OLLAMA)  # Always try, will skip if unavailable
        order.append(ProviderName.TEMPLATE)  # Always last resort
        logger.info(f"AI provider cascade order: {[p.value for p in order]}")
        return order

    def _init_clients(self):
        """Initialize client objects for each provider."""
        try:
            if os.getenv("ANTHROPIC_API_KEY"):
                import anthropic
                self._clients[ProviderName.ANTHROPIC] = anthropic.Anthropic(
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
        except Exception as e:
            logger.warning(f"Anthropic client init failed: {e}")

        try:
            openai_k = os.getenv("OPENAI_API_KEY", "")
            if openai_k and not openai_k.startswith("sk-dca"):
                from openai import OpenAI
                self._clients[ProviderName.OPENAI] = OpenAI(
                    api_key=openai_k
                )
        except Exception as e:
            logger.warning(f"OpenAI client init failed: {e}")

        try:
            if os.getenv("GEMINI_API_KEY"):
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                self._clients[ProviderName.GEMINI] = genai
        except Exception as e:
            logger.warning(f"Gemini client init failed: {e}")

        try:
            if os.getenv("GROQ_API_KEY"):
                from groq import Groq
                # max_retries=0 so when Groq free tier hits 429, it immediately falls back to NVIDIA NIM
                self._clients[ProviderName.GROQ] = Groq(
                    api_key=os.getenv("GROQ_API_KEY"),
                    max_retries=0,
                )
        except Exception as e:
            logger.warning(f"Groq client init failed: {e}")

        try:
            nim_key = os.getenv("NVIDIA_NIM_API_KEY") or os.getenv("NIM_API_KEY")
            if nim_key:
                from openai import OpenAI
                self._clients[ProviderName.NVIDIA_NIM] = OpenAI(
                    base_url="https://integrate.api.nvidia.com/v1",
                    api_key=nim_key,
                    timeout=40.0,
                    max_retries=1,
                )
        except Exception as e:
            logger.warning(f"NVIDIA NIM client init failed: {e}")

        try:
            if os.getenv("MISTRAL_API_KEY"):
                from openai import OpenAI
                self._clients[ProviderName.MISTRAL] = OpenAI(
                    base_url="https://api.mistral.ai/v1",
                    api_key=os.getenv("MISTRAL_API_KEY"),
                    timeout=20.0,
                    max_retries=1,
                )
        except Exception as e:
            logger.warning(f"Mistral client init failed: {e}")

    def get_available_provider(self) -> ProviderName:
        """Return first available provider name."""
        for provider in self._providers_order:
            if provider == ProviderName.TEMPLATE:
                return provider
            if provider == ProviderName.OLLAMA:
                if self._check_ollama_available():
                    return provider
            elif provider in self._clients:
                return provider
        return ProviderName.TEMPLATE

    def _check_ollama_available(self) -> bool:
        """Quick check if Ollama is running."""
        try:
            url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            resp = httpx.get(f"{url}/api/tags", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def complete(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> ProviderResponse:
        """
        Complete a request, cascading through providers until one succeeds.
        Returns a ProviderResponse with content and metadata.
        """
        last_error = None
        now = time.time()
        for provider in self._providers_order:
            # Skip provider if currently in cooldown (e.g. rate-limited)
            if now < self._provider_cooldowns.get(provider, 0):
                continue

            try:
                start = time.time()
                if provider == ProviderName.ANTHROPIC and ProviderName.ANTHROPIC in self._clients:
                    resp = await self._complete_anthropic(system_prompt, messages, tools, max_tokens)
                elif provider == ProviderName.OPENAI and ProviderName.OPENAI in self._clients:
                    resp = await self._complete_openai(system_prompt, messages, tools, max_tokens)
                elif provider == ProviderName.GEMINI and ProviderName.GEMINI in self._clients:
                    resp = await self._complete_gemini(system_prompt, messages, tools, max_tokens)
                elif provider == ProviderName.GROQ and ProviderName.GROQ in self._clients:
                    resp = await self._complete_groq(system_prompt, messages, tools, max_tokens)
                elif provider == ProviderName.NVIDIA_NIM and ProviderName.NVIDIA_NIM in self._clients:
                    resp = await self._complete_nvidia_nim(system_prompt, messages, tools, max_tokens)
                elif provider == ProviderName.MISTRAL and ProviderName.MISTRAL in self._clients:
                    resp = await self._complete_mistral(system_prompt, messages, tools, max_tokens)
                elif provider == ProviderName.OLLAMA:
                    if not self._check_ollama_available():
                        continue
                    resp = await self._complete_ollama(system_prompt, messages, tools, max_tokens)
                elif provider == ProviderName.TEMPLATE:
                    resp = self._complete_template(system_prompt, messages, tools)
                else:
                    continue

                resp.latency_ms = int((time.time() - start) * 1000)
                logger.info(f"AI response from {provider.value} in {resp.latency_ms}ms")
                return resp

            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate limit" in err_str or "ratelimit" in err_str or "quota" in err_str or "tpd" in err_str
                if is_rate_limit:
                    # Longer cooldown for daily token limit (TPD), shorter for temporary rate limit
                    is_daily_limit = "tpd" in err_str or "tokens per day" in err_str or "daily" in err_str
                    cooldown_secs = 600.0 if is_daily_limit else 60.0
                    self._provider_cooldowns[provider] = time.time() + cooldown_secs
                    logger.warning(f"Provider {provider.value} rate-limited, cooling down for {int(cooldown_secs)}s: {e}")
                elif "timeout" in err_str:
                    self._provider_cooldowns[provider] = time.time() + 30.0
                    logger.warning(f"Provider {provider.value} timed out, cooling down for 30s: {e}")
                else:
                    logger.warning(f"Provider {provider.value} failed: {type(e).__name__}: {e}")
                last_error = e
                continue

        # This should never happen because template fallback always works
        raise RuntimeError(f"All AI providers failed. Last error: {last_error}")

    async def _complete_anthropic(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]],
        max_tokens: int,
    ) -> ProviderResponse:
        import anthropic
        client: anthropic.Anthropic = self._clients[ProviderName.ANTHROPIC]

        kwargs: Dict[str, Any] = {
            "model": "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        # Run sync in thread pool to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.messages.create(**kwargs))

        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "name": block.name,
                    "input": block.input,
                    "id": block.id,
                })

        return ProviderResponse(
            content=content,
            provider=ProviderName.ANTHROPIC,
            model="claude-sonnet-4-6",
            tokens_used=(response.usage.input_tokens + response.usage.output_tokens),
            tool_calls=tool_calls,
        )

    async def _complete_openai(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]],
        max_tokens: int,
    ) -> ProviderResponse:
        from openai import OpenAI
        client: OpenAI = self._clients[ProviderName.OPENAI]

        openai_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs: Dict[str, Any] = {
            "model": "gpt-4o-mini",
            "max_tokens": max_tokens,
            "messages": openai_messages,
            "temperature": 0.3,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(**kwargs))

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "name": tc.function.name,
                    "input": args,
                    "id": tc.id,
                })

        return ProviderResponse(
            content=content,
            provider=ProviderName.OPENAI,
            model="gpt-4o-mini",
            tokens_used=(response.usage.total_tokens if response.usage else 0),
            tool_calls=tool_calls,
        )

    async def _complete_gemini(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]],
        max_tokens: int,
    ) -> ProviderResponse:
        import google.generativeai as genai

        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_prompt,
        )

        # Convert message format
        gemini_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            gemini_messages.append({"role": role, "parts": [msg["content"]]})

        import asyncio
        loop = asyncio.get_event_loop()

        def _call():
            chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
            last = gemini_messages[-1]["parts"][0] if gemini_messages else ""
            return chat.send_message(last, generation_config={"max_output_tokens": max_tokens})

        response = await loop.run_in_executor(None, _call)
        content = response.text if hasattr(response, "text") else ""

        return ProviderResponse(
            content=content,
            provider=ProviderName.GEMINI,
            model="gemini-1.5-flash",
            tool_calls=[],  # Gemini tool-calling simplified for fallback
        )

    @staticmethod
    def _normalize_messages_for_openai(messages: List[Dict]) -> List[Dict]:
        """
        Convert Anthropic-style messages to OpenAI/Groq format.

        Anthropic format (what buyer_agent builds):
          {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "..."}]}
          {"role": "assistant", "content": [{"type": "tool_use", ...}, {"type": "text", ...}]}

        OpenAI/Groq format (what these APIs expect):
          {"role": "tool", "tool_call_id": "x", "content": "..."}          # one per result
          {"role": "assistant", "content": "text", "tool_calls": [...]}     # with tool_calls field
        """
        normalized: List[Dict] = []
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Anthropic tool results: role=user, content=[{type:tool_result, ...}, ...]
            if role == "user" and isinstance(content, list):
                all_tool_results = all(
                    isinstance(item, dict) and item.get("type") == "tool_result"
                    for item in content
                )
                if all_tool_results:
                    # Expand each tool result into its own role:tool message
                    for item in content:
                        normalized.append({
                            "role": "tool",
                            "tool_call_id": item.get("tool_use_id", "unknown"),
                            "content": item.get("content", ""),
                        })
                    continue
                else:
                    # Mixed content — join text parts into a plain string
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            parts.append(str(item.get("content", item.get("text", ""))))
                        else:
                            parts.append(str(item))
                    normalized.append({"role": "user", "content": " ".join(parts)})
                    continue

            # Anthropic assistant content list: role=assistant, content=[{type:tool_use,...},{type:text,...}]
            if role == "assistant" and isinstance(content, list):
                text_parts = []
                tool_calls_out = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_use":
                            tool_calls_out.append({
                                "id": item.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": item.get("name", ""),
                                    "arguments": json.dumps(item.get("input", {})),
                                },
                            })
                out_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": " ".join(text_parts) or None,
                }
                if tool_calls_out:
                    out_msg["tool_calls"] = tool_calls_out
                normalized.append(out_msg)
                continue

            # Plain string content — pass through as-is
            normalized.append(msg)

        return normalized

    async def _complete_groq(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]],
        max_tokens: int,
    ) -> ProviderResponse:
        """
        Groq inference via the official groq Python client.
        Uses qwen/qwen3.8-27b which supports tool calling.
        Normalizes Anthropic-style messages to OpenAI format before sending.
        """
        from groq import Groq
        client: Groq = self._clients[ProviderName.GROQ]

        # Normalize Anthropic-style tool result messages → OpenAI role:tool format
        normalized = self._normalize_messages_for_openai(messages)
        groq_messages = [{"role": "system", "content": system_prompt}] + normalized

        # Groq model to use — qwen3.8-27b supports tool calling (compound does not)
        model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": groq_messages,
            "temperature": 0.3,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(**kwargs))

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "name": tc.function.name,
                    "input": args,
                    "id": tc.id,
                })

        return ProviderResponse(
            content=content,
            provider=ProviderName.GROQ,
            model=model,
            tokens_used=(response.usage.total_tokens if response.usage else 0),
            tool_calls=tool_calls,
        )

    async def _complete_nvidia_nim(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]],
        max_tokens: int,
    ) -> ProviderResponse:
        """
        NVIDIA NIM inference using OpenAI-compatible client.
        Uses meta/llama-3.2-11b-vision-instruct with function calling.
        """
        from openai import OpenAI
        client: OpenAI = self._clients[ProviderName.NVIDIA_NIM]

        normalized = self._normalize_messages_for_openai(messages)
        nim_messages = [{"role": "system", "content": system_prompt}] + normalized
        model = os.getenv("NVIDIA_NIM_MODEL", "meta/llama-3.2-11b-vision-instruct")

        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": nim_messages,
            "temperature": 0.3,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(**kwargs))

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({
                    "name": tc.function.name,
                    "input": args,
                    "id": tc.id,
                })

        return ProviderResponse(
            content=content,
            provider=ProviderName.NVIDIA_NIM,
            model=model,
            tokens_used=(response.usage.total_tokens if response.usage else 0),
            tool_calls=tool_calls,
        )

    async def _complete_mistral(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]],
        max_tokens: int,
    ) -> ProviderResponse:
        """
        Mistral inference via OpenAI-compatible endpoint.
        """
        from openai import OpenAI
        client: OpenAI = self._clients[ProviderName.MISTRAL]

        normalized = self._normalize_messages_for_openai(messages)
        m_messages = [{"role": "system", "content": system_prompt}] + normalized
        model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": m_messages,
            "temperature": 0.3,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(**kwargs))

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({
                    "name": tc.function.name,
                    "input": args,
                    "id": tc.id,
                })

        return ProviderResponse(
            content=content,
            provider=ProviderName.MISTRAL,
            model=model,
            tokens_used=(response.usage.total_tokens if response.usage else 0),
            tool_calls=tool_calls,
        )

    async def _complete_ollama(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]],
        max_tokens: int,
    ) -> ProviderResponse:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.2")

        ollama_messages = [{"role": "system", "content": system_prompt}] + messages

        payload: Dict[str, Any] = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.3},
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content", "")

        # Parse tool calls from content if JSON embedded
        tool_calls = []
        if tools and "```json" in content:
            try:
                json_start = content.index("```json") + 7
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                parsed = json.loads(json_str)
                if isinstance(parsed, dict) and "tool" in parsed:
                    tool_calls.append({
                        "name": parsed["tool"],
                        "input": parsed.get("args", {}),
                        "id": f"ollama_{int(time.time())}",
                    })
                content = content[:content.index("```json")].strip()
            except Exception:
                pass

        return ProviderResponse(
            content=content,
            provider=ProviderName.OLLAMA,
            model=model,
            tool_calls=tool_calls,
        )

    def _complete_template(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolDefinition]],
    ) -> ProviderResponse:
        """
        Rule-based template fallback. Analyzes messages and returns structured responses.
        Always works, even with no internet or API keys.
        Content may be a string or a list (when messages contain tool results).
        """
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                raw_content = msg.get("content", "")
                # content can be a list of tool results or a plain string
                if isinstance(raw_content, list):
                    parts = []
                    for item in raw_content:
                        if isinstance(item, dict):
                            parts.append(str(item.get("content", "")))
                        else:
                            parts.append(str(item))
                    last_user_msg = " ".join(parts).lower()
                else:
                    last_user_msg = str(raw_content).lower()
                break

        content = ""
        tool_calls = []

        # Generate appropriate response based on context
        if tools:
            tool_names = [t.name for t in tools]
            if "search_catalog" in tool_names and ("find" in last_user_msg or "buy" in last_user_msg or "get" in last_user_msg or "want" in last_user_msg or "looking" in last_user_msg):
                # Extract potential query
                query = last_user_msg.replace("i want to", "").replace("find me", "").replace("buy", "").replace("i need", "").strip()
                tool_calls.append({
                    "name": "search_catalog",
                    "input": {"query": query or last_user_msg, "limit": 5},
                    "id": f"template_{int(time.time())}",
                })
                content = f"Let me search the catalog for you."
            elif "initiate_payment" not in tool_names:
                content = "I found some products for you. Which would you like to purchase?"
            else:
                content = "I'll help you with that purchase. Let me check what's available."
        else:
            content = "I understand your request. Let me help you find the right product."

        return ProviderResponse(
            content=content,
            provider=ProviderName.TEMPLATE,
            model="template_fallback",
            tool_calls=tool_calls,
        )


# ── Embedding Provider ─────────────────────────────────────────────────────────

class EmbeddingProvider:
    """
    Multi-provider embedding generation.
    Cascades: OpenAI → Gemini → local sentence-transformers
    """

    def __init__(self):
        self._model = None
        self._provider = None
        self._dim = 384  # default for local
        self._init()

    def _init(self):
        provider_pref = os.getenv("EMBEDDING_PROVIDER", "auto")
        openai_k = os.getenv("OPENAI_API_KEY", "")
        if provider_pref in ("auto", "openai") and openai_k and not openai_k.startswith("sk-dca"):
            try:
                from openai import OpenAI
                self._openai = OpenAI(api_key=openai_k)
                self._provider = "openai"
                self._dim = 1536
                logger.info("Embedding provider: OpenAI text-embedding-3-small")
                return
            except Exception as e:
                logger.warning(f"OpenAI embedding init failed: {e}")

        if provider_pref in ("auto", "gemini") and os.getenv("GEMINI_API_KEY"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                self._gemini = genai
                self._provider = "gemini"
                self._dim = 768
                logger.info("Embedding provider: Google Gemini")
                return
            except Exception as e:
                logger.warning(f"Gemini embedding init failed: {e}")

        # Always fall back to local sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._provider = "local"
            self._dim = 384
            logger.info("Embedding provider: local sentence-transformers (all-MiniLM-L6-v2)")
        except Exception as e:
            logger.error(f"Local embedding model failed: {e}. Using zero vectors.")
            self._provider = "zeros"
            self._dim = 384

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_sync, text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_batch_sync, texts)

    def _embed_sync(self, text: str) -> List[float]:
        return self._embed_batch_sync([text])[0]

    def _embed_batch_sync(self, texts: List[str]) -> List[List[float]]:
        if self._provider == "openai":
            response = self._openai.embeddings.create(
                input=texts, model="text-embedding-3-small"
            )
            return [item.embedding for item in response.data]

        elif self._provider == "gemini":
            results = []
            for text in texts:
                result = self._gemini.embed_content(
                    model="models/embedding-001",
                    content=text,
                    task_type="retrieval_document",
                )
                results.append(result["embedding"])
            return results

        elif self._provider == "local":
            import numpy as np
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            return [e.tolist() for e in embeddings]

        else:
            # Zero vector fallback
            import random
            return [[random.gauss(0, 0.1) for _ in range(self._dim)] for _ in texts]

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def provider_name(self) -> str:
        return self._provider or "unknown"


# Singletons
_ai_provider: Optional[AIProvider] = None
_embedding_provider: Optional[EmbeddingProvider] = None


def get_ai_provider() -> AIProvider:
    global _ai_provider
    if _ai_provider is None:
        _ai_provider = AIProvider()
    return _ai_provider


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = EmbeddingProvider()
    return _embedding_provider
