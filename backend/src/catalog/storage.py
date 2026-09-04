"""
Catalog storage and embedding-based semantic search.
Products are stored in SQLite with pre-computed embeddings for fast search.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import DBMerchant, DBProduct
from src.models import (
    AgentPermissions, MerchantCatalog, NormalizedProduct,
    PaymentConstraints, ShippingOption, CatalogStatus, ProductSearchResult, SearchResponse
)

logger = logging.getLogger(__name__)


def _product_to_db(product: NormalizedProduct, merchant_id: str) -> DBProduct:
    """Convert Pydantic model to DB model."""
    return DBProduct(
        product_id=product.product_id,
        merchant_id=merchant_id,
        name=product.name,
        description=product.description,
        price_inr=product.price_inr,
        availability=product.availability,
        stock_count=product.stock_count,
        category=product.category,
        payment_constraints=product.payment_constraints.model_dump(),
        return_policy_days=product.return_policy_days,
        shipping_options=[s.model_dump() for s in product.shipping_options],
        embedding=product.embedding,
        source_format=product.source_format,
    )


def _db_to_product(db: DBProduct) -> NormalizedProduct:
    """Convert DB model to Pydantic model."""
    pc = db.payment_constraints or {}
    so_list = db.shipping_options or [{"method": "standard", "days": 5, "cost_inr": 0}]

    return NormalizedProduct(
        product_id=db.product_id,
        name=db.name,
        description=db.description or "",
        price_inr=db.price_inr,
        availability=db.availability,
        stock_count=db.stock_count,
        category=db.category or "Other",
        payment_constraints=PaymentConstraints(**pc),
        return_policy_days=db.return_policy_days or 0,
        shipping_options=[ShippingOption(**s) for s in so_list],
        embedding=db.embedding,
        source_format=db.source_format or "form",
        created_at=db.created_at or datetime.utcnow(),
    )


def _db_to_catalog(db: DBMerchant, products: List[DBProduct]) -> MerchantCatalog:
    """Convert DB merchant + products to Pydantic catalog."""
    perms = db.agent_permissions or {}
    return MerchantCatalog(
        merchant_id=db.merchant_id,
        merchant_name=db.merchant_name,
        catalog_version=db.catalog_version or "v1.0",
        products=[_db_to_product(p) for p in products],
        agent_permissions=AgentPermissions(**perms),
        status=CatalogStatus(db.status or "DRAFT"),
        onboarding_source=db.onboarding_source or "form",
        created_at=db.created_at or datetime.utcnow(),
        updated_at=db.updated_at or datetime.utcnow(),
    )


# ── Storage Operations ────────────────────────────────────────────────────────

async def save_catalog(
    db: AsyncSession,
    catalog: MerchantCatalog,
) -> MerchantCatalog:
    """Save or update a merchant catalog and its products."""
    # Check if merchant exists
    result = await db.execute(
        select(DBMerchant).where(DBMerchant.merchant_id == catalog.merchant_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update merchant
        existing.merchant_name = catalog.merchant_name
        existing.catalog_version = catalog.catalog_version
        existing.status = catalog.status.value
        existing.agent_permissions = catalog.agent_permissions.model_dump()
        existing.updated_at = datetime.utcnow()
        db_merchant = existing
    else:
        # Create new merchant
        db_merchant = DBMerchant(
            merchant_id=catalog.merchant_id,
            merchant_name=catalog.merchant_name,
            catalog_version=catalog.catalog_version,
            status=catalog.status.value,
            onboarding_source=catalog.onboarding_source,
            agent_permissions=catalog.agent_permissions.model_dump(),
        )
        db.add(db_merchant)
        await db.flush()

    # Delete existing products for this merchant using bulk delete
    from sqlalchemy import delete as sql_delete
    await db.execute(
        sql_delete(DBProduct)
        .where(DBProduct.merchant_id == catalog.merchant_id)
        .execution_options(synchronize_session="fetch")
    )
    await db.flush()
    # Expunge any cached product objects so SQLAlchemy identity map is clean
    db.expire_all()

    # Insert new products
    for product in catalog.products:
        db_product = _product_to_db(product, catalog.merchant_id)
        db.add(db_product)

    await db.flush()
    return catalog


async def get_catalog(
    db: AsyncSession,
    merchant_id: str,
) -> Optional[MerchantCatalog]:
    """Get full catalog for a merchant."""
    result = await db.execute(
        select(DBMerchant).where(DBMerchant.merchant_id == merchant_id)
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        return None

    products_result = await db.execute(
        select(DBProduct).where(DBProduct.merchant_id == merchant_id)
    )
    products = products_result.scalars().all()
    return _db_to_catalog(merchant, list(products))


async def get_all_merchants(db: AsyncSession) -> List[Dict[str, Any]]:
    """Get summary list of all published merchants."""
    result = await db.execute(
        select(DBMerchant).where(DBMerchant.status == "PUBLISHED")
    )
    merchants = result.scalars().all()
    summaries = []
    for m in merchants:
        count_result = await db.execute(
            select(DBProduct).where(
                DBProduct.merchant_id == m.merchant_id,
                DBProduct.availability == True
            )
        )
        product_count = len(count_result.scalars().all())
        summaries.append({
            "merchant_id": m.merchant_id,
            "merchant_name": m.merchant_name,
            "catalog_version": m.catalog_version,
            "status": m.status,
            "product_count": product_count,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return summaries


async def get_product(
    db: AsyncSession,
    merchant_id: str,
    product_id: str,
) -> Optional[NormalizedProduct]:
    """Get a single product by ID."""
    result = await db.execute(
        select(DBProduct).where(
            DBProduct.merchant_id == merchant_id,
            DBProduct.product_id == product_id,
        )
    )
    db_product = result.scalar_one_or_none()
    if not db_product:
        return None
    return _db_to_product(db_product)


async def get_availability(
    db: AsyncSession,
    merchant_id: str,
) -> Dict[str, bool]:
    """Get current availability for all products of a merchant."""
    result = await db.execute(
        select(DBProduct).where(DBProduct.merchant_id == merchant_id)
    )
    products = result.scalars().all()
    return {p.product_id: p.availability for p in products}


async def update_product_stock(
    db: AsyncSession,
    merchant_id: str,
    product_id: str,
    new_stock: int,
):
    """Update stock count for a product."""
    result = await db.execute(
        select(DBProduct).where(
            DBProduct.merchant_id == merchant_id,
            DBProduct.product_id == product_id,
        )
    )
    product = result.scalar_one_or_none()
    if product:
        product.stock_count = max(0, new_stock)
        product.availability = new_stock > 0


# ── Semantic Search ───────────────────────────────────────────────────────────

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    try:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        norm_a = np.linalg.norm(va)
        norm_b = np.linalg.norm(vb)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(va, vb) / (norm_a * norm_b))
    except Exception:
        return 0.0


async def search_catalog(
    db: AsyncSession,
    merchant_id: str,
    query: str,
    limit: int = 5,
    min_similarity: float = 0.1,
    max_price: Optional[float] = None,
) -> SearchResponse:
    """
    Semantic search over merchant's product catalog using embeddings.
    Falls back to keyword matching if embeddings unavailable.
    """
    from src.ai_provider import get_embedding_provider

    # Get available products, filtered by max_price if specified
    stmt = select(DBProduct).where(
        DBProduct.merchant_id == merchant_id,
        DBProduct.availability == True,
    )
    if max_price is not None:
        stmt = stmt.where(DBProduct.price_inr <= max_price)

    result = await db.execute(stmt)
    products = result.scalars().all()

    # Fallback to all products if budget filter returned 0 items
    if not products and max_price is not None:
        fallback_stmt = select(DBProduct).where(
            DBProduct.merchant_id == merchant_id,
            DBProduct.availability == True,
        )
        fb_result = await db.execute(fallback_stmt)
        products = fb_result.scalars().all()

    if not products:
        return SearchResponse(
            query=query,
            merchant_id=merchant_id,
            results=[],
            total_searched=0,
            embedding_used=False,
        )

    # Check if products have embeddings
    has_embeddings = any(p.embedding for p in products)
    embedding_used = False
    scored: List[Tuple[float, NormalizedProduct]] = []

    if has_embeddings:
        try:
            embedder = get_embedding_provider()
            query_embedding = await embedder.embed(query)
            embedding_used = True

            for db_product in products:
                product = _db_to_product(db_product)
                if product.embedding:
                    score = _cosine_similarity(query_embedding, product.embedding)
                else:
                    # Keyword fallback for products without embeddings
                    score = _keyword_score(query, product)
                scored.append((score, product))

        except Exception as e:
            logger.warning(f"Embedding search failed: {e}, falling back to keyword search")
            embedding_used = False
            for db_product in products:
                product = _db_to_product(db_product)
                score = _keyword_score(query, product)
                scored.append((score, product))
    else:
        # Pure keyword search
        for db_product in products:
            product = _db_to_product(db_product)
            score = _keyword_score(query, product)
            scored.append((score, product))

    # Sort by score and filter by minimum threshold
    scored.sort(key=lambda x: x[0], reverse=True)
    top_results = [
        (score, product)
        for score, product in scored[:limit]
        if score >= min_similarity
    ]

    # If no results meet threshold, return top N anyway
    if not top_results and scored:
        top_results = scored[:min(limit, len(scored))]

    results = [
        ProductSearchResult(
            product=product,
            similarity_score=round(score, 4),
            rank=i + 1,
        )
        for i, (score, product) in enumerate(top_results)
    ]

    return SearchResponse(
        query=query,
        merchant_id=merchant_id,
        results=results,
        total_searched=len(products),
        embedding_used=embedding_used,
    )


def _keyword_score(query: str, product: NormalizedProduct) -> float:
    """Simple keyword matching fallback for when embeddings are unavailable."""
    query_lower = query.lower()
    query_words = set(re.split(r'\W+', query_lower))

    product_text = f"{product.name} {product.description} {product.category}".lower()
    product_words = set(re.split(r'\W+', product_text))

    if not query_words:
        return 0.5  # neutral

    # Word overlap score
    overlap = len(query_words & product_words)
    word_score = overlap / len(query_words)

    # Price matching (under/below/cheap)
    price_score = 0.0
    price_match = re.search(r'(?:under|below|within|max|less than|upto|up to)\s*[₹rs]?\s*(\d+)', query_lower)
    if price_match:
        max_price = float(price_match.group(1))
        if product.price_inr <= max_price:
            price_score = 0.3
        else:
            price_score = -0.3

    if "cheap" in query_lower or "cheapest" in query_lower or "lowest" in query_lower:
        price_score += 0.1

    return min(1.0, max(0.0, word_score + price_score))


import re  # ensure re is imported at module level
