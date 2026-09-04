"""
Buyer Agent — AI-powered purchase assistant with tool-calling.
Uses multi-LLM cascade (Anthropic → OpenAI → Gemini → Ollama → template).
Enforces all safety rules deterministically — AI cannot bypass permission checks.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.permission_enforcer import check_permissions, check_payment_can_retry
from src.ai_provider import AIProvider, ToolDefinition, get_ai_provider
from src.audit.logger import SessionAuditLogger
from src.catalog.storage import get_catalog, get_product, search_catalog, update_product_stock
from src.database import DBSession
from src.models import (
    AgentPermissions, BuyerSession, MerchantCatalog, NormalizedProduct,
    PaymentMethod, PaymentStatus, SessionOutcome, StepType
)
from src.payment.razorpay_client import initiate_payment, poll_payment_status

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a purchasing agent helping users buy products from small Indian merchants on Razorpay test mode.

Your rules (NON-NEGOTIABLE):
1. ALWAYS call search_catalog before recommending any product.
2. Whenever the user chooses or wants to buy a product, ALWAYS call confirmation_gate with the product's details. NEVER call initiate_payment directly.
3. NEVER exceed the buyer's spending limit — call check_spending_limit before calling confirmation_gate.
4. NEVER retry a payment more than once. After 2 failures, stop completely.
5. Log every significant decision using log_decision.
6. If you find multiple matching products, present them to the user — do NOT guess.
7. Always call check_availability immediately before calling confirmation_gate.

You operate in Razorpay test mode. No real money is transacted.
Be concise and helpful. Present prices in ₹ format."""


def _get_tools() -> List[ToolDefinition]:
    """Return all tools available to the buyer agent."""
    return [
        ToolDefinition(
            name="search_catalog",
            description="Search the merchant's product catalog using natural language. Returns ranked matching products.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query. Be specific — include color, material, price range if mentioned."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (1-10). Default 5.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),
        ToolDefinition(
            name="get_product_details",
            description="Get full details for a specific product including return policy, shipping, and constraints.",
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "The product ID to look up."}
                },
                "required": ["product_id"]
            }
        ),
        ToolDefinition(
            name="check_availability",
            description="Check current stock availability for a product. ALWAYS call this immediately before initiating payment.",
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID to check."}
                },
                "required": ["product_id"]
            }
        ),
        ToolDefinition(
            name="check_spending_limit",
            description="Check if a product price is within the buyer's spending limit. Call before confirmation_gate.",
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID to check."},
                    "price_inr": {"type": "number", "description": "Product price in INR."}
                },
                "required": ["product_id", "price_inr"]
            }
        ),
        ToolDefinition(
            name="confirmation_gate",
            description=(
                "REQUIRED: Present product details to user and get explicit purchase confirmation. "
                "You MUST call this before any payment. Wait for the user's response."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"},
                    "price_inr": {"type": "number"},
                    "merchant_name": {"type": "string"},
                    "return_policy_days": {"type": "integer"},
                    "shipping_info": {"type": "string"}
                },
                "required": ["product_id", "product_name", "price_inr", "merchant_name"]
            }
        ),
        ToolDefinition(
            name="initiate_payment",
            description=(
                "Initiate a Razorpay test-mode payment. "
                "Only call AFTER confirmation_gate returned confirmed=true. "
                "Only call if check_availability and check_spending_limit both passed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "amount_inr": {"type": "number"},
                    "payment_method": {
                        "type": "string",
                        "enum": ["UPI", "card", "netbanking"],
                        "description": "Preferred payment method"
                    }
                },
                "required": ["product_id", "amount_inr", "payment_method"]
            }
        ),
        ToolDefinition(
            name="log_decision",
            description="Log a decision to the audit trail. Call at each significant step.",
            parameters={
                "type": "object",
                "properties": {
                    "step": {"type": "string", "description": "Step name"},
                    "reasoning": {"type": "string", "description": "Why this decision was made"},
                    "action": {"type": "string", "description": "What action was taken"},
                    "confidence": {"type": "number", "description": "Confidence 0-1", "minimum": 0, "maximum": 1}
                },
                "required": ["step", "reasoning", "action"]
            }
        ),
    ]


class BuyerAgent:
    """
    Stateful buyer agent for a single purchase session.
    Manages conversation history, tool execution, and session state.
    """

    def __init__(
        self,
        session: BuyerSession,
        catalog: MerchantCatalog,
        db: AsyncSession,
        audit: SessionAuditLogger,
        payment_mock: Optional[str] = None,
    ):
        self.session = session
        self.catalog = catalog
        self.db = db
        self.audit = audit
        self.payment_mock = payment_mock  # For evaluation: "FAIL_FIRST_ATTEMPT", "FAIL_ALL"
        self._messages: List[Dict[str, Any]] = []
        self._pending_confirmation: Optional[Dict[str, Any]] = None
        self._confirmation_received: bool = False
        self._selected_product: Optional[NormalizedProduct] = None
        self._ai = get_ai_provider()
        self._tools = _get_tools()
        self._step_count = 0

    def _build_initial_message(self, purchase_intent: str) -> str:
        """Build the initial user message with context."""
        return (
            f"I want to: {purchase_intent}\n\n"
            f"Merchant: {self.catalog.merchant_name}\n"
            f"My budget: ₹{self.session.spending_limit_inr:,.0f}"
        )

    async def process_message(self, user_message: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a user message and stream agent events.
        Yields event dicts: {type, content, data}
        
        Event types:
        - thinking: Agent is processing
        - tool_call: Agent called a tool
        - tool_result: Tool returned a result
        - message: Agent text response
        - confirmation_gate: Requires user response
        - session_complete: Session finished
        - error: Something went wrong
        """
        self._messages.append({"role": "user", "content": user_message})
        self._step_count += 1

        # Infinite loop guard
        max_iterations = 15
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Check if session should end
            if self.session.status != SessionOutcome.ACTIVE:
                break

            yield {"type": "thinking", "content": "Processing your request..."}

            try:
                t0 = time.time()
                response = await self._ai.complete(
                    system_prompt=SYSTEM_PROMPT,
                    messages=self._messages,
                    tools=self._tools,
                    max_tokens=1500,
                )
                latency = int((time.time() - t0) * 1000)

                # Track which provider was used
                self.session.ai_provider_used = response.provider.value

            except Exception as e:
                logger.error(f"AI provider error: {e}")
                yield {"type": "error", "content": f"AI provider error: {str(e)}"}
                # Try to give a helpful response even on AI failure
                yield {
                    "type": "message",
                    "content": "I encountered an issue. Could you please rephrase your request or try again?",
                }
                break

            # Add assistant response to history
            assistant_content: List[Any] = []
            if response.content:
                assistant_content.append({"type": "text", "text": response.content})

            # Handle tool calls
            if response.tool_calls:
                for tc in response.tool_calls:
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"tool_{iteration}"),
                        "name": tc["name"],
                        "input": tc["input"],
                    })

                self._messages.append({
                    "role": "assistant",
                    "content": assistant_content if assistant_content else (response.content or ""),
                })

                # Execute each tool call
                tool_results = []
                for tc in response.tool_calls:
                    yield {"type": "tool_call", "data": {"name": tc["name"], "input": tc["input"]}}

                    result, event = await self._execute_tool(tc["name"], tc["input"])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.get("id", f"tool_{iteration}"),
                        "content": json.dumps(result),
                    })

                    yield {"type": "tool_result", "data": {"name": tc["name"], "result": result}}

                    # If this tool generates a special event, yield it
                    if event:
                        yield event

                        # If confirmation gate, pause and wait for user input
                        if event["type"] == "confirmation_gate":
                            self._messages.append({
                                "role": "user",
                                "content": tool_results,
                            })
                            return  # Pause — resume when user confirms/cancels

                        # If session complete, stop
                        if event["type"] == "session_complete":
                            self._messages.append({
                                "role": "user",
                                "content": tool_results,
                            })
                            return

                # Add tool results to conversation
                self._messages.append({
                    "role": "user",
                    "content": tool_results,
                })
                # Continue the loop — AI will process tool results
                continue

            else:
                # No tool calls — just text response
                self._messages.append({
                    "role": "assistant",
                    "content": response.content,
                })
                if response.content:
                    yield {"type": "message", "content": response.content}
                break

        # End of loop without explicit session_complete
        if self.session.status == SessionOutcome.ACTIVE and iteration >= max_iterations:
            yield {
                "type": "message",
                "content": "I've completed processing your request. Is there anything else you'd like to do?",
            }

    async def handle_confirmation(
        self,
        confirmed: bool,
        selected_product_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Handle user's response to the confirmation gate.
        If confirmed, proceeds with payment.
        If declined, ends session gracefully.
        """
        if not self._pending_confirmation:
            yield {"type": "error", "content": "No pending confirmation found."}
            return

        product_id = selected_product_id or self._pending_confirmation.get("product_id")

        await self.audit.log(
            step=StepType.CONFIRMATION_GATE,
            input_data={"product_id": product_id, "confirmed": confirmed},
            output_data={"user_confirmed": confirmed},
            reasoning="User provided explicit purchase confirmation response",
            model_used="user_input",
        )

        if not confirmed:
            # User declined
            self.session.status = SessionOutcome.STOPPED
            self._messages.append({
                "role": "user",
                "content": "I don't want to buy this. Please cancel.",
            })

            await self.audit.log(
                step=StepType.SESSION_COMPLETE,
                output_data={"status": "STOPPED", "reason": "user_cancelled"},
                reasoning="User declined purchase at confirmation gate",
            )

            yield {"type": "message", "content": "Purchase cancelled. Your session has ended."}
            yield {
                "type": "session_complete",
                "data": {
                    "status": "STOPPED",
                    "reason": "user_cancelled",
                    "session_id": self.session.session_id,
                }
            }
            return

        # User confirmed — proceed with payment
        self.session.confirmation_gate_hit = True
        self._confirmation_received = True

        # Get the product
        product = await get_product(self.db, self.catalog.merchant_id, product_id)
        if not product:
            yield {"type": "error", "content": "Product no longer available."}
            return

        # Double-check availability
        yield {"type": "thinking", "content": "Verifying availability and processing payment..."}

        if not product.availability or product.stock_count <= 0:
            await self.audit.log(
                step=StepType.AVAILABILITY_CHECKED,
                input_data={"product_id": product_id},
                output_data={"available": False},
                reasoning="Product went out of stock between confirmation and payment",
            )
            yield {
                "type": "message",
                "content": f"'{product.name}' just went out of stock. Let me search for alternatives.",
            }
            # Search for alternatives
            alternatives = await search_catalog(self.db, self.catalog.merchant_id, product.name, limit=3)
            alts = [r for r in alternatives.results if r.product.product_id != product_id]
            if alts:
                alt_text = "\n".join([f"• {a.product.name} — ₹{a.product.price_inr:,.0f}" for a in alts[:2]])
                yield {"type": "message", "content": f"Here are some alternatives:\n{alt_text}\n\nWhich would you like?"}
            else:
                yield {"type": "message", "content": "No alternatives found. Please try a different search."}
            return

        # Initiate payment
        async for event in self._do_payment(product):
            yield event

    async def _do_payment(self, product: NormalizedProduct) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute payment with retry logic."""
        payment_methods = [PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.NETBANKING]

        for attempt in range(2):
            if self.session.payment_attempts >= 2:
                break

            method = payment_methods[attempt % len(payment_methods)]
            force_fail = (
                self.payment_mock == "FAIL_ALL" or
                (self.payment_mock == "FAIL_FIRST_ATTEMPT" and attempt == 0)
            )

            t0 = time.time()
            self.session.payment_attempts += 1

            await self.audit.log(
                step=StepType.PAYMENT_INITIATED,
                input_data={
                    "product_id": product.product_id,
                    "amount_inr": product.price_inr,
                    "method": method.value,
                    "attempt": attempt + 1,
                },
                reasoning=f"Initiating payment attempt {attempt+1} with {method.value}",
                model_used="razorpay_api",
            )

            try:
                payment_result = await initiate_payment(
                    merchant_id=self.catalog.merchant_id,
                    product_id=product.product_id,
                    amount_inr=product.price_inr,
                    payment_method=method,
                    session_id=self.session.session_id,
                    force_fail=force_fail,
                )

                yield {"type": "thinking", "content": f"Payment processing... (attempt {attempt+1})"}

                # Poll for final status
                final_status = await poll_payment_status(payment_result.payment_id)
                latency = int((time.time() - t0) * 1000)

                await self.audit.log(
                    step=StepType.PAYMENT_STATUS_POLLED,
                    input_data={"payment_id": payment_result.payment_id},
                    output_data={"status": final_status.value, "attempt": attempt + 1},
                    latency_ms=latency,
                    model_used="razorpay_api",
                )

                if final_status == PaymentStatus.CAPTURED:
                    # Success!
                    self.session.status = SessionOutcome.SUCCESS
                    self.session.payment_id = payment_result.payment_id
                    self.session.product_purchased = product.product_id
                    self.session.amount_inr = product.price_inr

                    # Update stock
                    if product.stock_count > 0:
                        await update_product_stock(
                            self.db,
                            self.catalog.merchant_id,
                            product.product_id,
                            product.stock_count - 1,
                        )

                    await self.audit.log(
                        step=StepType.PAYMENT_CONFIRMED,
                        input_data={"payment_id": payment_result.payment_id},
                        output_data={
                            "status": "CAPTURED",
                            "payment_id": payment_result.payment_id,
                            "amount_inr": product.price_inr,
                        },
                        reasoning="Payment successfully captured",
                    )

                    await self.audit.log(
                        step=StepType.SESSION_COMPLETE,
                        output_data={"status": "SUCCESS"},
                    )

                    yield {
                        "type": "session_complete",
                        "data": {
                            "status": "SUCCESS",
                            "payment_id": payment_result.payment_id,
                            "product_name": product.name,
                            "amount_inr": product.price_inr,
                            "payment_method": method.value,
                            "session_id": self.session.session_id,
                        }
                    }
                    return

                elif final_status == PaymentStatus.TIMEOUT:
                    yield {
                        "type": "message",
                        "content": (
                            "⚠️ Payment status is unknown. We couldn't confirm if it succeeded. "
                            "Please check your payment history before trying again."
                        )
                    }
                    self.session.status = SessionOutcome.FAILED
                    self.session.error_message = "Payment status timeout"

                    await self.audit.log(
                        step=StepType.ERROR,
                        output_data={"status": "TIMEOUT", "payment_id": payment_result.payment_id},
                        error="Payment status could not be determined within timeout period",
                    )
                    return

                else:
                    # Payment failed
                    await self.audit.log(
                        step=StepType.PAYMENT_FAILED,
                        input_data={"payment_id": payment_result.payment_id},
                        output_data={"status": "FAILED", "attempt": attempt + 1},
                        error=payment_result.error_message or "Payment declined",
                    )

                    if attempt == 0 and self.payment_mock != "FAIL_ALL":
                        # Offer retry with different method
                        next_method = payment_methods[1] if method != PaymentMethod.CARD else PaymentMethod.UPI
                        yield {
                            "type": "message",
                            "content": (
                                f"Payment via {method.value} failed. "
                                f"Would you like to retry with {next_method.value}?"
                            )
                        }
                        # For evaluation mode, auto-retry; for UI, wait for user
                        if self.payment_mock:
                            # Auto-retry in evaluation mode
                            continue
                        else:
                            # In UI mode, return and let user decide via message
                            return
                    else:
                        # Max attempts reached or all methods failed
                        self.session.status = SessionOutcome.FAILED
                        self.session.error_message = "Both payment attempts failed"

                        await self.audit.log(
                            step=StepType.SESSION_COMPLETE,
                            output_data={"status": "FAILED", "total_attempts": self.session.payment_attempts},
                            error="All payment attempts exhausted",
                        )

                        yield {
                            "type": "message",
                            "content": (
                                f"Both payment attempts have failed. "
                                f"Please complete your purchase directly on {self.catalog.merchant_name}'s website, "
                                f"or contact them for assistance."
                            )
                        }
                        yield {
                            "type": "session_complete",
                            "data": {"status": "FAILED", "session_id": self.session.session_id}
                        }
                        return

            except Exception as e:
                logger.error(f"Payment error: {e}")
                await self.audit.log(
                    step=StepType.ERROR,
                    error=str(e),
                )
                yield {"type": "error", "content": f"Payment system error: {str(e)}"}
                return

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """
        Execute a tool call and return (result, optional_event).
        The optional event is used for confirmation_gate and session_complete.
        """
        t0 = time.time()

        try:
            if tool_name == "search_catalog":
                return await self._tool_search_catalog(tool_input)

            elif tool_name == "get_product_details":
                return await self._tool_get_product_details(tool_input)

            elif tool_name == "check_availability":
                return await self._tool_check_availability(tool_input)

            elif tool_name == "check_spending_limit":
                return await self._tool_check_spending_limit(tool_input)

            elif tool_name == "confirmation_gate":
                return await self._tool_confirmation_gate(tool_input)

            elif tool_name == "initiate_payment":
                return await self._tool_initiate_payment(tool_input)

            elif tool_name == "log_decision":
                return await self._tool_log_decision(tool_input)

            else:
                error_msg = f"Unknown tool: {tool_name}"
                logger.warning(error_msg)
                return {"error": error_msg}, None

        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            await self.audit.log(
                step=StepType.ERROR,
                input_data={"tool": tool_name, "input": tool_input},
                error=str(e),
                latency_ms=int((time.time() - t0) * 1000),
            )
            return {"error": str(e)}, None

    async def _tool_search_catalog(self, inp: Dict) -> Tuple[Any, None]:
        query = inp.get("query", "")
        limit = min(int(inp.get("limit", 5)), 10)

        t0 = time.time()
        budget = self.session.spending_limit_inr
        results = await search_catalog(self.db, self.catalog.merchant_id, query, limit, max_price=budget)
        latency = int((time.time() - t0) * 1000)

        # Sort products so that items within budget come first, then by semantic similarity
        sorted_results = sorted(
            results.results,
            key=lambda r: (1 if r.product.price_inr <= budget else 0, r.similarity_score),
            reverse=True,
        )

        output = {
            "results_count": len(sorted_results),
            "buyer_spending_limit_inr": budget,
            "products": [
                {
                    "product_id": r.product.product_id,
                    "name": r.product.name,
                    "price_inr": r.product.price_inr,
                    "within_budget": r.product.price_inr <= budget,
                    "description": r.product.description[:100] if r.product.description else "",
                    "category": r.product.category,
                    "availability": r.product.availability,
                    "stock_count": r.product.stock_count,
                    "similarity_score": r.similarity_score,
                }
                for r in sorted_results
            ],
            "embedding_used": results.embedding_used,
        }

        await self.audit.log(
            step=StepType.SEARCH_CATALOG,
            input_data={"query": query, "limit": limit},
            output_data={"results_count": len(results.results)},
            reasoning=f"Searched for '{query}' — found {len(results.results)} matches",
            latency_ms=latency,
            model_used="embedding_search" if results.embedding_used else "keyword_search",
        )

        return output, None

    async def _tool_get_product_details(self, inp: Dict) -> Tuple[Any, None]:
        product_id = inp.get("product_id", "")
        product = await get_product(self.db, self.catalog.merchant_id, product_id)

        if not product:
            return {"error": f"Product {product_id} not found."}, None

        return {
            "product_id": product.product_id,
            "name": product.name,
            "description": product.description,
            "price_inr": product.price_inr,
            "availability": product.availability,
            "stock_count": product.stock_count,
            "category": product.category,
            "return_policy_days": product.return_policy_days,
            "shipping": product.shipping_options[0].model_dump() if product.shipping_options else {},
        }, None

    async def _tool_check_availability(self, inp: Dict) -> Tuple[Any, None]:
        product_id = inp.get("product_id", "")
        product = await get_product(self.db, self.catalog.merchant_id, product_id)

        if not product:
            result = {"available": False, "stock_count": 0, "error": "Product not found"}
        else:
            result = {
                "available": product.availability,
                "stock_count": product.stock_count,
                "product_id": product_id,
            }

        await self.audit.log(
            step=StepType.AVAILABILITY_CHECKED,
            input_data={"product_id": product_id},
            output_data=result,
            reasoning=f"Checked availability for {product_id}",
        )

        return result, None

    async def _tool_check_spending_limit(self, inp: Dict) -> Tuple[Any, None]:
        product_id = inp.get("product_id", "")
        price_inr = float(inp.get("price_inr", 0))

        within_limit = price_inr <= self.session.spending_limit_inr
        result = {
            "within_limit": within_limit,
            "price_inr": price_inr,
            "spending_limit_inr": self.session.spending_limit_inr,
            "difference_inr": self.session.spending_limit_inr - price_inr,
        }

        await self.audit.log(
            step=StepType.PERMISSION_CHECKED,
            input_data={"product_id": product_id, "price_inr": price_inr},
            output_data=result,
            reasoning=f"Spending limit check: ₹{price_inr} vs limit ₹{self.session.spending_limit_inr}",
            model_used="deterministic",
        )

        return result, None

    async def _tool_confirmation_gate(self, inp: Dict) -> Tuple[Any, Optional[Dict]]:
        """
        Records pending confirmation and returns an event to pause the agent.
        The agent resumes only when the user explicitly confirms or cancels.
        """
        product_id = inp.get("product_id", "")
        product_name = inp.get("product_name", "")
        price_inr = float(inp.get("price_inr", 0))
        merchant_name = inp.get("merchant_name", self.catalog.merchant_name)
        return_days = inp.get("return_policy_days", 0)
        shipping_info = inp.get("shipping_info", "Standard shipping")

        # Get full product to verify permission
        product = await get_product(self.db, self.catalog.merchant_id, product_id)
        if not product:
            return {"error": "Product not found"}, None

        # Permission check (deterministic — cannot be bypassed)
        permission = check_permissions(product, self.session, self.catalog.agent_permissions)
        if not permission.allowed:
            await self.audit.log(
                step=StepType.PERMISSION_CHECKED,
                input_data={"product_id": product_id},
                output_data={"allowed": False, "reason": permission.reason.value if permission.reason else None},
                reasoning=permission.message,
                model_used="deterministic",
            )
            return {
                "allowed": False,
                "reason": permission.reason.value if permission.reason else "UNKNOWN",
                "message": permission.message,
            }, {
                "type": "message",
                "content": f"⚠️ {permission.message}",
            }

        # Store pending confirmation
        self._pending_confirmation = {
            "product_id": product_id,
            "product_name": product_name,
            "price_inr": price_inr,
            "merchant_name": merchant_name,
        }
        self._selected_product = product

        gate_data = {
            "product_id": product_id,
            "product_name": product_name,
            "price_inr": price_inr,
            "merchant_name": merchant_name,
            "return_policy_days": return_days,
            "shipping_info": shipping_info,
            "requires_response": True,
        }

        await self.audit.log(
            step=StepType.CONFIRMATION_GATE,
            input_data=gate_data,
            output_data={"requires_user_input": True},
            reasoning="Presenting product to user for explicit purchase confirmation",
            model_used="deterministic",
        )

        return {"confirmation_presented": True, "awaiting_user": True}, {
            "type": "confirmation_gate",
            "data": gate_data,
        }

    async def _tool_initiate_payment(self, inp: Dict) -> Tuple[Any, Optional[Dict]]:
        """
        Hard enforcement: payment cannot be initiated without confirmation.
        """
        if not self._confirmation_received:
            error_msg = "SAFETY VIOLATION: Payment attempted without confirmation gate. Payment blocked. You MUST call confirmation_gate first to present product details to the user."
            logger.error(f"[{self.session.session_id}] {error_msg}")
            await self.audit.log(
                step=StepType.ERROR,
                error=error_msg,
                model_used="deterministic",
            )
            return {
                "error": error_msg,
                "blocked": True,
                "required_action": "Call confirmation_gate with product_id, product_name, price_inr, and merchant_name immediately.",
            }, None

        # This tool returns a placeholder — actual payment handled by handle_confirmation
        return {"message": "Confirmation already received. Payment will proceed."}, None

    async def _tool_log_decision(self, inp: Dict) -> Tuple[Any, None]:
        step_name = inp.get("step", "unknown")
        reasoning = inp.get("reasoning", "")
        action = inp.get("action", "")
        confidence = inp.get("confidence")

        await self.audit.log(
            step=StepType.SESSION_STARTED if "start" in step_name.lower() else StepType.PRODUCT_SELECTED,
            input_data={"step": step_name, "action": action},
            reasoning=reasoning,
            confidence=confidence,
            model_used=self.session.ai_provider_used,
        )

        return {"logged": True, "step": step_name}, None
