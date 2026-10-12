"""Live AI plan quality eval — docs/8_TEST_PLAN.md §7. NOT run in CI.

Run manually:
  cd api && pytest tests/evals/eval_plan_quality.py -m eval
"""

from __future__ import annotations

import pytest


@pytest.mark.eval
def test_eval_plan_quality_placeholder() -> None:
    """
    Eval goal (docs/8_TEST_PLAN.md): generate a 7-day plan with live AI,
    score with LLM-as-judge on coherence, exclusion compliance, and macros.

    Blocked on agent prompt approval for PlanGeneratorAgent.
    """
    pytest.skip(
        "Live Anthropic eval — deterministic assigner gold lives in "
        "tests/unit/test_gold_assigner.py (8 profiles in tests/evals/gold/profiles.jsonl)"
    )
