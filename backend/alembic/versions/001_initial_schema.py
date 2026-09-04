"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2026-09-04 00:00:00.000000

Creates all five core tables:
  - merchants
  - products
  - agent_sessions
  - audit_entries
  - evaluations
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── merchants ──────────────────────────────────────────────────────────────
    op.create_table(
        "merchants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("merchant_id", sa.String(length=50), nullable=False),
        sa.Column("merchant_name", sa.String(length=200), nullable=False),
        sa.Column("catalog_version", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("onboarding_source", sa.String(length=50), nullable=True),
        sa.Column("agent_permissions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_merchants_id"), "merchants", ["id"], unique=False)
    op.create_index(
        op.f("ix_merchants_merchant_id"), "merchants", ["merchant_id"], unique=True
    )

    # ── products ──────────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(length=50), nullable=False),
        sa.Column("merchant_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_inr", sa.Float(), nullable=False),
        sa.Column("availability", sa.Boolean(), nullable=True),
        sa.Column("stock_count", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("payment_constraints", sa.JSON(), nullable=True),
        sa.Column("return_policy_days", sa.Integer(), nullable=True),
        sa.Column("shipping_options", sa.JSON(), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("source_format", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.merchant_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_id"), "products", ["id"], unique=False)
    op.create_index(
        op.f("ix_products_merchant_id"), "products", ["merchant_id"], unique=False
    )
    op.create_index(
        op.f("ix_products_product_id"), "products", ["product_id"], unique=True
    )
    op.create_index(
        "ix_products_merchant_availability",
        "products",
        ["merchant_id", "availability"],
        unique=False,
    )

    # ── agent_sessions ────────────────────────────────────────────────────────
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=50), nullable=False),
        sa.Column("merchant_id", sa.String(length=50), nullable=False),
        sa.Column("purchase_intent", sa.Text(), nullable=False),
        sa.Column("spending_limit_inr", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("payment_attempts", sa.Integer(), nullable=True),
        sa.Column("confirmation_gate_hit", sa.Boolean(), nullable=True),
        sa.Column("payment_id", sa.String(length=100), nullable=True),
        sa.Column("product_purchased", sa.String(length=50), nullable=True),
        sa.Column("amount_inr", sa.Float(), nullable=True),
        sa.Column("ai_provider_used", sa.String(length=50), nullable=True),
        sa.Column("total_session_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.merchant_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_sessions_id"), "agent_sessions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_agent_sessions_session_id"),
        "agent_sessions",
        ["session_id"],
        unique=True,
    )

    # ── audit_entries ─────────────────────────────────────────────────────────
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.String(length=50), nullable=False),
        sa.Column("session_id", sa.String(length=50), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step", sa.String(length=50), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_audit_entries_id"), "audit_entries", ["id"], unique=False
    )
    op.create_index(
        "ix_audit_session_seq",
        "audit_entries",
        ["session_id", "sequence"],
        unique=False,
    )

    # ── evaluations ───────────────────────────────────────────────────────────
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("total_scenarios", sa.Integer(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("output_file", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evaluations_id"), "evaluations", ["id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluations_id"), table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index("ix_audit_session_seq", table_name="audit_entries")
    op.drop_index(op.f("ix_audit_entries_id"), table_name="audit_entries")
    op.drop_table("audit_entries")
    op.drop_index(op.f("ix_agent_sessions_session_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_id"), table_name="agent_sessions")
    op.drop_table("agent_sessions")
    op.drop_index("ix_products_merchant_availability", table_name="products")
    op.drop_index(op.f("ix_products_product_id"), table_name="products")
    op.drop_index(op.f("ix_products_merchant_id"), table_name="products")
    op.drop_index(op.f("ix_products_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_merchants_merchant_id"), table_name="merchants")
    op.drop_index(op.f("ix_merchants_id"), table_name="merchants")
    op.drop_table("merchants")
