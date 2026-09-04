"""
Razorpay Remote MCP Server Client (https://mcp.razorpay.com/mcp)
Connects directly to Razorpay's official hosted Remote MCP Server using HTTP Basic Auth.
Supports listing tools, calling tools (create_order, create_payment_link, etc.),
and checking MCP server health.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

MCP_ENDPOINT = "https://mcp.razorpay.com/mcp"


def _get_auth_headers() -> Dict[str, str]:
    """Generate Basic Auth header for Razorpay Remote MCP server."""
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


async def check_mcp_health() -> Dict[str, Any]:
    """Send MCP initialize handshake to verify credentials & connection."""
    headers = _get_auth_headers()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "small-merchant-ai-agent", "version": "1.0.0"},
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(MCP_ENDPOINT, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                server_info = data.get("result", {}).get("serverInfo", {})
                return {
                    "connected": True,
                    "server_name": server_info.get("name", "razorpay-mcp-server"),
                    "protocol_version": data.get("result", {}).get("protocolVersion"),
                    "endpoint": MCP_ENDPOINT,
                }
            return {
                "connected": False,
                "status_code": resp.status_code,
                "error": resp.text[:200],
            }
    except Exception as e:
        logger.error(f"MCP health check failed: {e}")
        return {"connected": False, "error": str(e)}


async def list_mcp_tools() -> List[Dict[str, Any]]:
    """Fetch all available tools from the Razorpay Remote MCP Server."""
    headers = _get_auth_headers()
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(MCP_ENDPOINT, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", {}).get("tools", [])
    except Exception as e:
        logger.error(f"Error fetching MCP tools: {e}")
    return []


async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool on Razorpay Remote MCP server."""
    headers = _get_auth_headers()
    payload = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(MCP_ENDPOINT, headers=headers, json=payload)
            if resp.status_code == 200:
                res_data = resp.json()
                result = res_data.get("result", {})
                content = result.get("content", [])
                if content and content[0].get("type") == "text":
                    try:
                        parsed = json.loads(content[0]["text"])
                        return {"success": True, "data": parsed, "raw": content[0]["text"]}
                    except json.JSONDecodeError:
                        return {"success": True, "text": content[0]["text"]}
                return {"success": True, "result": result}
            return {
                "success": False,
                "status_code": resp.status_code,
                "error": resp.text[:300],
            }
    except Exception as e:
        logger.error(f"Error calling MCP tool {tool_name}: {e}")
        return {"success": False, "error": str(e)}


async def create_order_via_mcp(amount_inr: float, receipt: str, notes: Dict[str, str]) -> Optional[str]:
    """Helper to create a Razorpay order via Remote MCP Server."""
    res = await call_mcp_tool("create_order", {
        "amount": int(amount_inr * 100),
        "currency": "INR",
        "receipt": receipt[:40],
        "notes": notes,
    })
    if res.get("success") and "data" in res:
        return res["data"].get("id")
    return None


async def create_payment_link_via_mcp(amount_inr: float, description: str) -> Optional[Dict[str, Any]]:
    """Helper to create a payment link via Remote MCP Server."""
    res = await call_mcp_tool("create_payment_link", {
        "amount": int(amount_inr * 100),
        "currency": "INR",
        "description": description[:200],
    })
    if res.get("success") and "data" in res:
        return {
            "id": res["data"].get("id"),
            "short_url": res["data"].get("short_url"),
            "status": res["data"].get("status"),
        }
    return None
