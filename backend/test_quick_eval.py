import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

from src.evaluator import run_evaluation

async def main():
    print("=== RUNNING QUICK VERIFICATION SUITE (3 SCENARIOS) ===")
    # Load 3 test scenarios (one from each category: A, B, C)
    with open("data/test_scenarios.json") as f:
        all_scenarios = json.load(f)

    subset = [s for s in all_scenarios if s["scenario_id"] in ("A_001", "B_001", "C_001")]
    with open("data/quick_scenarios.json", "w") as f:
        json.dump(subset, f)

    async def on_prog(idx, total, res):
        status = "PASSED" if res.passed else "FAILED"
        print(f"[{status}] {idx}/{total}: {res.scenario_id} -> {res.outcome.value} ({res.session_ms}ms)")

    result = await run_evaluation(scenarios_path="data/quick_scenarios.json", on_progress=on_prog)
    m = result.metrics
    print("\n--- RESULTS ---")
    print(f"Pass Rate: {m.pass_rate:.1f}%")
    print(f"Confirmation Gate Hit Rate: {m.confirmation_gate_hit_rate:.1f}%")
    print(f"Stopping Rule Compliance: {m.stopping_rule_compliance:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
