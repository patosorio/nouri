"""Calendar routes — docs/4_API_DESIGN.yaml /calendar*."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import CurrentUser, get_current_user, get_db
from schemas.http import CalendarAssignPayload
from services.calendar_service import CalendarService

router = APIRouter()
_service = CalendarService()


@router.get("/calendar")
async def list_calendar_weeks(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    weeks = await _service.list_weeks(
        current_user.id, db, from_date=from_date, to_date=to_date
    )
    return {"data": weeks}


@router.get("/calendar/{week_start_date}")
async def get_calendar_week(
    week_start_date: date,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return await _service.get_week(current_user.id, week_start_date, db)


@router.put("/calendar/{week_start_date}")
async def assign_plan_to_week(
    week_start_date: date,
    body: CalendarAssignPayload,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return await _service.assign_plan(
        current_user.id, week_start_date, body.plan_id, db
    )


@router.delete(
    "/calendar/{week_start_date}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def unassign_plan_from_week(
    week_start_date: date,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _service.unassign_week(current_user.id, week_start_date, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
