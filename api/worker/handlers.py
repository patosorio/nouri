"""Job handlers for the background worker — docs/2_SAD.md §9 / Phase 7."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.nutrition_estimator import NutritionEstimatorAgent
from agent.plan_generator import PlanGeneratorAgent
from db.models import JobQueue, NotificationType, Recipe, RecipeNutrition
from exceptions import PlanGenerationFailedError
from schemas.agent import PlanGenerationJob
from schemas.plans import PlanGenerationParams
from services.job_service import JobService
from services.notification_service import NotificationService
from services.plan_service import PlanService
from services.recipe_service import RecipeService
from worker.agent_to_service import map_generated_plan

logger = structlog.get_logger(__name__)

# Existing enqueue uses generate_plan (SAD/ERD); Phase 7 prompt uses plan_generation.
PLAN_JOB_TYPES = frozenset({"plan_generation", "generate_plan"})
NUTRITION_JOB_TYPE = "recipe_nutrition_estimation"
NUTRITION_ESTIMATED_TAG = "RECIPE_NUTRITION_ESTIMATED"


async def handle_plan_generation(job: JobQueue, db: AsyncSession) -> dict[str, Any]:
    job_payload = _build_plan_generation_job(job)
    trace_id = job_payload.trace_id

    try:
        agent_plan = await PlanGeneratorAgent().generate(job_payload, db)
    except PlanGenerationFailedError as exc:
        await JobService().mark_failed(job.id, exc.message, db)
        await NotificationService().publish(
            job.user_id,
            NotificationType.PLAN_FAILED.value,
            {
                "job_id": str(job.id),
                "plan_id": str(job_payload.plan_id),
                "message": exc.message,
            },
            db,
            title="Plan generation failed",
            body=exc.message,
        )
        raise

    service_plan = map_generated_plan(agent_plan)
    saved: list[Recipe] = []
    if service_plan.generated_recipes:
        saved = await RecipeService().save_generated_batch(
            job.user_id, service_plan.generated_recipes, db
        )
        from search.recipe_search_service import RecipeSearchService

        search = RecipeSearchService()
        for recipe in saved:
            await search.embed_recipe(recipe, db)

    plan = await PlanService().write_generated_plan(
        job_payload.plan_id, service_plan, db
    )

    missing_nutrition_ids = await _recipe_ids_missing_nutrition(
        [r.id for r in saved], db
    )
    if missing_nutrition_ids:
        await JobService().enqueue(
            NUTRITION_JOB_TYPE,
            job.user_id,
            {
                "recipe_ids": [str(rid) for rid in missing_nutrition_ids],
                "trace_id": trace_id,
            },
            db,
        )

    result = {
        "plan_id": str(plan.id),
        "status": plan.status.value,
        "recipes_saved": [str(r.id) for r in saved],
    }
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
    payload = dict(job.payload or {})
    raw_ids = payload.get("recipe_ids") or []
    trace_id = payload.get("trace_id")
    if isinstance(trace_id, str) is False:
        trace_id = None

    recipe_ids = [UUID(str(rid)) for rid in raw_ids]
    estimator = NutritionEstimatorAgent()
    recipe_service = RecipeService()
    estimated: list[str] = []
    skipped: list[str] = []

    for recipe_id in recipe_ids:
        existing = await db.get(RecipeNutrition, recipe_id)
        if existing is not None:
            skipped.append(str(recipe_id))
            continue

        recipe = await db.get(Recipe, recipe_id)
        if recipe is None or recipe.user_id != job.user_id:
            logger.warning(
                "nutrition_job_recipe_missing",
                recipe_id=str(recipe_id),
                job_id=str(job.id),
                trace_id=trace_id,
            )
            skipped.append(str(recipe_id))
            continue

        draft = await estimator.estimate(recipe, db, trace_id=trace_id)
        await recipe_service.upsert_nutrition(recipe.id, draft, db)

        tags = list(recipe.tags or [])
        if NUTRITION_ESTIMATED_TAG not in tags:
            tags.append(NUTRITION_ESTIMATED_TAG)
            recipe.tags = tags

        estimated.append(str(recipe.id))
        logger.info(
            "recipe_nutrition_estimated",
            recipe_id=str(recipe.id),
            job_id=str(job.id),
            trace_id=trace_id,
        )

    result = {"estimated": estimated, "skipped": skipped}
    await JobService().mark_complete(job.id, result, db)
    return result


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
        include_juicing=params.include_juicing,
        notes=params.notes,
        trace_id=trace_id,
    )


async def _recipe_ids_missing_nutrition(
    recipe_ids: list[UUID], db: AsyncSession
) -> list[UUID]:
    missing: list[UUID] = []
    for recipe_id in recipe_ids:
        row = await db.get(RecipeNutrition, recipe_id)
        if row is None:
            missing.append(recipe_id)
    return missing
