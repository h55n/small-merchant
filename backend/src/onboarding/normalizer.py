"""
Catalog normalizer and validator.
Converts raw parsed data into validated NormalizedProduct instances.
Uses optional LLM for category inference when category is missing/ambiguous.
"""
from __future__ import annotations

import logging
import math
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from src.models import (
    NormalizationResult, NormalizedProduct, PaymentConstraints,
    ShippingOption, ValidationError, ValidationWarning
)

logger = logging.getLogger(__name__)

KNOWN_CATEGORIES = [
    "Food & Beverage", "Clothing", "Electronics", "Services",
    "Health & Beauty", "Home & Living", "Books & Media",
    "Accessories", "Sports & Fitness", "Education", "Other"
]

AMBIGUOUS_CATEGORIES = {"misc", "miscellaneous", "na", "n/a", "none", "general", "all", ""}


def _clean_price(raw_price: Any) -> Optional[float]:
    """Parse price from various formats: '750', 'Rs.750', '1,299.50', 750, etc."""
    if raw_price is None or isinstance(raw_price, bool):
        return None
    if isinstance(raw_price, (int, float)):
        value = float(raw_price)
        return value if math.isfinite(value) and value != 0 else None
    price_str = str(raw_price).strip()
    # Step 1: Remove currency symbols and surrounding whitespace
    price_str = re.sub(r"(?i)(₹|rs\.?|inr)\s*", "", price_str).strip()
    # Step 2: Remove thousands-separator commas (comma followed by exactly 3 digits)
    price_str = re.sub(r",(?=\d{3}(?:[,.]|$))", "", price_str)
    # Step 3: Remove any remaining non-numeric chars except decimal point and minus
    price_str = re.sub(r"[^\d.\-]", "", price_str)
    try:
        val = float(price_str)
        return val if math.isfinite(val) and val != 0 else None
    except ValueError:
        return None

def _clean_stock(raw_stock: Any) -> int:
    """Parse stock count from various formats."""
    if raw_stock is None:
        return 0
    if isinstance(raw_stock, (int, float)):
        return max(0, int(raw_stock)) if math.isfinite(raw_stock) else 0
    s = str(raw_stock).strip().lower()
    if s in ("yes", "true", "available", "in stock", "in-stock", "instock"):
        return 1
    if s in ("no", "false", "unavailable", "out of stock", "out-of-stock"):
        return 0
    try:
        return max(0, int(float(s)))
    except (ValueError, OverflowError):
        return 0


def _clean_category(raw_cat: Any) -> Optional[str]:
    """
    Clean category string. Returns None if ambiguous (triggers LLM inference).
    """
    if not raw_cat:
        return None
    cat = str(raw_cat).strip()
    if cat.lower() in AMBIGUOUS_CATEGORIES:
        return None
    # Check if it matches known categories
    for known in KNOWN_CATEGORIES:
        if cat.lower() == known.lower():
            return known
    # Return as-is if non-empty and not ambiguous
    return cat[:100]


async def _infer_category_with_llm(name: str, description: str) -> str:
    """Use AI provider to infer product category."""
    try:
        from src.ai_provider import get_ai_provider
        ai = get_ai_provider()
        response = await ai.complete(
            system_prompt="You are a product categorization assistant. Respond with ONLY the category name, nothing else.",
            messages=[{
                "role": "user",
                "content": (
                    f"Classify this product into exactly one of these categories: "
                    f"{', '.join(KNOWN_CATEGORIES)}\n\n"
                    f"Product: {name}\nDescription: {description or 'No description'}\n\n"
                    f"Reply with only the category name."
                )
            }],
            max_tokens=20,
        )
        inferred = response.content.strip().strip('"').strip("'")
        # Validate against known categories
        for known in KNOWN_CATEGORIES:
            if inferred.lower() == known.lower():
                return known
        return "Other"
    except Exception as e:
        logger.warning(f"Category inference failed: {e}")
        return "Other"


def _generate_product_id() -> str:
    return f"prod_{uuid.uuid4().hex[:8]}"


def _validate_product(
    raw: Dict[str, Any],
    idx: int,
    seen_ids: set,
) -> Tuple[Optional[NormalizedProduct], List[ValidationError], List[ValidationWarning]]:
    """
    Validate and normalize a single raw product dict.
    Returns (product_or_None, errors, warnings).
    """
    errors: List[ValidationError] = []
    warnings: List[ValidationWarning] = []
    product_id_raw = raw.get("product_id")

    def err(code: str, field: str, message: str):
        errors.append(ValidationError(
            product_index=idx,
            product_id=str(product_id_raw) if product_id_raw else None,
            code=code, field=field, message=message
        ))

    def warn(code: str, message: str):
        warnings.append(ValidationWarning(
            product_index=idx,
            product_id=str(product_id_raw) if product_id_raw else None,
            code=code, message=message
        ))

    # ── Name validation ──────────────────────────────────────────────────────
    name_raw = raw.get("name")
    if not name_raw or str(name_raw).strip() == "":
        err("MISSING_REQUIRED_FIELD", "name", f"Row {idx+1}: Product name is required.")
        return None, errors, warnings

    name = str(name_raw).strip()[:200]
    if len(name) < 2:
        err("NAME_TOO_SHORT", "name", f"Row {idx+1}: Name '{name}' is too short (min 2 chars).")
        return None, errors, warnings

    # ── Price validation ──────────────────────────────────────────────────────
    price = _clean_price(raw.get("price"))
    if price is None:
        err("MISSING_REQUIRED_FIELD", "price", f"Row {idx+1} '{name}': Price is required.")
        return None, errors, warnings
    if price <= 0:
        err("INVALID_PRICE", "price", f"Row {idx+1} '{name}': Price must be > 0 (got {price}).")
        return None, errors, warnings
    if price >= 1_000_000:
        err("PRICE_TOO_HIGH", "price", f"Row {idx+1} '{name}': Price ₹{price:,.0f} seems too high. Max ₹9,99,999.")
        return None, errors, warnings
    if price > 100_000:
        warn("PRICE_SUSPICIOUS", f"Row {idx+1} '{name}': Price ₹{price:,.0f} is unusually high — please verify.")

    # ── Product ID ────────────────────────────────────────────────────────────
    if product_id_raw and str(product_id_raw).strip():
        product_id = str(product_id_raw).strip()
        if product_id in seen_ids:
            err("DUPLICATE_PRODUCT_ID", "product_id",
                f"Row {idx+1} '{name}': Duplicate product ID '{product_id}'.")
            return None, errors, warnings
        seen_ids.add(product_id)
    else:
        product_id = _generate_product_id()

    # ── Stock ─────────────────────────────────────────────────────────────────
    stock = _clean_stock(raw.get("stock"))
    availability = stock > 0

    # ── Category ──────────────────────────────────────────────────────────────
    category_raw = _clean_category(raw.get("category"))
    # We'll use "INFER" as sentinel for async inference later
    category = category_raw or "INFER"

    # ── Description ───────────────────────────────────────────────────────────
    description = str(raw.get("description") or "").strip()[:500]
    if not description:
        warn("MISSING_DESCRIPTION", f"Row {idx+1} '{name}': No description — product will have minimal info for AI buyers.")

    # ── Return policy ─────────────────────────────────────────────────────────
    try:
        return_days = max(0, int(raw.get("return_policy_days") or 0))
    except (ValueError, TypeError):
        return_days = 0

    # ── Payment constraints ───────────────────────────────────────────────────
    try:
        min_order = float(raw.get("min_order") or 0)
    except (ValueError, TypeError):
        min_order = 0.0
    try:
        max_order = float(raw.get("max_order") or 100000)
    except (ValueError, TypeError):
        max_order = 100000.0

    product = NormalizedProduct(
        product_id=product_id,
        name=name,
        description=description,
        price_inr=price,
        availability=availability,
        stock_count=stock,
        category=category,  # May be "INFER" — resolved in normalize()
        payment_constraints=PaymentConstraints(
            min_order_inr=min_order,
            max_order_inr=max_order,
        ),
        return_policy_days=return_days,
        shipping_options=[ShippingOption()],
        source_format=str(raw.get("source_format", "unknown")),
    )
    return product, errors, warnings


async def normalize(
    raw_products: List[Dict[str, Any]],
    source_format: str = "unknown",
    infer_categories: bool = True,
) -> NormalizationResult:
    """
    Normalize and validate a list of raw products.
    Optionally uses LLM to infer missing categories.
    Returns NormalizationResult with products, errors, warnings, stats.
    """
    if not raw_products:
        return NormalizationResult(
            success=False,
            errors=[ValidationError(code="EMPTY_INPUT", field="products", message="No products to process.")],
            stats={"total_parsed": 0, "valid": 0, "invalid": 0},
        )

    all_errors: List[ValidationError] = []
    all_warnings: List[ValidationWarning] = []
    valid_products: List[NormalizedProduct] = []
    seen_ids: set = set()

    for idx, raw in enumerate(raw_products):
        raw["source_format"] = source_format
        product, errors, warnings = _validate_product(raw, idx, seen_ids)
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        if product is not None:
            valid_products.append(product)

    # Async category inference for products needing it
    if infer_categories:
        inference_tasks = [
            (i, p) for i, p in enumerate(valid_products) if p.category == "INFER"
        ]
        if inference_tasks:
            import asyncio
            tasks = [_infer_category_with_llm(p.name, p.description) for _, p in inference_tasks]
            inferred_cats = await asyncio.gather(*tasks, return_exceptions=True)
            for (i, p), cat in zip(inference_tasks, inferred_cats):
                if isinstance(cat, Exception):
                    valid_products[i].category = "Other"
                else:
                    valid_products[i].category = cat

    # Fallback: any remaining "INFER" → "Other"
    for p in valid_products:
        if p.category == "INFER":
            p.category = "Other"

    stats = {
        "total_parsed": len(raw_products),
        "valid": len(valid_products),
        "invalid": len(raw_products) - len(valid_products),
        "errors_count": len(all_errors),
        "warnings_count": len(all_warnings),
        "source_format": source_format,
    }

    # Success if at least some products are valid
    success = len(valid_products) > 0 and len(all_errors) == 0

    return NormalizationResult(
        success=success,
        products=valid_products,
        errors=all_errors,
        warnings=all_warnings,
        stats=stats,
    )
