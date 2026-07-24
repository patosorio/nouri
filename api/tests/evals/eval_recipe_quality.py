"""Live AI recipe quality eval — docs/8_TEST_PLAN.md §7. NOT run in CI.

Run manually:
  cd api && pytest tests/evals/eval_recipe_quality.py -m eval
"""

from __future__ import annotations

import pytest


@pytest.mark.eval
def test_eval_recipe_quality_placeholder() -> None:
    """
    Eval goal: generate 5 recipes with live AI; check exclusion compliance
    and NutritionValidator bounds (RISK-06).
    """
    pytest.skip("Live eval — enable after RecipeGeneratorAgent prompts are approved")
