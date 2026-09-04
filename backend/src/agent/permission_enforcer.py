"""
Deterministic permission enforcement layer.
This module is safety-critical — AI agents cannot bypass these checks.
All money actions pass through here before execution.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.models import (
    AgentPermissions, BuyerSession, NormalizedProduct,
    PermissionDenialReason, PermissionResult
)

logger = logging.getLogger(__name__)


def check_permissions(
    product: NormalizedProduct,
    session: BuyerSession,
    agent_permissions: AgentPermissions,
) -> PermissionResult:
    """
    Evaluate all permission checks before any payment can be initiated.
    Returns PermissionResult — if allowed=False, payment is blocked.
    
    Checks (in order):
    1. Payment attempt limit (max 2 per session)
    2. Buyer spending limit
    3. Merchant max transaction cap
    4. Product exclusion list
    5. Confirmation requirement (always True)
    """

    # ── Check 1: Payment attempt limit ────────────────────────────────────────
    if session.payment_attempts >= 2:
        msg = (
            f"Maximum payment attempts (2) reached for this session. "
            f"Please start a new session or complete your purchase directly on the merchant's website."
        )
        logger.warning(f"[session={session.session_id}] Payment attempt limit reached: {session.payment_attempts}")
        return PermissionResult(
            allowed=False,
            confirmation_required=False,
            reason=PermissionDenialReason.PAYMENT_ATTEMPTS_EXCEEDED,
            message=msg,
        )

    # ── Check 2: Buyer spending limit ─────────────────────────────────────────
    if product.price_inr > session.spending_limit_inr:
        msg = (
            f"This product costs ₹{product.price_inr:,.0f}, which exceeds your session "
            f"budget of ₹{session.spending_limit_inr:,.0f}. "
            f"You can increase your spending limit or choose a different product."
        )
        logger.info(
            f"[session={session.session_id}] Buyer limit exceeded: "
            f"product=₹{product.price_inr}, limit=₹{session.spending_limit_inr}"
        )
        return PermissionResult(
            allowed=False,
            confirmation_required=False,
            reason=PermissionDenialReason.BUYER_LIMIT_EXCEEDED,
            message=msg,
        )

    # ── Check 3: Merchant max transaction cap ─────────────────────────────────
    if product.price_inr > agent_permissions.max_transaction_inr:
        msg = (
            f"This merchant has set a maximum agent transaction of "
            f"₹{agent_permissions.max_transaction_inr:,.0f}. "
            f"This product (₹{product.price_inr:,.0f}) exceeds that limit. "
            f"Please complete this purchase directly on the merchant's website."
        )
        logger.info(
            f"[session={session.session_id}] Merchant cap exceeded: "
            f"product=₹{product.price_inr}, cap=₹{agent_permissions.max_transaction_inr}"
        )
        return PermissionResult(
            allowed=False,
            confirmation_required=False,
            reason=PermissionDenialReason.MERCHANT_CAP_EXCEEDED,
            message=msg,
        )

    # ── Check 4: Product exclusion list ───────────────────────────────────────
    if product.product_id in agent_permissions.excluded_product_ids:
        msg = (
            f"'{product.name}' is not available for agent purchase by the merchant. "
            f"Please complete this purchase directly on the merchant's website."
        )
        logger.info(f"[session={session.session_id}] Product excluded: {product.product_id}")
        return PermissionResult(
            allowed=False,
            confirmation_required=False,
            reason=PermissionDenialReason.PRODUCT_EXCLUDED,
            message=msg,
        )

    # ── Check 5: Determine if confirmation is required ────────────────────────
    # Confirmation is ALWAYS required. This is a non-negotiable safety gate.
    # We never auto-approve any transaction.
    confirmation_required = True

    logger.info(
        f"[session={session.session_id}] Permission granted: "
        f"product={product.product_id}, price=₹{product.price_inr}, "
        f"confirmation_required={confirmation_required}"
    )

    return PermissionResult(
        allowed=True,
        confirmation_required=confirmation_required,
        reason=None,
        message=None,
    )


def check_confirmation_recorded(
    session: BuyerSession,
    product_id: str,
) -> bool:
    """
    Verify that confirmation gate has been recorded for this session.
    This is called by initiate_payment to enforce the gate.
    """
    return session.confirmation_gate_hit


def check_payment_can_retry(session: BuyerSession) -> bool:
    """Check if another payment attempt is allowed."""
    return session.payment_attempts < 2
