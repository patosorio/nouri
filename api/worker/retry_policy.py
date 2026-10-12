"""Which job failures may be requeued. Plan generation fails closed once a model call starts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from exceptions import LlmDeadlineError, PlanGenerationFailedError, SpendLimitExceeded
from jobs.types import PLAN_JOB_TYPES

__all__ = ["PLAN_JOB_TYPES", "PlanAttemptState", "begin_plan_attempt", "failure_should_retry"]


@dataclass
class PlanAttemptState:
    model_call_started: bool = False
    llm_output_saved: bool = False


def begin_plan_attempt(job: Any) -> PlanAttemptState:
    saved = getattr(job, "llm_output", None) is not None
    state = PlanAttemptState(llm_output_saved=saved)
    job.plan_attempt_state = state
    return state


def failure_should_retry(
    job: Any,
    *,
    timed_out: bool,
    exc: BaseException | None,
) -> bool:
    """True when mark_failed may requeue. Non-plan jobs keep the previous retry behavior."""
    if getattr(job, "job_type", None) not in PLAN_JOB_TYPES:
        return True
    if timed_out or _llm_output_saved(job) or _model_call_started(job):
        return False
    return not isinstance(
        exc, (PlanGenerationFailedError, SpendLimitExceeded, LlmDeadlineError)
    )


def _llm_output_saved(job: Any) -> bool:
    if getattr(job, "llm_output", None) is not None:
        return True
    state = getattr(job, "plan_attempt_state", None)
    return isinstance(state, PlanAttemptState) and state.llm_output_saved


def _model_call_started(job: Any) -> bool:
    state = getattr(job, "plan_attempt_state", None)
    return isinstance(state, PlanAttemptState) and state.model_call_started
