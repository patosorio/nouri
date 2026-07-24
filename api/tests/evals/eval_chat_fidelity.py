"""Live AI chat fidelity eval — docs/8_TEST_PLAN.md §7. NOT run in CI.

Run manually:
  cd api && pytest tests/evals/eval_chat_fidelity.py -m eval
"""

from __future__ import annotations

import pytest


@pytest.mark.eval
def test_eval_chat_fidelity_placeholder() -> None:
    """
    Eval goal: run 3 conversation scenarios; check tool-use correctness
    and FR-2.9 language bounds.
    """
    pytest.skip("Live eval — enable after ChatAgent prompts are approved")
