"""
Database setup and models using SQLAlchemy async.
SQLite for development — easily switchable to PostgreSQL via DATABASE_URL.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, Integer, String, Text,
    ForeignKey, Index, event,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

# Determine database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
# Convert sync SQLite URL to async
if DATABASE_URL.startswith("sqlite:///"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
elif DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
else:
    ASYNC_DATABASE_URL = DATABASE_URL

_is_pg = "postgresql" in ASYNC_DATABASE_URL
from sqlalchemy.pool import NullPool

_connect_args = {"check_same_thread": False, "timeout": 60} if "sqlite" in ASYNC_DATABASE_URL else {}
_pool_kwargs: dict = (
    {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}
    if _is_pg
    else {"poolclass": NullPool}
)

engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=os.getenv("LOG_LEVEL", "INFO") == "DEBUG",
    connect_args=_connect_args,
    **_pool_kwargs,
)

# Enable WAL mode for SQLite — allows concurrent reads + one writer
# This eliminates "database is locked" errors during evaluator parallel runs
if "sqlite" in ASYNC_DATABASE_URL:
    from sqlalchemy import event as sa_event, text

    @sa_event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")  # 60 seconds
        cursor.execute("PRAGMA synchronous=NORMAL")   # Faster writes, still safe
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


# ── ORM Models ────────────────────────────────────────────────────────────────

class DBMerchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(String(50), unique=True, index=True, nullable=False)
    merchant_name = Column(String(200), nullable=False)
    catalog_version = Column(String(20), default="v1.0")
    status = Column(String(20), default="DRAFT")
    onboarding_source = Column(String(50), default="form")
    agent_permissions = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    products = relationship("DBProduct", back_populates="merchant", cascade="all, delete-orphan")
    sessions = relationship("DBSession", back_populates="merchant")


class DBProduct(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(50), unique=True, index=True, nullable=False)
    merchant_id = Column(String(50), ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    price_inr = Column(Float, nullable=False)
    availability = Column(Boolean, default=True)
    stock_count = Column(Integer, default=0)
    category = Column(String(100), default="Other")
    payment_constraints = Column(JSON, default=dict)
    return_policy_days = Column(Integer, default=0)
    shipping_options = Column(JSON, default=list)
    embedding = Column(JSON, nullable=True)  # Stored as list[float]
    source_format = Column(String(50), default="form")
    created_at = Column(DateTime, default=datetime.utcnow)

    merchant = relationship("DBMerchant", back_populates="products")

    __table_args__ = (
        Index("ix_products_merchant_availability", "merchant_id", "availability"),
    )


class DBSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(50), unique=True, index=True, nullable=False)
    merchant_id = Column(String(50), ForeignKey("merchants.merchant_id"), nullable=False)
    purchase_intent = Column(Text, nullable=False)
    spending_limit_inr = Column(Float, default=2000.0)
    status = Column(String(20), default="ACTIVE")
    payment_attempts = Column(Integer, default=0)
    confirmation_gate_hit = Column(Boolean, default=False)
    payment_id = Column(String(100), nullable=True)
    product_purchased = Column(String(50), nullable=True)
    amount_inr = Column(Float, nullable=True)
    ai_provider_used = Column(String(50), nullable=True)
    total_session_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    merchant = relationship("DBMerchant", back_populates="sessions")
    audit_entries = relationship("DBAuditEntry", back_populates="session", cascade="all, delete-orphan", order_by="DBAuditEntry.sequence")


class DBAuditEntry(Base):
    __tablename__ = "audit_entries"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(String(50), unique=True, nullable=False)
    session_id = Column(String(50), ForeignKey("agent_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sequence = Column(Integer, nullable=False)
    step = Column(String(50), nullable=False)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    reasoning = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    model_used = Column(String(100), nullable=True)
    error = Column(Text, nullable=True)

    session = relationship("DBSession", back_populates="audit_entries")

    __table_args__ = (
        Index("ix_audit_session_seq", "session_id", "sequence"),
    )


class DBEvaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(50), unique=True, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    total_scenarios = Column(Integer, default=0)
    metrics = Column(JSON, nullable=True)
    output_file = Column(String(200), nullable=True)
    status = Column(String(20), default="RUNNING")


# ── Database Lifecycle ─────────────────────────────────────────────────────────

async def create_tables():
    """Create all tables if they don't exist."""
    import os
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    os.makedirs("results", exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
