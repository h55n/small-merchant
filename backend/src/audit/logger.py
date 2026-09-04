"""
Structured audit trail logger for agent sessions.
Every agent decision is logged with input, output, reasoning, and latency.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database import DBAuditEntry, DBSession
from src.models import AuditEntry, BuyerSession, FullAuditTrail, SessionOutcome, SessionOutcomeRecord, StepType

logger = logging.getLogger(__name__)


class SessionAuditLogger:
    """
    Per-session audit logger. Tracks sequence number and persists to DB.
    Also maintains in-memory buffer for streaming to frontend.
    """

    def __init__(self, session_id: str, db: AsyncSession):
        self.session_id = session_id
        self.db = db
        self._sequence = 0
        self._buffer: List[AuditEntry] = []
        self._start_time = time.time()

    async def log(
        self,
        step: StepType,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        reasoning: Optional[str] = None,
        confidence: Optional[float] = None,
        latency_ms: Optional[int] = None,
        model_used: Optional[str] = None,
        error: Optional[str] = None,
    ) -> AuditEntry:
        """Log a single audit entry and persist to database."""
        self._sequence += 1
        entry = AuditEntry(
            session_id=self.session_id,
            sequence=self._sequence,
            step=step,
            input_data=input_data,
            output_data=output_data,
            reasoning=reasoning,
            confidence=confidence,
            latency_ms=latency_ms,
            model_used=model_used,
            error=error,
        )

        # Persist to DB
        try:
            db_entry = DBAuditEntry(
                entry_id=entry.entry_id,
                session_id=entry.session_id,
                timestamp=entry.timestamp,
                sequence=entry.sequence,
                step=entry.step.value,
                input_data=entry.input_data,
                output_data=entry.output_data,
                reasoning=entry.reasoning,
                confidence=entry.confidence,
                latency_ms=entry.latency_ms,
                model_used=entry.model_used,
                error=entry.error,
            )
            self.db.add(db_entry)
            await self.db.commit()
        except Exception as e:
            try:
                await self.db.rollback()
            except Exception:
                pass
            logger.error(f"Failed to persist audit entry: {e}")

        self._buffer.append(entry)
        logger.debug(f"[{self.session_id}] audit #{self._sequence}: {step.value}")
        return entry

    def elapsed_ms(self) -> int:
        """Return milliseconds since session started."""
        return int((time.time() - self._start_time) * 1000)

    @property
    def entries(self) -> List[AuditEntry]:
        return self._buffer.copy()


async def get_session_audit(
    db: AsyncSession,
    session_id: str,
) -> Optional[FullAuditTrail]:
    """Retrieve full audit trail for a session from the database."""
    # Get session
    session_result = await db.execute(
        select(DBSession).where(DBSession.session_id == session_id)
    )
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        return None

    # Get audit entries
    entries_result = await db.execute(
        select(DBAuditEntry)
        .where(DBAuditEntry.session_id == session_id)
        .order_by(DBAuditEntry.sequence)
    )
    db_entries = entries_result.scalars().all()

    entries = []
    for e in db_entries:
        try:
            step = StepType(e.step)
        except ValueError:
            step = StepType.ERROR
        entries.append(AuditEntry(
            entry_id=e.entry_id,
            session_id=e.session_id,
            timestamp=e.timestamp,
            sequence=e.sequence,
            step=step,
            input_data=e.input_data,
            output_data=e.output_data,
            reasoning=e.reasoning,
            confidence=e.confidence,
            latency_ms=e.latency_ms,
            model_used=e.model_used,
            error=e.error,
        ))

    outcome = None
    if db_session.status != "ACTIVE":
        outcome = SessionOutcomeRecord(
            status=SessionOutcome(db_session.status),
            payment_id=db_session.payment_id,
            product_purchased=db_session.product_purchased,
            amount_inr=db_session.amount_inr,
            confirmation_gate_hit=db_session.confirmation_gate_hit,
            payment_attempts=db_session.payment_attempts,
            total_session_ms=db_session.total_session_ms,
            ai_provider_used=db_session.ai_provider_used,
            error_message=db_session.error_message,
        )

    # Get merchant name
    from src.database import DBMerchant
    merchant_result = await db.execute(
        select(DBMerchant).where(DBMerchant.merchant_id == db_session.merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    merchant_name = merchant.merchant_name if merchant else db_session.merchant_id

    return FullAuditTrail(
        session_id=session_id,
        merchant_id=db_session.merchant_id,
        merchant_name=merchant_name,
        started_at=db_session.started_at,
        completed_at=db_session.completed_at,
        purchase_intent=db_session.purchase_intent,
        entries=entries,
        outcome=outcome,
    )


async def get_all_sessions(db: AsyncSession, limit: int = 50) -> List[Dict[str, Any]]:
    """Get summary of recent agent sessions."""
    result = await db.execute(
        select(DBSession).order_by(DBSession.started_at.desc()).limit(limit)
    )
    sessions = result.scalars().all()

    summaries = []
    for s in sessions:
        summaries.append({
            "session_id": s.session_id,
            "merchant_id": s.merchant_id,
            "purchase_intent": s.purchase_intent[:100],
            "status": s.status,
            "payment_attempts": s.payment_attempts,
            "confirmation_gate_hit": s.confirmation_gate_hit,
            "amount_inr": s.amount_inr,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "total_session_ms": s.total_session_ms,
        })
    return summaries
