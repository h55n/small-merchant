"""
Small-Merchant AI Readiness Agent — FastAPI Backend
All routes, WebSocket streaming, CORS, Alembic migrations,
rate limiting, structured logging, background tasks, JWT auth,
Redis session state, Prometheus metrics, UAP skeleton.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, Form, HTTPException,
    Query, Request, UploadFile, WebSocket, WebSocketDisconnect, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

# Load env first
load_dotenv()

# ── Structured Logging ────────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, os.getenv("LOG_LEVEL", "INFO"))
    ),
)

# Also configure stdlib for libraries that use it
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = structlog.get_logger("api.main")

from src.database import AsyncSessionLocal, DBSession, get_db
from src.models import (
    AgentPermissions, BuyerSession, CatalogStatus, ConfirmPurchaseRequest,
    CreateSessionRequest, MerchantCatalog, NormalizationResult,
    OnboardManualRequest, OnboardSheetsRequest, OnboardURLRequest,
    PublishCatalogRequest, SessionOutcome,
)

# ── Rate Limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── Redis Session State ───────────────────────────────────────────────────────

_redis_client: Optional[Any] = None

async def _get_redis():
    """Return Redis client if REDIS_URL is set, else None (in-memory fallback)."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis.asyncio as redis
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        await _redis_client.ping()
        log.info("redis_connected", url=redis_url)
        return _redis_client
    except Exception as e:
        log.warning("redis_unavailable", error=str(e))
        return None


async def save_session_state(session_id: str, state: dict) -> None:
    r = await _get_redis()
    if r:
        await r.setex(f"session:{session_id}", 3600, json.dumps(state, default=str))


async def load_session_state(session_id: str) -> Optional[dict]:
    r = await _get_redis()
    if r:
        raw = await r.get(f"session:{session_id}")
        return json.loads(raw) if raw else None
    return None


# ── JWT Auth (Phase 3.1) ──────────────────────────────────────────────────────

_SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

def create_merchant_token(merchant_id: str) -> str:
    """Issue a JWT scoped to a merchant_id."""
    try:
        from jose import jwt
        payload = {
            "sub": merchant_id,
            "type": "merchant",
            "exp": datetime.utcnow() + timedelta(days=90),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, _SECRET_KEY, algorithm="HS256")
    except ImportError:
        # python-jose not installed — return a simple HMAC token
        import base64
        data = json.dumps({"sub": merchant_id, "type": "merchant"}).encode()
        sig = hmac.new(_SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(data).decode() + "." + sig


def verify_merchant_token(token: str) -> Optional[str]:
    """Verify token and return merchant_id, or None if invalid."""
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(token, _SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "merchant":
            return None
        return payload.get("sub")
    except Exception:
        return None


# ── Webhook Signature Verification (Phase 1.4) ───────────────────────────────

def verify_razorpay_signature(payload: bytes, signature: str, secret: str) -> bool:
    """HMAC-SHA256 verification for Razorpay webhook payloads."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Input Sanitization (Phase 1.3) ───────────────────────────────────────────

MAX_MERCHANT_NAME_LEN = 200
MAX_PRODUCTS_MANUAL = 100
MAX_CSV_SIZE_MB = 5


def sanitize_text(text: str, max_len: int = 500) -> str:
    """HTML-escape and truncate a string."""
    if not text:
        return ""
    return html.escape(text.strip())[:max_len]


# ── Prometheus Metrics (Phase 3.6) ────────────────────────────────────────────

try:
    from prometheus_client import Counter, Gauge, Histogram

    SESSIONS_CREATED = Counter(
        "agent_sessions_created_total", "Total agent sessions started"
    )
    SESSIONS_COMPLETED = Counter(
        "agent_sessions_completed_total",
        "Agent sessions completed by status",
        ["status"],
    )
    PAYMENT_ATTEMPTS = Counter(
        "payment_attempts_total",
        "Payment attempts by method and outcome",
        ["method", "outcome"],
    )
    CATALOG_SEARCH_LATENCY = Histogram(
        "catalog_search_duration_seconds", "Catalog search latency in seconds"
    )
    ACTIVE_SESSIONS = Gauge("active_agent_sessions", "Currently active WebSocket sessions")
    _prometheus_available = True
except ImportError:
    _prometheus_available = False


# ── Application Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle with Alembic migrations."""
    log.info("startup_begin", service="small-merchant-ai-readiness-agent")

    # Initialize database tables
    try:
        from src.database import create_tables
        await create_tables()
        log.info("database_tables_initialized")
    except Exception as e:
        log.warning("table_init_warning", error=str(e))

    # Seed demo merchant
    try:
        await _seed_demo_merchant()
    except Exception as e:
        log.warning("demo_seed_failed", error=str(e))

    log.info("startup_complete")
    yield
    log.info("shutdown")


# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Small-Merchant AI Readiness Agent",
    description=(
        "Self-service onboarding layer enabling small merchants to become "
        "transactable by AI buyers. Built for Razorpay AI Buildathon 2026."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiter exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Prometheus instrumentation
if _prometheus_available:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            excluded_handlers=["/metrics", "/health"],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    except ImportError:
        pass


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return structured JSON error."""
    log.error(
        "unhandled_exception",
        method=request.method,
        url=str(request.url),
        exc_type=type(exc).__name__,
        exc_msg=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred.", "type": type(exc).__name__},
    )


# CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production via CORS_ORIGINS env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store (Redis-backed when REDIS_URL is set)
_active_agents: Dict[str, Any] = {}


# ── Demo Seeding ──────────────────────────────────────────────────────────────

async def _seed_demo_merchant():
    """Seed the Kiran Artisan Goods demo catalog at startup if not present."""
    from src.catalog.storage import get_catalog, save_catalog
    from src.onboarding.embedder import generate_embeddings
    from src.onboarding.normalizer import normalize
    from src.onboarding.parsers import parse_csv

    merchant_id = "merch_DEMO01"
    async with AsyncSessionLocal() as db:
        catalog = await get_catalog(db, merchant_id)
        if catalog and len(catalog.products) > 0:
            await db.rollback()
            return

        fixture_path = "data/merchant_fixtures/kiran_artisan_catalog.csv"
        if not os.path.exists(fixture_path):
            log.warning("fixture_not_found", path=fixture_path)
            return

        with open(fixture_path, "rb") as f:
            raw, error = parse_csv(f.read())

        if error or not raw:
            log.error("fixture_parse_failed", error=error)
            return

        result = await normalize(raw, source_format="csv", infer_categories=False)
        result.products = await generate_embeddings(result.products)

        catalog = MerchantCatalog(
            merchant_id=merchant_id,
            merchant_name="Kiran Artisan Goods",
            status=CatalogStatus.PUBLISHED,
            products=result.products,
            agent_permissions=AgentPermissions(
                max_transaction_inr=10000,
                requires_confirmation_above_inr=0,
                auto_approve_below_inr=0,
            ),
            onboarding_source="fixture",
        )
        await save_catalog(db, catalog)
        await db.commit()
        log.info("demo_merchant_seeded", product_count=len(result.products))


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    from src.ai_provider import get_ai_provider, get_embedding_provider
    ai = get_ai_provider()
    emb = get_embedding_provider()
    redis_ok = False
    r = await _get_redis()
    if r:
        try:
            await r.ping()
            redis_ok = True
        except Exception:
            pass
    return {
        "status": "ok",
        "ai_provider": ai.get_available_provider().value,
        "embedding_provider": emb.provider_name,
        "redis": "connected" if redis_ok else "not_configured",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Merchant Onboarding ───────────────────────────────────────────────────────

@app.post("/api/merchants/onboard/csv")
@limiter.limit("20/minute")
async def onboard_csv(
    request: Request,
    merchant_name: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Onboard a merchant via CSV file upload."""
    from src.onboarding.parsers import parse_csv
    from src.onboarding.normalizer import normalize

    merchant_name = sanitize_text(merchant_name, MAX_MERCHANT_NAME_LEN)
    if not merchant_name:
        raise HTTPException(400, "merchant_name is required.")

    if not (file.filename or "").endswith(".csv"):
        raise HTTPException(400, "Only CSV files supported.")

    content = await file.read()
    if len(content) > MAX_CSV_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File too large. Maximum {MAX_CSV_SIZE_MB}MB.")

    raw, error = parse_csv(content)
    if error:
        raise HTTPException(400, f"CSV parsing failed: {error}")

    result = await normalize(raw, source_format="csv")
    return await _save_draft_catalog(db, merchant_name, result, "csv")


@app.post("/api/merchants/onboard/sheets")
@limiter.limit("20/minute")
async def onboard_sheets(
    request: Request,
    req: OnboardSheetsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Onboard a merchant via Google Sheets URL."""
    from src.onboarding.parsers import parse_google_sheets
    from src.onboarding.normalizer import normalize

    req.merchant_name = sanitize_text(req.merchant_name, MAX_MERCHANT_NAME_LEN)
    raw, error = parse_google_sheets(req.sheets_url)
    if error:
        raise HTTPException(400, error)

    result = await normalize(raw, source_format="sheets")
    return await _save_draft_catalog(db, req.merchant_name, result, "sheets")


@app.post("/api/merchants/onboard/manual")
@limiter.limit("20/minute")
async def onboard_manual(
    request: Request,
    req: OnboardManualRequest,
    db: AsyncSession = Depends(get_db),
):
    """Onboard a merchant via manual form entry (max 100 products)."""
    from src.onboarding.parsers import parse_manual_form
    from src.onboarding.normalizer import normalize

    req.merchant_name = sanitize_text(req.merchant_name, MAX_MERCHANT_NAME_LEN)
    if len(req.products) > MAX_PRODUCTS_MANUAL:
        raise HTTPException(400, f"Maximum {MAX_PRODUCTS_MANUAL} products per manual submission.")

    # Sanitize product names and descriptions
    sanitized = []
    for p in req.products:
        sp = dict(p)
        if "name" in sp:
            sp["name"] = sanitize_text(str(sp["name"]), 200)
        if "description" in sp:
            sp["description"] = sanitize_text(str(sp.get("description", "")), 500)
        sanitized.append(sp)

    raw, error = parse_manual_form(sanitized)
    if error:
        raise HTTPException(400, error)

    result = await normalize(raw, source_format="form")
    return await _save_draft_catalog(db, req.merchant_name, result, "form")


@app.post("/api/merchants/onboard/url")
@limiter.limit("10/minute")
async def onboard_url(
    request: Request,
    req: OnboardURLRequest,
    db: AsyncSession = Depends(get_db),
):
    """Onboard a merchant via product page URL (best-effort scraper)."""
    from src.onboarding.parsers import parse_url
    from src.onboarding.normalizer import normalize

    req.merchant_name = sanitize_text(req.merchant_name, MAX_MERCHANT_NAME_LEN)
    raw, error = parse_url(req.product_page_url)
    if error:
        raise HTTPException(400, error)

    result = await normalize(raw, source_format="url")
    return await _save_draft_catalog(db, req.merchant_name, result, "url")


async def _save_draft_catalog(
    db: AsyncSession,
    merchant_name: str,
    result: NormalizationResult,
    source: str,
) -> Dict:
    """Save parsed products as DRAFT catalog and return summary."""
    from src.catalog.storage import save_catalog
    import uuid

    merchant_id = f"merch_{uuid.uuid4().hex[:8]}"
    catalog = MerchantCatalog(
        merchant_id=merchant_id,
        merchant_name=merchant_name,
        status=CatalogStatus.DRAFT,
        products=result.products,
        onboarding_source=source,
    )

    if result.products:
        await save_catalog(db, catalog)

    log.info(
        "catalog_draft_saved",
        merchant_id=merchant_id,
        source=source,
        valid=result.stats.get("valid", 0),
        invalid=result.stats.get("invalid", 0),
    )

    return {
        "merchant_id": merchant_id,
        "merchant_name": merchant_name,
        "catalog_version": "v1.0",
        "status": "DRAFT",
        "validation": {
            "total_parsed": result.stats.get("total_parsed", 0),
            "valid": result.stats.get("valid", 0),
            "invalid": result.stats.get("invalid", 0),
            "errors": [e.model_dump() for e in result.errors],
            "warnings": [w.model_dump() for w in result.warnings],
        },
        "preview": [
            {
                "product_id": p.product_id,
                "name": p.name,
                "price_inr": p.price_inr,
                "category": p.category,
                "availability": p.availability,
                "stock_count": p.stock_count,
                "description": p.description[:80] if p.description else "",
            }
            for p in result.products[:10]
        ],
        "can_publish": len(result.errors) == 0 and len(result.products) > 0,
    }


# ── Background Embedding Task (Phase 1.6) ─────────────────────────────────────

async def _background_generate_embeddings(merchant_id: str, permissions: AgentPermissions):
    """Run embedding generation in the background after publish_catalog() returns."""
    from src.catalog.storage import get_catalog, save_catalog
    from src.onboarding.embedder import generate_embeddings
    t0 = time.time()
    try:
        async with AsyncSessionLocal() as db:
            catalog = await get_catalog(db, merchant_id)
            if not catalog:
                log.error("bg_embed_merchant_not_found", merchant_id=merchant_id)
                return
            catalog.products = await generate_embeddings(catalog.products)
            catalog.status = CatalogStatus.PUBLISHED
            catalog.agent_permissions = permissions
            catalog.updated_at = datetime.utcnow()
            await save_catalog(db, catalog)
            await db.commit()
        elapsed = round((time.time() - t0) * 1000)
        log.info(
            "bg_embed_complete",
            merchant_id=merchant_id,
            product_count=len(catalog.products),
            elapsed_ms=elapsed,
        )
    except Exception as e:
        log.error("bg_embed_failed", merchant_id=merchant_id, error=str(e))


@app.post("/api/merchants/{merchant_id}/publish")
@limiter.limit("10/minute")
async def publish_catalog(
    request: Request,
    merchant_id: str,
    req: PublishCatalogRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Publish a draft catalog with agent permissions.
    Embedding generation runs in the background — poll /api/merchants/{id}/status.
    Returns a merchant_token (JWT) scoped to this merchant_id.
    """
    from src.catalog.storage import get_catalog, save_catalog

    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")
    if not catalog.products:
        raise HTTPException(400, "Cannot publish an empty catalog.")

    # Immediately flip to PUBLISHING so clients can poll
    catalog.status = CatalogStatus.PUBLISHING
    catalog.updated_at = datetime.utcnow()
    await save_catalog(db, catalog)

    # Queue embedding in background
    background_tasks.add_task(
        _background_generate_embeddings, merchant_id, req.agent_permissions
    )

    merchant_token = create_merchant_token(merchant_id)

    log.info(
        "catalog_publish_queued",
        merchant_id=merchant_id,
        product_count=len(catalog.products),
    )

    return {
        "merchant_id": merchant_id,
        "status": "PUBLISHING",
        "catalog_endpoint": f"/catalog/{merchant_id}",
        "product_count": len(catalog.products),
        "agent_permissions": req.agent_permissions.model_dump(),
        "merchant_token": merchant_token,
        "message": "Embeddings are generating in the background. Poll /api/merchants/{id}/status.",
    }


@app.get("/api/merchants/{merchant_id}/status")
async def get_merchant_status(merchant_id: str, db: AsyncSession = Depends(get_db)):
    """Poll embedding progress. Returns current catalog status."""
    from src.catalog.storage import get_catalog
    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")
    embedded = sum(1 for p in catalog.products if p.embedding)
    return {
        "merchant_id": merchant_id,
        "status": catalog.status.value,
        "product_count": len(catalog.products),
        "embedded_products": embedded,
        "embedding_progress": (
            round(embedded / len(catalog.products) * 100, 1) if catalog.products else 0
        ),
        "updated_at": catalog.updated_at.isoformat(),
    }


@app.get("/api/merchants")
async def list_merchants(db: AsyncSession = Depends(get_db)):
    """List all merchants."""
    from src.catalog.storage import get_all_merchants
    return {"merchants": await get_all_merchants(db)}


@app.get("/api/merchants/{merchant_id}")
async def get_merchant(merchant_id: str, db: AsyncSession = Depends(get_db)):
    """Get merchant details."""
    from src.catalog.storage import get_catalog
    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")
    return {
        "merchant_id": catalog.merchant_id,
        "merchant_name": catalog.merchant_name,
        "status": catalog.status.value,
        "product_count": len(catalog.products),
        "agent_permissions": catalog.agent_permissions.model_dump(),
        "created_at": catalog.created_at.isoformat(),
    }


# ── Merchant Dashboard API (Phase 3.3) ────────────────────────────────────────

@app.get("/api/merchants/{merchant_id}/products")
async def list_merchant_products(
    merchant_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all products for a merchant (paginated)."""
    from src.catalog.storage import get_catalog
    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")
    start = (page - 1) * page_size
    end = start + page_size
    products = catalog.products[start:end]
    return {
        "merchant_id": merchant_id,
        "total": len(catalog.products),
        "page": page,
        "page_size": page_size,
        "products": [p.model_dump(exclude={"embedding"}) for p in products],
    }


@app.post("/api/merchants/{merchant_id}/products")
@limiter.limit("30/minute")
async def add_product(
    request: Request,
    merchant_id: str,
    product_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """Add a single product to an existing catalog."""
    from src.catalog.storage import get_catalog, save_catalog
    from src.onboarding.normalizer import normalize

    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")

    product_data["name"] = sanitize_text(str(product_data.get("name", "")), 200)
    product_data["description"] = sanitize_text(str(product_data.get("description", "")), 500)

    result = await normalize([product_data], source_format="form")
    if not result.products:
        raise HTTPException(400, f"Product validation failed: {result.errors}")

    catalog.products.append(result.products[0])
    catalog.updated_at = datetime.utcnow()
    await save_catalog(db, catalog)

    return {"added": result.products[0].model_dump(exclude={"embedding"})}


@app.patch("/api/merchants/{merchant_id}/products/{product_id}")
async def update_product(
    merchant_id: str,
    product_id: str,
    updates: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """Update price, stock, or availability for a specific product."""
    from src.catalog.storage import get_catalog, save_catalog

    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")

    product = next((p for p in catalog.products if p.product_id == product_id), None)
    if not product:
        raise HTTPException(404, f"Product {product_id} not found.")

    allowed_fields = {"price_inr", "stock_count", "availability", "description"}
    for field, value in updates.items():
        if field in allowed_fields:
            if field == "description":
                value = sanitize_text(str(value), 500)
            setattr(product, field, value)

    catalog.updated_at = datetime.utcnow()
    await save_catalog(db, catalog)
    return {"updated": product.model_dump(exclude={"embedding"})}


@app.delete("/api/merchants/{merchant_id}/products/{product_id}")
async def delete_product(
    merchant_id: str,
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a product from the catalog."""
    from src.catalog.storage import get_catalog, save_catalog

    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")

    before_count = len(catalog.products)
    catalog.products = [p for p in catalog.products if p.product_id != product_id]
    if len(catalog.products) == before_count:
        raise HTTPException(404, f"Product {product_id} not found.")

    catalog.updated_at = datetime.utcnow()
    await save_catalog(db, catalog)
    return {"deleted": product_id, "remaining_products": len(catalog.products)}


@app.patch("/api/merchants/{merchant_id}/permissions")
async def update_permissions(
    merchant_id: str,
    permissions: AgentPermissions,
    db: AsyncSession = Depends(get_db),
):
    """Update agent permissions without re-publishing."""
    from src.catalog.storage import get_catalog, save_catalog

    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")

    catalog.agent_permissions = permissions
    catalog.updated_at = datetime.utcnow()
    await save_catalog(db, catalog)
    return {"merchant_id": merchant_id, "permissions": permissions.model_dump()}


# ── Catalog API (for buyer agent consumption) ──────────────────────────────────

@app.get("/catalog/{merchant_id}")
async def get_full_catalog(merchant_id: str, db: AsyncSession = Depends(get_db)):
    """Return full merchant catalog (agent-queryable). Only available when PUBLISHED."""
    from src.catalog.storage import get_catalog
    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")
    if catalog.status == CatalogStatus.PUBLISHING:
        raise HTTPException(202, "Catalog is being indexed. Retry shortly.")
    if catalog.status != CatalogStatus.PUBLISHED:
        raise HTTPException(403, "Catalog not published yet.")

    return {
        "merchant_id": catalog.merchant_id,
        "merchant_name": catalog.merchant_name,
        "catalog_version": catalog.catalog_version,
        "agent_permissions": catalog.agent_permissions.model_dump(),
        "products": [
            {
                "product_id": p.product_id,
                "name": p.name,
                "description": p.description,
                "price_inr": p.price_inr,
                "availability": p.availability,
                "stock_count": p.stock_count,
                "category": p.category,
                "return_policy_days": p.return_policy_days,
                "shipping_options": [s.model_dump() for s in p.shipping_options],
                "payment_constraints": p.payment_constraints.model_dump(),
            }
            for p in catalog.products
        ],
    }


@app.get("/catalog/{merchant_id}/search")
@limiter.limit("60/minute")
async def search_catalog_endpoint(
    request: Request,
    merchant_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(default=5, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search over merchant catalog."""
    from src.catalog.storage import search_catalog
    t0 = time.time()
    results = await search_catalog(db, merchant_id, q, limit)
    elapsed = time.time() - t0
    if _prometheus_available:
        CATALOG_SEARCH_LATENCY.observe(elapsed)
    return {
        "query": q,
        "merchant_id": merchant_id,
        "total_searched": results.total_searched,
        "embedding_used": results.embedding_used,
        "results": [
            {
                "product_id": r.product.product_id,
                "name": r.product.name,
                "price_inr": r.product.price_inr,
                "description": r.product.description,
                "category": r.product.category,
                "availability": r.product.availability,
                "similarity_score": r.similarity_score,
                "rank": r.rank,
            }
            for r in results.results
        ],
    }


@app.get("/catalog/{merchant_id}/product/{product_id}")
async def get_product_endpoint(
    merchant_id: str, product_id: str, db: AsyncSession = Depends(get_db)
):
    from src.catalog.storage import get_product
    product = await get_product(db, merchant_id, product_id)
    if not product:
        raise HTTPException(404, f"Product {product_id} not found.")
    return product.model_dump(exclude={"embedding"})


@app.get("/catalog/{merchant_id}/availability")
async def get_availability_endpoint(merchant_id: str, db: AsyncSession = Depends(get_db)):
    from src.catalog.storage import get_availability
    return await get_availability(db, merchant_id)


# ── UAP/ACP Protocol Skeleton (Phase 3.5) ────────────────────────────────────

@app.get("/catalog/{merchant_id}/capabilities")
async def get_catalog_capabilities(merchant_id: str, db: AsyncSession = Depends(get_db)):
    """
    Advertise catalog capabilities per UAP/ACP draft protocol.
    Returns what operations this catalog endpoint supports.
    """
    from src.catalog.storage import get_catalog
    catalog = await get_catalog(db, merchant_id)
    if not catalog or catalog.status != CatalogStatus.PUBLISHED:
        raise HTTPException(404, "Catalog not available.")
    return {
        "merchant_id": merchant_id,
        "protocol_version": "UAP-draft-0.1",
        "capabilities": {
            "search": True,
            "reserve": False,       # Phase 3.5 — pending UAP finalization
            "purchase": True,
            "cancel": False,        # Phase 3.5 — pending UAP finalization
            "availability": True,
        },
        "agent_registration": "/agents/register",
        "note": "Reserve and cancel pending NPCI UAP finalization (RBI approval pending August 2026)",
    }


@app.post("/agents/register")
async def register_agent(
    agent_id: str,
    merchant_id: str,
    callback_url: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    UAP-compatible agent registration skeleton.
    Issues a delegation_token scoped to this agent+merchant pair.
    Full implementation pending UAP finalization.
    """
    from src.catalog.storage import get_catalog
    catalog = await get_catalog(db, merchant_id)
    if not catalog or catalog.status != CatalogStatus.PUBLISHED:
        raise HTTPException(404, "Merchant not available for agent registration.")
    delegation_token = create_merchant_token(f"{agent_id}:{merchant_id}")
    return {
        "agent_id": agent_id,
        "merchant_id": merchant_id,
        "delegation_token": delegation_token,
        "status": "registered",
        "note": "Full UAP agent registration pending protocol finalization.",
    }


@app.post("/catalog/{merchant_id}/reserve")
async def reserve_product(
    merchant_id: str,
    product_id: str,
    agent_token: str,
    ttl_seconds: int = Query(default=300, ge=60, le=3600),
    db: AsyncSession = Depends(get_db),
):
    """
    UAP-draft reserve endpoint skeleton.
    Holds a product for N seconds before payment.
    Full implementation pending NPCI UAP finalization.
    """
    return {
        "reservation_id": None,
        "status": "NOT_IMPLEMENTED",
        "message": "Product reservation is pending UAP protocol finalization by NPCI/RBI.",
        "product_id": product_id,
        "merchant_id": merchant_id,
        "ttl_seconds": ttl_seconds,
    }


# ── Catalog Versioning (Phase 3.4) ────────────────────────────────────────────

@app.get("/catalog/{merchant_id}/versions")
async def get_catalog_versions(merchant_id: str, db: AsyncSession = Depends(get_db)):
    """
    Return catalog version history.
    Full version tracking requires DBCatalogVersion table (Phase 3.4 extension).
    Currently returns current version metadata.
    """
    from src.catalog.storage import get_catalog
    catalog = await get_catalog(db, merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {merchant_id} not found.")
    return {
        "merchant_id": merchant_id,
        "current_version": catalog.catalog_version,
        "versions": [
            {
                "version": catalog.catalog_version,
                "status": catalog.status.value,
                "product_count": len(catalog.products),
                "updated_at": catalog.updated_at.isoformat(),
            }
        ],
        "note": "Full version history with DBCatalogVersion table is a Phase 3.4 extension.",
    }


# ── Agent Sessions ─────────────────────────────────────────────────────────────

@app.post("/api/agent/session")
@limiter.limit("10/minute")
async def create_session(
    request: Request,
    req: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new buyer agent session."""
    from src.catalog.storage import get_catalog

    catalog = await get_catalog(db, req.merchant_id)
    if not catalog:
        raise HTTPException(404, f"Merchant {req.merchant_id} not found.")
    if catalog.status == CatalogStatus.PUBLISHING:
        raise HTTPException(503, "Catalog is still being indexed. Retry shortly.")
    if catalog.status != CatalogStatus.PUBLISHED:
        raise HTTPException(400, "Merchant catalog is not published.")

    session = BuyerSession(
        merchant_id=req.merchant_id,
        purchase_intent=req.purchase_intent,
        spending_limit_inr=req.spending_limit_inr,
    )

    db_session = DBSession(
        session_id=session.session_id,
        merchant_id=session.merchant_id,
        purchase_intent=session.purchase_intent,
        spending_limit_inr=session.spending_limit_inr,
        status="ACTIVE",
    )
    db.add(db_session)
    await db.commit()

    if _prometheus_available:
        SESSIONS_CREATED.inc()

    await save_session_state(session.session_id, {
        "session_id": session.session_id,
        "merchant_id": session.merchant_id,
        "purchase_intent": session.purchase_intent,
        "spending_limit_inr": session.spending_limit_inr,
        "status": "ACTIVE",
    })

    log.info(
        "session_created",
        session_id=session.session_id,
        merchant_id=catalog.merchant_id,
        spending_limit_inr=session.spending_limit_inr,
    )

    return {
        "session_id": session.session_id,
        "merchant_id": catalog.merchant_id,
        "merchant_name": catalog.merchant_name,
        "spending_limit_inr": session.spending_limit_inr,
        "status": "ACTIVE",
    }


@app.websocket("/ws/agent/{session_id}")
async def agent_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time agent streaming.
    Client sends: {"type": "message", "content": "..."}
    Server streams: {type, content/data} events
    """
    await websocket.accept()
    log.info("websocket_connected", session_id=session_id)

    if _prometheus_available:
        ACTIVE_SESSIONS.inc()

    try:
        async with AsyncSessionLocal() as db:
            from src.agent.buyer_agent import BuyerAgent
            from src.audit.logger import SessionAuditLogger
            from src.catalog.storage import get_catalog
            from sqlalchemy import select

            # Load session from DB (with Redis fallback for state)
            result = await db.execute(
                select(DBSession).where(DBSession.session_id == session_id)
            )
            db_sess = result.scalar_one_or_none()
            if not db_sess:
                await websocket.send_json({"type": "error", "content": "Session not found."})
                await websocket.close()
                return

            session = BuyerSession(
                session_id=db_sess.session_id,
                merchant_id=db_sess.merchant_id,
                purchase_intent=db_sess.purchase_intent,
                spending_limit_inr=db_sess.spending_limit_inr,
            )

            # Restore state from Redis if available
            cached_state = await load_session_state(session_id)
            if cached_state:
                session.payment_attempts = cached_state.get("payment_attempts", 0)
                session.confirmation_gate_hit = cached_state.get("confirmation_gate_hit", False)

            catalog = await get_catalog(db, session.merchant_id)
            if not catalog:
                await websocket.send_json({"type": "error", "content": "Merchant not found."})
                return

            audit = SessionAuditLogger(session_id, db)
            agent = BuyerAgent(session=session, catalog=catalog, db=db, audit=audit)
            _active_agents[session_id] = agent

            await websocket.send_json({
                "type": "session_info",
                "data": {
                    "merchant_name": catalog.merchant_name,
                    "product_count": len(catalog.products),
                    "spending_limit_inr": session.spending_limit_inr,
                }
            })

            while True:
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=300.0)
                    msg = json.loads(raw)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "timeout", "content": "Session timed out."})
                    break
                except WebSocketDisconnect:
                    break

                msg_type = msg.get("type", "message")
                content = msg.get("content", "")

                if msg_type == "message":
                    async for event in agent.process_message(content):
                        await websocket.send_json(event)
                        if event["type"] == "session_complete":
                            await _persist_session_outcome(db, db_sess, session, audit)
                            if _prometheus_available:
                                SESSIONS_COMPLETED.labels(status=session.status.value).inc()

                elif msg_type == "confirm":
                    confirmed = msg.get("confirmed", False)
                    product_id = msg.get("product_id")
                    async for event in agent.handle_confirmation(confirmed, product_id):
                        await websocket.send_json(event)
                        if event["type"] == "session_complete":
                            await _persist_session_outcome(db, db_sess, session, audit)
                            if _prometheus_available:
                                SESSIONS_COMPLETED.labels(status=session.status.value).inc()
                                outcome = event.get("data", {}).get("outcome", "UNKNOWN")
                                method = event.get("data", {}).get("payment_method", "unknown")
                                PAYMENT_ATTEMPTS.labels(
                                    method=method,
                                    outcome=outcome,
                                ).inc()

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        log.info("websocket_disconnected", session_id=session_id)
    except Exception as e:
        log.error("websocket_error", session_id=session_id, error=str(e))
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
    finally:
        _active_agents.pop(session_id, None)
        if _prometheus_available:
            ACTIVE_SESSIONS.dec()
        log.info("websocket_closed", session_id=session_id)


async def _persist_session_outcome(db, db_sess, session, audit):
    """Write final session outcome fields to the DB and update Redis state."""
    db_sess.status = session.status.value
    db_sess.payment_attempts = session.payment_attempts
    db_sess.confirmation_gate_hit = session.confirmation_gate_hit
    db_sess.ai_provider_used = session.ai_provider_used
    db_sess.total_session_ms = audit.elapsed_ms()
    db_sess.completed_at = datetime.utcnow()
    if hasattr(session, "payment_id"):
        db_sess.payment_id = getattr(session, "payment_id", None)
    if hasattr(session, "product_purchased"):
        db_sess.product_purchased = getattr(session, "product_purchased", None)
    if hasattr(session, "amount_inr"):
        db_sess.amount_inr = getattr(session, "amount_inr", None)
    await db.commit()

    # Update Redis state
    await save_session_state(session.session_id, {
        "session_id": session.session_id,
        "status": session.status.value,
        "payment_attempts": session.payment_attempts,
        "confirmation_gate_hit": session.confirmation_gate_hit,
    })

    log.info(
        "session_complete",
        session_id=session.session_id,
        status=session.status.value,
        payment_attempts=session.payment_attempts,
        elapsed_ms=audit.elapsed_ms(),
    )


@app.get("/api/agent/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """List recent agent sessions."""
    from src.audit.logger import get_all_sessions
    return {"sessions": await get_all_sessions(db)}


@app.get("/api/agent/sessions/{session_id}/audit")
async def get_session_audit_trail(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get full audit trail for a session."""
    from src.audit.logger import get_session_audit
    trail = await get_session_audit(db, session_id)
    if not trail:
        raise HTTPException(404, f"Session {session_id} not found.")
    return trail.model_dump(mode="json")


# ── Webhook Verification (Phase 1.4) ─────────────────────────────────────────

@app.post("/webhooks/razorpay/dispute")
async def razorpay_webhook(request: Request):
    """Receive Razorpay webhook events (e.g. dispute created). Verifies HMAC signature."""
    payload = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    if secret and not verify_razorpay_signature(payload, sig, secret):
        log.warning("webhook_signature_invalid", sig=sig[:16])
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event_data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON payload")

    event_type = event_data.get("event", "unknown")
    log.info("webhook_received", event_type=event_type)

    # Handle dispute events
    if event_type == "dispute.created":
        payment_id = event_data.get("payload", {}).get("dispute", {}).get("entity", {}).get("payment_id")
        log.info("dispute_created", payment_id=payment_id)

    return {"status": "ok", "event": event_type}


# ── Razorpay Remote MCP Server Integration ────────────────────────────────────

@app.get("/api/razorpay/mcp/status")
async def get_razorpay_mcp_status():
    """Verify live connection to Razorpay Remote MCP Server (https://mcp.razorpay.com/mcp)."""
    from src.payment.razorpay_mcp import check_mcp_health
    return await check_mcp_health()


@app.get("/api/razorpay/mcp/tools")
async def get_razorpay_mcp_tools():
    """List all available tools provided by the Razorpay Remote MCP Server."""
    from src.payment.razorpay_mcp import list_mcp_tools
    tools = await list_mcp_tools()
    return {"endpoint": "https://mcp.razorpay.com/mcp", "count": len(tools), "tools": tools}


@app.post("/api/razorpay/mcp/call")
async def call_razorpay_mcp_endpoint(payload: Dict[str, Any]):
    """Execute a tool directly on the Razorpay Remote MCP Server."""
    from src.payment.razorpay_mcp import call_mcp_tool
    tool_name = payload.get("tool_name")
    arguments = payload.get("arguments", {})
    if not tool_name:
        raise HTTPException(400, "tool_name is required")
    return await call_mcp_tool(tool_name, arguments)


# ── Batch Evaluation ──────────────────────────────────────────────────────────

@app.get("/api/evaluate/stream")
@limiter.limit("20/minute")
async def evaluate_stream(
    request: Request,
    scenario: str = Query(default="all", description="A, B, C, or all"),
):
    """Stream evaluation progress as real-time Server-Sent Events with keep-alive pings."""
    import asyncio
    from src.evaluator import run_evaluation

    scenario_filter = None if scenario == "all" else scenario
    queue: asyncio.Queue = asyncio.Queue()

    async def progress_callback(run_id: int, total: int, r: Any):
        data = {
            "type": "run_complete",
            "run_id": r.run_id,
            "total": total,
            "scenario_id": r.scenario_id,
            "category": r.category.value,
            "passed": r.passed,
            "outcome": r.outcome.value,
            "confirmation_gate": r.confirmation_gate_fired,
            "payment_attempts": r.payment_attempts,
            "session_ms": r.session_ms,
        }
        await queue.put(data)

    async def background_runner():
        try:
            eval_result = await run_evaluation(
                scenario_filter=scenario_filter,
                on_progress=progress_callback,
            )

            if eval_result.metrics:
                m = eval_result.metrics
                summary = {
                    "type": "complete",
                    "metrics": {
                        "total_runs": m.total_runs,
                        "end_to_end_success_rate": m.end_to_end_success_rate,
                        "confirmation_gate_hit_rate": m.confirmation_gate_hit_rate,
                        "stopping_rule_compliance": m.stopping_rule_compliance,
                        "audit_trail_completeness": m.audit_trail_completeness,
                        "avg_steps_to_payment": m.avg_steps_to_payment,
                        "avg_session_time_ms": m.avg_session_time_ms,
                        "scenario_breakdown": m.scenario_breakdown,
                        "honest_failures": m.honest_failures,
                    },
                    "output_file": eval_result.output_file,
                }
                await queue.put(summary)
            else:
                await queue.put({"type": "complete", "metrics": None, "output_file": eval_result.output_file})
        except Exception as e:
            log.error("evaluation_error", error=str(e))
            await queue.put({"type": "error", "message": str(e)})
        finally:
            await queue.put(None)  # Sentinel to close generator

    # Start evaluation task in background
    eval_task = asyncio.create_task(background_runner())

    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'scenario': scenario})}\n\n"

        while True:
            try:
                # 5s timeout sends keepalive comments to prevent proxy drops
                item = await asyncio.wait_for(queue.get(), timeout=5.0)
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except asyncio.TimeoutError:
                # SSE keep-alive ping comment (ignored by clients, keeps TCP alive)
                yield ": keep-alive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/evaluate/results")
async def list_eval_results():
    """List saved evaluation result files."""
    import glob
    files = sorted(glob.glob("results/batch_run_*.json"), reverse=True)
    results = []
    for f in files[:10]:
        try:
            with open(f) as fp:
                data = json.load(fp)
            results.append({
                "file": f,
                "run_id": data.get("run_id"),
                "started_at": data.get("started_at"),
                "total_scenarios": data.get("total_scenarios"),
                "metrics": data.get("metrics", {}),
            })
        except Exception:
            pass
    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
