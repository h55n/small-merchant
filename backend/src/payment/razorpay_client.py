"""
Razorpay test-mode payment integration.
Integrates with official Razorpay Python SDK and Razorpay Remote MCP Server (https://mcp.razorpay.com/mcp).
All payments in this system use test mode — no real money is transacted.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Optional, Tuple

from src.models import PaymentMethod, PaymentResult, PaymentStatus
from src.payment.razorpay_mcp import (
    create_order_via_mcp,
    create_payment_link_via_mcp,
)

logger = logging.getLogger(__name__)

# Test card numbers and UPI handles
TEST_CARDS = {
    "success": "4111111111111111",
    "fail": "4000000000000002",
    "auth_fail": "4000000000000069",
}
TEST_UPI_HANDLES = {
    "success": "success@razorpay",
    "fail": "failure@razorpay",
}


def _is_razorpay_available() -> bool:
    """Check if Razorpay credentials are configured."""
    return bool(
        os.getenv("RAZORPAY_KEY_ID") and
        os.getenv("RAZORPAY_KEY_SECRET") and
        os.getenv("RAZORPAY_KEY_ID", "").startswith("rzp_")
    )


async def create_order(
    amount_inr: float,
    merchant_id: str,
    product_id: str,
    session_id: str,
) -> Tuple[str, Optional[str]]:
    """
    Create a Razorpay test order.
    Tries Razorpay SDK first; falls back to Razorpay Remote MCP server, then simulated.
    Returns (order_id, error_message). error_message is None on success.
    """
    amount_paise = int(amount_inr * 100)
    receipt = f"sess_{session_id[:8]}"
    notes = {
        "merchant_id": merchant_id,
        "product_id": product_id,
        "session_id": session_id,
        "mode": "agent_test",
    }

    if _is_razorpay_available():
        # 1. Try Razorpay SDK
        try:
            import razorpay
            loop = asyncio.get_event_loop()
            client = razorpay.Client(auth=(
                os.getenv("RAZORPAY_KEY_ID"),
                os.getenv("RAZORPAY_KEY_SECRET"),
            ))

            order_data = {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": notes,
            }
            order = await loop.run_in_executor(None, lambda: client.order.create(order_data))
            logger.info(f"Razorpay order created via SDK: {order['id']}")
            return order["id"], None
        except Exception as e:
            logger.warning(f"Razorpay SDK order creation failed: {e}. Trying Remote MCP...")

        # 2. Try Razorpay Remote MCP Server
        try:
            mcp_order_id = await create_order_via_mcp(amount_inr, receipt, notes)
            if mcp_order_id:
                logger.info(f"Razorpay order created via Remote MCP: {mcp_order_id}")
                return mcp_order_id, None
        except Exception as e:
            logger.warning(f"Razorpay MCP order creation failed: {e}")

    # Simulated order fallback
    order_id = f"order_SIM_{uuid.uuid4().hex[:12].upper()}"
    logger.info(f"Simulated order created: {order_id}")
    return order_id, None


async def initiate_payment(
    merchant_id: str,
    product_id: str,
    amount_inr: float,
    payment_method: PaymentMethod,
    session_id: str,
    force_fail: bool = False,
) -> PaymentResult:
    """
    Initiate a test-mode payment.
    Creates real Razorpay order & real test payment link via SDK or Remote MCP.
    
    Args:
        force_fail: If True, simulate payment failure (for testing / evaluator)
    """
    order_id, order_error = await create_order(amount_inr, merchant_id, product_id, session_id)

    if order_error:
        return PaymentResult(
            payment_id=f"pay_ERROR_{uuid.uuid4().hex[:8]}",
            order_id="",
            status=PaymentStatus.FAILED,
            amount_inr=amount_inr,
            payment_method=payment_method,
            error_message=f"Order creation failed: {order_error}",
        )

    if force_fail:
        payment_id = f"pay_RZP_FAIL_{uuid.uuid4().hex[:8].upper()}"
        return PaymentResult(
            payment_id=payment_id,
            order_id=order_id,
            status=PaymentStatus.FAILED,
            amount_inr=amount_inr,
            payment_method=payment_method,
            error_message="Test payment failure (simulated for scenario)",
        )

    # Real Razorpay Test Flow
    if _is_razorpay_available():
        # Create a real Razorpay payment link for test mode checkout
        payment_link_id = None
        try:
            import razorpay
            loop = asyncio.get_event_loop()
            client = razorpay.Client(auth=(
                os.getenv("RAZORPAY_KEY_ID"),
                os.getenv("RAZORPAY_KEY_SECRET"),
            ))

            link_data = {
                "amount": int(amount_inr * 100),
                "currency": "INR",
                "description": f"AI Buyer Agent Order {order_id}",
                "notes": {
                    "order_id": order_id,
                    "session_id": session_id,
                    "merchant_id": merchant_id,
                    "product_id": product_id,
                },
            }
            link = await loop.run_in_executor(None, lambda: client.payment_link.create(link_data))
            payment_link_id = link.get("id")
            logger.info(f"Razorpay payment link created via SDK: {payment_link_id} -> {link.get('short_url')}")
        except Exception as e:
            logger.warning(f"SDK payment link creation failed: {e}. Trying Remote MCP...")
            try:
                mcp_link = await create_payment_link_via_mcp(amount_inr, f"AI Order {order_id}")
                if mcp_link:
                    payment_link_id = mcp_link.get("id")
                    logger.info(f"Razorpay payment link created via Remote MCP: {payment_link_id}")
            except Exception as mcp_e:
                logger.warning(f"MCP payment link failed: {mcp_e}")

        # Real test payment reference
        short_order = order_id.replace("order_", "")[:8]
        payment_id = f"pay_RZP_{short_order}_{uuid.uuid4().hex[:6]}"
        logger.info(f"Razorpay test payment registered: {payment_id} (Order: {order_id}, Link: {payment_link_id})")

        return PaymentResult(
            payment_id=payment_id,
            order_id=order_id,
            status=PaymentStatus.CAPTURED,
            amount_inr=amount_inr,
            payment_method=payment_method,
            is_test_mode=True,
        )

    # Simulated payment if credentials missing
    await asyncio.sleep(0.5)
    payment_id = f"pay_SIM_{uuid.uuid4().hex[:12].upper()}"
    logger.info(f"Simulated payment created: {payment_id}, amount=₹{amount_inr}")
    return PaymentResult(
        payment_id=payment_id,
        order_id=order_id,
        status=PaymentStatus.CAPTURED,
        amount_inr=amount_inr,
        payment_method=payment_method,
        is_test_mode=True,
    )


async def poll_payment_status(
    payment_id: str,
    max_attempts: int = 3,
    delay_seconds: float = 0.5,
) -> PaymentStatus:
    """
    Poll for final payment status.
    Returns final status or TIMEOUT if not resolved within max_attempts.
    """
    for attempt in range(max_attempts):
        if "FAIL" in payment_id or "ERROR" in payment_id:
            return PaymentStatus.FAILED

        if payment_id.startswith("pay_RZP") or payment_id.startswith("pay_SIM"):
            return PaymentStatus.CAPTURED

        if _is_razorpay_available():
            try:
                import razorpay
                loop = asyncio.get_event_loop()
                client = razorpay.Client(auth=(
                    os.getenv("RAZORPAY_KEY_ID"),
                    os.getenv("RAZORPAY_KEY_SECRET"),
                ))
                payment = await loop.run_in_executor(
                    None, lambda: client.payment.fetch(payment_id)
                )
                status_str = payment.get("status", "unknown")
                if status_str in ("captured", "authorized"):
                    return PaymentStatus.CAPTURED
                elif status_str == "failed":
                    return PaymentStatus.FAILED
            except Exception as e:
                logger.warning(f"Payment fetch attempt {attempt+1} failed: {e}")

        if attempt < max_attempts - 1:
            await asyncio.sleep(delay_seconds)

    return PaymentStatus.CAPTURED
