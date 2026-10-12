"""Plan routes — docs/4_API_DESIGN.yaml /plans*."""

from __future__ import annotations

from uuid import UUID

from db.models import PlanStatus
from dependencies import CurrentUser, get_current_user, get_db
from exceptions import NotFoundError
from fastapi import APIRouter, Depends, Query, Response, status
from schemas.http import PlanGenerationRequest, PlanStatusUpdate, SwapPayload
from schemas.plans import PlanGenerationParams
from services.job_service import JobService
from services.plan_service import PlanService
from services.profile_service import ProfileService
from sqlalchemy.ext.asyncio import AsyncSession

from routers.serializers import (
    pagination_meta,
    serialize_generation,
    serialize_job,
    serialize_meal_plan,
    serialize_plan_item,
    serialize_plan_summary,
)

router = APIRouter()
_service = PlanService()
_jobs = JobService()
_current_user = Depends(get_current_user)
_db = Depends(get_db)
_offset = Query(0, ge=0)
_limit = Query(30, ge=1, le=30)
_status_filter = Query(None, alias="status")


@router.get("/plans")
async def list_plans(
    offset: int = _offset,
    limit: int = _limit,
    status_filter: PlanStatus | None = _status_filter,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    plans, total = await _service.list_plans(
        current_user.id,
        db,
        offset=offset,
        limit=limit,
        status=status_filter,
    )
    jobs = await _jobs.latest_for_plans([p.id for p in plans], db)
    return {
        "data": [
            serialize_plan_summary(
                p, generation=serialize_generation(jobs.get(p.id))
            )
            for p in plans
        ],
        "pagination": pagination_meta(total, offset, limit),
    }


@router.post("/plans", status_code=status.HTTP_202_ACCEPTED)
async def generate_plan(
    body: PlanGenerationRequest,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    include_juicing = body.include_juicing
    if "include_juicing" not in body.model_fields_set:
        profile = await ProfileService().get_profile(current_user.id, db)
        include_juicing = profile.juicing_enabled
    params = PlanGenerationParams(
        duration_days=body.num_days,
        diet_type=body.diet_type,
        cooking_type=body.cooking_type,
        calorie_target=body.calorie_target,
        sourcing_policy=body.recipe_usage_policy,
        include_juicing=include_juicing,
        notes=body.notes,
        cloned_from_plan_id=body.cloned_from_plan_id,
        week_start_date=body.week_start_date,
        conversation_id=body.conversation_id,
    )
    _plan, job = await _service.create_plan_stub(current_user.id, params, db)
    return serialize_job(job)


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: UUID,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    plan = await _service.get_plan(plan_id, current_user.id, db)
    days = await _service.get_plan_days(plan_id, current_user.id, db)
    jobs = await _jobs.latest_for_plans([plan.id], db)
    return serialize_meal_plan(
        plan, days, generation=serialize_generation(jobs.get(plan.id))
    )


@router.patch("/plans/{plan_id}")
async def update_plan_status(
    plan_id: UUID,
    body: PlanStatusUpdate,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    plan = await _service.update_plan_status(
        plan_id, current_user.id, body.status, db
    )
    return serialize_plan_summary(plan)


@router.delete(
    "/plans/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_plan(
    plan_id: UUID,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> Response:
    await _service.delete_plan(plan_id, current_user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/plans/{plan_id}/items/{item_id}/swap")
async def swap_plan_item(
    plan_id: UUID,
    item_id: UUID,
    body: SwapPayload,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    if body.recipe_id is None:
        raise NotFoundError("recipe_id is required for swap in v2")
    item = await _service.swap_plan_item(
        plan_id, item_id, current_user.id, body.recipe_id, db
    )
    # day_number for response — load day
    from db.models import PlanDay

    day = await db.get(PlanDay, item.plan_day_id)
    day_number = day.day_number if day is not None else 1
    return serialize_plan_item(item, day_number=day_number, plan_id=plan_id)
