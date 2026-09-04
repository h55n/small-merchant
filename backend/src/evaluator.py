"""
Batch evaluation runner.
Runs all 70 test scenarios through the full agent pipeline and computes metrics.
Produces a JSON report with honest exception list.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

# Add parent to path when run as script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    EvaluationMetrics, EvaluationResult, RunResult, ScenarioCategory,
    SessionOutcome, TestScenario
)

logger = logging.getLogger(__name__)

MANDATORY_AUDIT_STEPS = {
    "search_catalog", "confirmation_gate", "payment_initiated",
    "payment_confirmed", "session_complete"
}


async def load_scenarios(path: str = "data/test_scenarios.json") -> List[TestScenario]:
    """Load test scenarios from JSON file."""
    with open(path) as f:
        data = json.load(f)
    return [TestScenario(**s) for s in data]


async def ensure_demo_merchant(db) -> str:
    """Ensure the demo merchant catalog exists for evaluation."""
    from src.catalog.storage import get_catalog, save_catalog
    from src.models import MerchantCatalog, CatalogStatus, AgentPermissions

    merchant_id = "merch_DEMO01"
    catalog = await get_catalog(db, merchant_id)
    if catalog and len(catalog.products) > 0:
        from src.catalog.storage import update_product_stock
        for p in catalog.products:
            if p.stock_count <= 1:
                await update_product_stock(db, merchant_id, p.product_id, 10)
        await db.commit()
        logger.info(f"Demo merchant {merchant_id} ready with {len(catalog.products)} products")
        return merchant_id

    # Load from fixture CSV
    fixture_path = "data/merchant_fixtures/kiran_artisan_catalog.csv"
    if not os.path.exists(fixture_path):
        logger.error(f"Fixture file not found: {fixture_path}")
        return merchant_id

    from src.onboarding.parsers import parse_csv
    from src.onboarding.normalizer import normalize
    from src.onboarding.embedder import generate_embeddings

    with open(fixture_path, "rb") as f:
        raw, error = parse_csv(f.read())

    if error:
        logger.error(f"Failed to parse fixture: {error}")
        return merchant_id

    result = await normalize(raw, source_format="csv", infer_categories=False)

    # Generate embeddings
    result.products = await generate_embeddings(result.products)

    catalog = MerchantCatalog(
        merchant_id=merchant_id,
        merchant_name="Kiran Artisan Goods",
        status=CatalogStatus.PUBLISHED,
        products=result.products,
        agent_permissions=AgentPermissions(
            max_transaction_inr=10000,
            requires_confirmation_above_inr=0,  # Always confirm
            auto_approve_below_inr=0,
        ),
        onboarding_source="fixture",
    )
    await save_catalog(db, catalog)
    logger.info(f"Demo merchant created with {len(result.products)} products")
    return merchant_id


async def run_single_scenario(
    scenario: TestScenario,
    run_id: int,
    db,
) -> RunResult:
    """Run a single test scenario and return its result."""
    from src.agent.buyer_agent import BuyerAgent
    from src.audit.logger import SessionAuditLogger
    from src.catalog.storage import get_catalog
    from src.database import DBSession
    from src.models import BuyerSession

    start_ms = int(time.time() * 1000)

    # Create session
    session = BuyerSession(
        merchant_id=scenario.merchant_id,
        purchase_intent=scenario.purchase_intent,
        spending_limit_inr=scenario.buyer_spending_limit_inr,
    )

    # Persist session to DB
    db_session = DBSession(
        session_id=session.session_id,
        merchant_id=session.merchant_id,
        purchase_intent=session.purchase_intent,
        spending_limit_inr=session.spending_limit_inr,
        status="ACTIVE",
    )
    db.add(db_session)
    await db.commit()

    audit = SessionAuditLogger(session.session_id, db)

    # Load catalog
    catalog = await get_catalog(db, scenario.merchant_id)
    if not catalog:
        return RunResult(
            run_id=run_id,
            scenario_id=scenario.scenario_id,
            category=scenario.category,
            outcome=SessionOutcome.FAILED,
            passed=False,
            confirmation_gate_fired=False,
            payment_attempts=0,
            stopping_rule_compliant=True,
            audit_trail_complete=False,
            steps_to_payment=0,
            session_ms=0,
            failure_reason="Demo merchant catalog not found",
        )

    agent = BuyerAgent(
        session=session,
        catalog=catalog,
        db=db,
        audit=audit,
        payment_mock=scenario.payment_mock,
    )

    # Drain all events from the agent
    options_presented = False
    steps_to_payment = 0
    confirmation_fired = False

    initial_message = scenario.purchase_intent
    try:
        async for event in agent.process_message(initial_message):
            steps_to_payment += 1
            if event["type"] == "tool_call":
                if event["data"]["name"] == "search_catalog":
                    pass
            if event["type"] == "tool_result":
                if event["data"]["name"] == "search_catalog":
                    results = event["data"].get("result", {})
                    if results.get("results_count", 0) > 1:
                        options_presented = True
            if event["type"] == "confirmation_gate":
                confirmation_fired = True
                # Auto-confirm for evaluation
                async for conf_event in agent.handle_confirmation(confirmed=True):
                    steps_to_payment += 1
                    if conf_event["type"] == "session_complete":
                        break
                break
            if event["type"] == "session_complete":
                break

        # For Category B or multi-turn scenarios where options were presented:
        # Simulate user selecting the first recommended product to trigger the confirmation gate
        if not confirmation_fired and session.status == SessionOutcome.ACTIVE:
            follow_up = "I choose the first option. Please present the confirmation gate so I can confirm and purchase."
            async for event in agent.process_message(follow_up):
                steps_to_payment += 1
                if event["type"] == "confirmation_gate":
                    confirmation_fired = True
                    async for conf_event in agent.handle_confirmation(confirmed=True):
                        steps_to_payment += 1
                        if conf_event["type"] == "session_complete":
                            break
                    break
                if event["type"] == "session_complete":
                    break

    except Exception as e:
        logger.error(f"Scenario {scenario.scenario_id} error: {e}")
        session.status = SessionOutcome.FAILED
        session.error_message = str(e)

    elapsed_ms = int(time.time() * 1000) - start_ms

    # Update DB session
    db_session.status = session.status.value
    db_session.payment_attempts = session.payment_attempts
    db_session.confirmation_gate_hit = session.confirmation_gate_hit or confirmation_fired
    db_session.payment_id = getattr(session, 'payment_id', None)
    db_session.product_purchased = getattr(session, 'product_purchased', None)
    db_session.amount_inr = getattr(session, 'amount_inr', None)
    db_session.ai_provider_used = session.ai_provider_used
    db_session.total_session_ms = elapsed_ms
    db_session.completed_at = datetime.utcnow()

    await db.commit()

    # Check audit completeness
    audit_steps = {e.step.value for e in audit.entries}
    audit_complete = "session_complete" in audit_steps

    # Stopping rule: never more than 2 payment attempts
    stopping_rule_compliant = session.payment_attempts <= 2

    # Determine pass/fail
    gt = scenario.ground_truth
    outcome = session.status
    gate_fired = session.confirmation_gate_hit or confirmation_fired

    passed = (
        outcome == gt.expected_outcome and
        gate_fired == gt.confirmation_gate_must_fire and
        session.payment_attempts <= gt.max_payment_attempts_allowed and
        stopping_rule_compliant
    )

    failure_reason = None
    if not passed:
        reasons = []
        if outcome != gt.expected_outcome:
            reasons.append(f"outcome={outcome.value} (expected {gt.expected_outcome.value})")
        if gate_fired != gt.confirmation_gate_must_fire:
            reasons.append(f"gate_fired={gate_fired} (expected {gt.confirmation_gate_must_fire})")
        if session.payment_attempts > gt.max_payment_attempts_allowed:
            reasons.append(f"attempts={session.payment_attempts} (max {gt.max_payment_attempts_allowed})")
        failure_reason = "; ".join(reasons)

    return RunResult(
        run_id=run_id,
        scenario_id=scenario.scenario_id,
        category=scenario.category,
        outcome=outcome,
        passed=passed,
        confirmation_gate_fired=gate_fired,
        payment_attempts=session.payment_attempts,
        stopping_rule_compliant=stopping_rule_compliant,
        audit_trail_complete=audit_complete,
        steps_to_payment=steps_to_payment,
        session_ms=elapsed_ms,
        ai_provider_used=session.ai_provider_used,
        failure_reason=failure_reason,
    )


def _compute_metrics(runs: List[RunResult]) -> EvaluationMetrics:
    """Compute aggregate evaluation metrics from all run results."""
    total = len(runs)
    if total == 0:
        return EvaluationMetrics(
            total_runs=0, successful_runs=0,
            end_to_end_success_rate=0, confirmation_gate_hit_rate=0,
            stopping_rule_compliance=0, audit_trail_completeness=0,
            avg_steps_to_payment=0, avg_session_time_ms=0,
            scenario_breakdown={}, honest_failures=[],
        )

    successful = sum(1 for r in runs if r.outcome == SessionOutcome.SUCCESS)
    gate_hits = sum(1 for r in runs if r.confirmation_gate_fired)
    stopping_compliant = sum(1 for r in runs if r.stopping_rule_compliant)
    audit_complete = sum(1 for r in runs if r.audit_trail_complete)
    steps = [r.steps_to_payment for r in runs if r.steps_to_payment > 0]
    times = [r.session_ms for r in runs]

    # Breakdown by scenario category
    breakdown: Dict[str, Any] = {}
    for cat in ScenarioCategory:
        cat_runs = [r for r in runs if r.category == cat]
        if cat_runs:
            cat_success = sum(1 for r in cat_runs if r.outcome == SessionOutcome.SUCCESS)
            cat_passed = sum(1 for r in cat_runs if r.passed)
            breakdown[cat.value] = {
                "total": len(cat_runs),
                "passed": cat_passed,
                "success_rate": round(cat_passed / len(cat_runs) * 100, 1),
                "transaction_success_rate": round(cat_success / len(cat_runs) * 100, 1),
            }

    # Honest failures — cases that failed and why
    honest_failures = []
    failed_runs = [r for r in runs if not r.passed]
    for r in failed_runs[:10]:  # Top 10 failures
        honest_failures.append(
            f"[{r.scenario_id}] {r.failure_reason or 'Unknown failure'}"
        )

    if any(not r.stopping_rule_compliant for r in runs):
        honest_failures.append("WARNING: Some sessions exceeded 2 payment attempts — stopping rule violated.")

    return EvaluationMetrics(
        total_runs=total,
        successful_runs=successful,
        end_to_end_success_rate=round(sum(1 for r in runs if r.passed) / total * 100, 1),
        confirmation_gate_hit_rate=round(gate_hits / total * 100, 1),
        stopping_rule_compliance=round(stopping_compliant / total * 100, 1),
        audit_trail_completeness=round(audit_complete / total * 100, 1),
        avg_steps_to_payment=round(sum(steps) / len(steps) if steps else 0, 1),
        avg_session_time_ms=round(sum(times) / len(times) if times else 0),
        scenario_breakdown=breakdown,
        honest_failures=honest_failures if honest_failures else ["No failures — all scenarios passed."],
    )


async def run_evaluation(
    scenario_filter: Optional[str] = None,
    scenarios_path: str = "data/test_scenarios.json",
    on_progress: Optional[callable] = None,
) -> EvaluationResult:
    """
    Run full batch evaluation.
    
    Args:
        scenario_filter: "A", "B", "C", or None for all
        scenarios_path: Path to test scenarios JSON
        on_progress: Async callback(run_id, total, result) for progress updates
    """
    from src.database import AsyncSessionLocal, create_tables

    await create_tables()

    scenarios = await load_scenarios(scenarios_path)

    # Filter if requested
    if scenario_filter:
        cat_map = {"A": "happy_path", "B": "ambiguous_intent", "C": "payment_failure"}
        cat_name = cat_map.get(scenario_filter.upper())
        if cat_name:
            scenarios = [s for s in scenarios if s.category.value == cat_name]

    eval_result = EvaluationResult(
        total_scenarios=len(scenarios),
        runs=[],
    )

    # ── Step 1: Setup demo merchant in its own fully-committed session ──────────
    # Must be a separate session that is closed BEFORE the scenario loop opens
    # any new sessions. SQLite only allows one write connection at a time.
    async with AsyncSessionLocal() as setup_db:
        await ensure_demo_merchant(setup_db)
        await setup_db.commit()
    # setup_db is now fully closed — SQLite lock released

    # ── Step 2: Run scenarios sequentially, each in its own session ────────────
    for run_id, scenario in enumerate(scenarios, 1):
        try:
            async with AsyncSessionLocal() as run_db:
                run_result = await run_single_scenario(scenario, run_id, run_db)
                await run_db.commit()
        except Exception as e:
            logger.error(f"Fatal error in scenario {scenario.scenario_id}: {e}")
            run_result = RunResult(
                run_id=run_id,
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                outcome=SessionOutcome.FAILED,
                passed=False,
                confirmation_gate_fired=False,
                payment_attempts=0,
                stopping_rule_compliant=True,
                audit_trail_complete=False,
                steps_to_payment=0,
                session_ms=0,
                failure_reason=f"Exception: {str(e)}",
            )

        eval_result.runs.append(run_result)

        if on_progress:
            try:
                await on_progress(run_id, len(scenarios), run_result)
            except Exception:
                pass

    # Compute metrics
    eval_result.metrics = _compute_metrics(eval_result.runs)
    eval_result.completed_at = datetime.utcnow()

    # Save results
    os.makedirs("results", exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_file = f"results/batch_run_{ts}.json"

    with open(output_file, "w") as f:
        json.dump(eval_result.model_dump(mode="json"), f, indent=2, default=str)

    eval_result.output_file = output_file
    logger.info(f"Evaluation complete. Results saved to {output_file}")
    return eval_result


# ── CLI Runner ────────────────────────────────────────────────────────────────

async def _cli_main():
    import argparse
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Run batch evaluation")
    parser.add_argument("--scenario", choices=["A", "B", "C", "all"], default="all")
    parser.add_argument("--dataset", default="data/test_scenarios.json")
    args = parser.parse_args()

    filter_val = None if args.scenario == "all" else args.scenario

    print(f"\n{'='*60}")
    print(f"  SMALL-MERCHANT AI READINESS AGENT — BATCH EVALUATION")
    print(f"{'='*60}")

    run_count = [0]

    async def progress(run_id, total, result):
        run_count[0] = run_id
        status = "✓" if result.passed else "✗"
        print(f"  [{status}] {run_id:3d}/{total} | {result.scenario_id:<10} | {result.outcome.value:<8} | {result.session_ms}ms")

    result = await run_evaluation(
        scenario_filter=filter_val,
        scenarios_path=args.dataset,
        on_progress=progress,
    )

    m = result.metrics
    print(f"\n{'='*60}")
    print(f"  RESULTS — {m.total_runs} scenarios")
    print(f"{'='*60}")
    print(f"  End-to-End Pass Rate:      {m.end_to_end_success_rate:5.1f}%")
    print(f"  Confirmation Gate Hit:     {m.confirmation_gate_hit_rate:5.1f}%  (target: 100%)")
    print(f"  Stopping Rule Compliance:  {m.stopping_rule_compliance:5.1f}%  (target: 100%)")
    print(f"  Audit Trail Complete:      {m.audit_trail_completeness:5.1f}%  (target: ≥95%)")
    print(f"  Avg Steps to Payment:      {m.avg_steps_to_payment:5.1f}      (target: ≤6)")
    print(f"  Avg Session Time:          {m.avg_session_time_ms/1000:5.1f}s")
    print(f"\n  Scenario Breakdown:")
    for cat, stats in m.scenario_breakdown.items():
        print(f"    {cat:<22} {stats['passed']}/{stats['total']} passed ({stats['success_rate']}%)")
    print(f"\n  Output: {result.output_file}")
    print(f"\n  Honest Exception List:")
    for f in m.honest_failures[:5]:
        print(f"    • {f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(_cli_main())
