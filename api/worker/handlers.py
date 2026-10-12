"""Job handlers for the background worker — docs/2_SAD.md §9 / Phase 7."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from agent.plan_generator import PlanGeneratorAgent, plan_system_prompt
from agent.versions import plan_versions
from db.models import JobQueue, NotificationType, Recipe
from exceptions import PlanGenerationFailedError
from schemas.agent import PlanGenerationJob
from schemas.plans import GeneratedPlanData, PlanGenerationParams
from services.job_service import JobService
from services.notification_service import NotificationService
from services.plan_service import PlanService
from services.recipe_service import RecipeService
from sqlalchemy.ext.asyncio import AsyncSession

from worker.agent_to_service import (
    filter_unplaced_generated,
    map_generated_plan,
    placed_recipe_ids,
    remap_reused_recipe_ids,
)
from worker.retry_policy import begin_plan_attempt

logger = structlog.get_logger(__name__)

NUTRITION_JOB_TYPE = "recipe_nutrition_estimation"


async def handle_plan_generation(
    job: JobQueue,
    db: AsyncSession,
    *,
    deadline: float | None = None,
) -> dict[str, Any]:
    job_payload = _build_plan_generation_job(job)
    trace_id = job_payload.trace_id
    days_total = job_payload.duration_days
    jobs = JobService()
    attempt = begin_plan_attempt(job)

    async def on_progress(
        progress_pct: int,
        stage: str,
        days_completed: int,
        days_total_n: int,
    ) -> None:
        await jobs.set_progress(
            job.id,
            progress_pct=progress_pct,
            stage=stage,
            days_completed=days_completed,
            days_total=days_total_n,
        )

    await on_progress(5, "queued", 0, days_total)
    checkpoint_payload: dict[str, Any] = {}

    async def on_model_call_start() -> None:
        attempt.model_call_started = True

    async def on_llm_output(payload: dict[str, Any]) -> None:
        checkpoint_payload.clear()
        payload["versions"] = plan_job_versions(job)
        checkpoint_payload.update(payload)
        await jobs.save_llm_output(job.id, payload)
        attempt.llm_output_saved = True

    saved_llm_output = job.llm_output if isinstance(job.llm_output, dict) else None

    agent = PlanGeneratorAgent()
    try:
        if job.llm_output is not None and saved_llm_output is None:
            raise PlanGenerationFailedError("Saved plan output is invalid")
        agent_plan = await agent.generate(
            job_payload,
            db,
            on_progress=on_progress,
            saved_llm_output=saved_llm_output,
            on_llm_output=on_llm_output,
            on_model_call_start=on_model_call_start,
            deadline=deadline,
            job_id=job.id,
        )
    except PlanGenerationFailedError as exc:
        await db.rollback()
        await _fail_plan(
            job,
            job_payload,
            exc.message,
            db,
            dish_flags=list(agent.dish_flags),
        )
        raise

    try:
        handle_source = checkpoint_payload if checkpoint_payload else (saved_llm_output or {})
        raw_handles = (
            handle_source.get("handles") if isinstance(handle_source, dict) else None
        )
        saved_ids = _saved_ids_from_handles(raw_handles)
        service_plan = filter_unplaced_generated(
            map_generated_plan(agent_plan, saved_ids=saved_ids)
        )
        await PlanService()._assert_recipes_owned(
            job.user_id,
            _without_generated_recipes(service_plan),
            db,
        )
        saved: list[Recipe] = []
        if service_plan.generated_recipes:
            await on_progress(75, "saving", 0, days_total)
            batch = await RecipeService().save_generated_batch(
                job.user_id,
                service_plan.generated_recipes,
                db,
                placed_ids=placed_recipe_ids(service_plan),
            )
            service_plan = remap_reused_recipe_ids(service_plan, batch.id_remap)
            saved = batch.recipes
            from search.recipe_search_service import RecipeSearchService

            search = RecipeSearchService()
            for recipe in batch.inserted:
                try:
                    await search.embed_recipe(recipe, db)
                except Exception as exc:
                    # Plan must still save — embeddings can be backfilled later.
                    logger.exception(
                        "recipe_embed_failed_soft",
                        recipe_id=str(recipe.id),
                        job_id=str(job.id),
                        error=str(exc),
                        trace_id=trace_id,
                    )

        async def on_day_written(day_number: int, total: int) -> None:
            pct = 75 + int((day_number / max(total, 1)) * 20)
            await on_progress(pct, "writing_days", day_number, total)

        plan = await PlanService().write_generated_plan(
            job_payload.plan_id,
            service_plan,
            db,
            on_day_written=on_day_written,
        )
    except PlanGenerationFailedError as exc:
        await db.rollback()
        await _fail_plan(
            job,
            job_payload,
            exc.message,
            db,
            dish_flags=list(agent.dish_flags),
        )
        raise

    result = {
        "plan_id": str(plan.id),
        "status": plan.status.value,
        "recipes_saved": [str(r.id) for r in saved],
        "versions": plan_job_versions(job),
    }
    if agent.dish_flags:
        result["dish_flags"] = list(agent.dish_flags)
    current = getattr(plan, "generation_params", None)
    merged = dict(current) if isinstance(current, dict) else {}
    plan.generation_params = {**merged, "versions": result["versions"]}
    await db.flush()
    await JobService().mark_complete(job.id, result, db)
    await NotificationService().publish(
        job.user_id,
        NotificationType.PLAN_READY.value,
        {
            "job_id": str(job.id),
            "plan_id": str(plan.id),
        },
        db,
        title="Your meal plan is ready",
        body=plan.title or "Your generated meal plan is ready to review.",
    )
    return result


async def handle_recipe_nutrition_estimation(
    job: JobQueue, db: AsyncSession
) -> dict[str, Any]:
    result = {"skipped": "estimator_removed"}
    await JobService().mark_complete(job.id, result, db)
    return result


async def _fail_plan(
    job: JobQueue,
    job_payload: PlanGenerationJob,
    message: str,
    db: AsyncSession,
    *,
    dish_flags: list[str] | None = None,
) -> None:
    versions = plan_job_versions(job)
    result = dict(job.result) if isinstance(getattr(job, "result", None), dict) else {}
    result["versions"] = versions
    if dish_flags:
        result["dish_flags"] = list(dish_flags)
    job.result = result
    await JobService().mark_failed(job.id, message, db)
    await NotificationService().publish(
        job.user_id,
        NotificationType.PLAN_FAILED.value,
        {
            "job_id": str(job.id),
            "plan_id": str(job_payload.plan_id),
            "message": message,
        },
        db,
        title="Plan generation failed",
        body=message,
    )


def plan_job_versions(job: JobQueue) -> dict[str, str]:
    payload = _build_plan_generation_job(job)
    return plan_versions(plan_system_prompt(payload.duration_days, payload.diet_type))


def stamp_plan_versions(job: JobQueue) -> dict[str, str] | None:
    """Write versions onto job.result. Used on success and on failure."""
    from pydantic import ValidationError

    try:
        versions = plan_job_versions(job)
    except (ValidationError, ValueError, TypeError):
        return None
    result = dict(job.result) if isinstance(getattr(job, "result", None), dict) else {}
    result["versions"] = versions
    job.result = result
    return versions


def _without_generated_recipes(plan: GeneratedPlanData) -> GeneratedPlanData:
    """Drop recipes this job is about to insert so ownership sees saved ids only."""
    generated_ids = {
        draft.id for draft in plan.generated_recipes if draft.id is not None
    }
    days = []
    for day in plan.days:
        items = [
            item
            for item in day.items
            if item.recipe_id is not None and item.recipe_id not in generated_ids
        ]
        days.append(day.model_copy(update={"items": items}))
    return plan.model_copy(update={"days": days})


def _saved_ids_from_handles(raw_handles: object) -> set[UUID]:
    if not isinstance(raw_handles, dict):
        return set()
    ids: set[UUID] = set()
    for value in raw_handles.values():
        if isinstance(value, UUID):
            ids.add(value)
            continue
        ids.add(UUID(str(value)))
    return ids


def _build_plan_generation_job(job: JobQueue) -> PlanGenerationJob:
    payload = dict(job.payload or {})
    raw_params = payload.get("params") or {}
    if not isinstance(raw_params, dict):
        raw_params = {}
    params = PlanGenerationParams.model_validate(raw_params)

    plan_id = job.plan_id
    if plan_id is None:
        plan_id = UUID(str(payload["plan_id"]))

    trace_id = payload.get("trace_id")
    if not isinstance(trace_id, str):
        trace_id = None

    return PlanGenerationJob(
        user_id=job.user_id,
        plan_id=plan_id,
        duration_days=params.duration_days,
        diet_type=params.diet_type,
        cooking_type=params.cooking_type,
        calorie_target=params.calorie_target,
        sourcing_policy=params.sourcing_policy,
        include_juicing=(
            params.include_juicing if params.include_juicing is not None else False
        ),
        notes=params.notes,
        trace_id=trace_id,
    )
