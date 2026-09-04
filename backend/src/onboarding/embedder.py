"""
Product embedding generator.
Generates embeddings for all products at catalog publish time.
Embeddings are stored with products for fast search at query time.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from src.models import NormalizedProduct

logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # Process embeddings in batches to avoid timeouts


def _product_to_embedding_text(product: NormalizedProduct) -> str:
    """Create rich text representation of a product for embedding."""
    parts = [product.name]

    if product.description:
        parts.append(product.description)

    if product.category and product.category != "Other":
        parts.append(f"Category: {product.category}")

    parts.append(f"Price: ₹{product.price_inr:,.0f}")

    if product.return_policy_days > 0:
        parts.append(f"{product.return_policy_days}-day returns")

    shipping = product.shipping_options[0] if product.shipping_options else None
    if shipping and shipping.cost_inr == 0:
        parts.append("Free shipping")

    return " — ".join(parts)


async def generate_embeddings(
    products: List[NormalizedProduct],
    on_progress: Optional[callable] = None,
) -> List[NormalizedProduct]:
    """
    Generate embeddings for all products.
    Updates products in-place with embedding vectors.
    Gracefully handles failures — products without embeddings still work (keyword search fallback).
    """
    from src.ai_provider import get_embedding_provider

    try:
        embedder = get_embedding_provider()
    except Exception as e:
        logger.error(f"Failed to initialize embedding provider: {e}")
        return products  # Return unchanged — keyword search will work

    # Build text representations
    texts = [_product_to_embedding_text(p) for p in products]
    total = len(texts)
    embedded_count = 0

    # Process in batches
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch_texts = texts[batch_start:batch_end]
        batch_products = products[batch_start:batch_end]

        try:
            embeddings = await embedder.embed_batch(batch_texts)
            for product, embedding in zip(batch_products, embeddings):
                product.embedding = embedding
                embedded_count += 1
        except Exception as e:
            logger.warning(f"Embedding batch {batch_start}-{batch_end} failed: {e}. "
                          f"Affected products will use keyword search.")
            # Continue — don't fail the whole operation

        if on_progress:
            try:
                await on_progress(batch_end, total)
            except Exception:
                pass

        # Small delay between batches to avoid rate limits
        if batch_end < total:
            await asyncio.sleep(0.1)

    logger.info(f"Generated embeddings for {embedded_count}/{total} products "
                f"using {embedder.provider_name}")

    return products
