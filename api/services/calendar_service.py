"""CalendarService — week views derived from meal_plans (no calendar_assignments table)."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MealPlan, PlanDay, PlanItem, PlanStatus
from exceptions import NotFoundError, OwnershipError
from services._helpers import get_profile_or_404
from services.plan_service import PlanService


def _monday_on_or_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _enum(value: object) -> object:
    return value.value if hasattr(value, "value") else value


def _num(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


class CalendarService:
    async def list_weeks(
        self,
        user_id: UUID,
        db: AsyncSession,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[dict[str, object]]:
        await get_profile_or_404(user_id, db)
        start = _monday_on_or_before(from_date or date.today())
        end = to_date or (start + timedelta(weeks=12) - timedelta(days=1))
        if end < start:
            raise NotFoundError("Invalid calendar range")

        result = await db.execute(
            select(MealPlan).where(
                MealPlan.user_id == user_id,
                MealPlan.status == PlanStatus.APPROVED,
                MealPlan.scheduled_date.is_not(None),
                MealPlan.scheduled_date >= start,
                MealPlan.scheduled_date <= end,
            )
        )
        plans = list(result.scalars().all())
        by_week: dict[date, MealPlan] = {}
        for plan in plans:
            if plan.scheduled_date is not None:
                week = _monday_on_or_before(plan.scheduled_date)
                by_week[week] = plan

        weeks: list[dict[str, object]] = []
        cursor = start
        while cursor <= end:
            plan = by_week.get(cursor)
            weeks.append(await self._week_payload(cursor, plan, db))
            cursor += timedelta(weeks=1)
        return weeks

    async def get_week(
        self, user_id: UUID, week_start_date: date, db: AsyncSession
    ) -> dict[str, object]:
        await get_profile_or_404(user_id, db)
        week = _monday_on_or_before(week_start_date)
        plan = await self._plan_for_week(user_id, week, db)
        return await self._week_payload(week, plan, db)

    async def assign_plan(
        self,
        user_id: UUID,
        week_start_date: date,
        plan_id: UUID,
        db: AsyncSession,
    ) -> dict[str, object]:
        week = _monday_on_or_before(week_start_date)
        plan = await PlanService().get_plan(plan_id, user_id, db)
        if plan.status != PlanStatus.APPROVED:
            raise OwnershipError("Only approved plans can be assigned to the calendar")

        # Clear any existing assignment for this week
        existing = await db.execute(
            select(MealPlan).where(
                MealPlan.user_id == user_id,
                MealPlan.scheduled_date == week,
            )
        )
        for other in existing.scalars().all():
            if other.id != plan.id:
                other.scheduled_date = None

        plan.scheduled_date = week
        plan.week_start_date = week
        await db.flush()
        await db.refresh(plan)
        return await self._week_payload(week, plan, db)

    async def unassign_week(
        self, user_id: UUID, week_start_date: date, db: AsyncSession
    ) -> None:
        week = _monday_on_or_before(week_start_date)
        plan = await self._plan_for_week(user_id, week, db)
        if plan is None:
            raise NotFoundError("No plan assigned to this week")
        plan.scheduled_date = None
        await db.flush()

    async def _plan_for_week(
        self, user_id: UUID, week: date, db: AsyncSession
    ) -> MealPlan | None:
        result = await db.execute(
            select(MealPlan).where(
                MealPlan.user_id == user_id,
                MealPlan.scheduled_date == week,
            )
        )
        return result.scalar_one_or_none()

    async def _week_payload(
        self,
        week: date,
        plan: MealPlan | None,
        db: AsyncSession,
    ) -> dict[str, object]:
        days_payload: list[dict[str, object]] = []
        if plan is None:
            for i in range(7):
                days_payload.append(
                    {
                        "day_number": i + 1,
                        "date": (week + timedelta(days=i)).isoformat(),
                        "items": [],
                    }
                )
            return {
                "week_start_date": week.isoformat(),
                "plan_id": None,
                "days": days_payload,
            }

        days_result = await db.execute(
            select(PlanDay)
            .where(PlanDay.plan_id == plan.id)
            .order_by(PlanDay.day_number.asc())
        )
        days = list(days_result.scalars().all())
        day_ids = [d.id for d in days]
        items_by_day: dict[UUID, list[PlanItem]] = {d.id: [] for d in days}
        if day_ids:
            items_result = await db.execute(
                select(PlanItem).where(PlanItem.plan_day_id.in_(day_ids))
            )
            for item in items_result.scalars().all():
                items_by_day.setdefault(item.plan_day_id, []).append(item)

        for i in range(7):
            day_number = i + 1
            day_date = week + timedelta(days=i)
            match = next((d for d in days if d.day_number == day_number), None)
            if match is None:
                days_payload.append(
                    {
                        "day_number": day_number,
                        "date": day_date.isoformat(),
                        "items": [],
                    }
                )
            else:
                items = items_by_day.get(match.id, [])
                days_payload.append(
                    {
                        "id": str(match.id),
                        "day_number": match.day_number,
                        "date": day_date.isoformat(),
                        "calories_actual": _num(match.calories_actual),
                        "protein_g_actual": _num(match.protein_g_actual),
                        "carbs_g_actual": _num(match.carbs_g_actual),
                        "fat_g_actual": _num(match.fat_g_actual),
                        "fiber_g_actual": _num(match.fiber_g_actual),
                        "calories_target": _num(match.calories_target),
                        "protein_g_target": _num(match.protein_g_target),
                        "carbs_g_target": _num(match.carbs_g_target),
                        "fat_g_target": _num(match.fat_g_target),
                        "fiber_g_target": _num(match.fiber_g_target),
                        "items": [
                            {
                                "id": str(item.id),
                                "plan_id": str(plan.id),
                                "day_number": match.day_number,
                                "slot": _enum(item.slot),
                                "recipe_id": str(item.recipe_id)
                                if item.recipe_id
                                else None,
                                "name": item.name,
                                "description": item.description,
                                "recipe_type": _enum(item.recipe_type),
                                "item_source": _enum(item.item_source),
                                "prep_method": _enum(item.prep_method),
                                "color": item.color,
                                "prep_minutes": item.prep_minutes,
                                "slot_order": item.slot_order,
                                "calories": _num(item.calories),
                                "protein_g": _num(item.protein_g),
                                "carbs_g": _num(item.carbs_g),
                                "fat_g": _num(item.fat_g),
                                "fiber_g": _num(item.fiber_g),
                            }
                            for item in items
                        ],
                    }
                )

        return {
            "week_start_date": week.isoformat(),
            "plan_id": str(plan.id),
            "days": days_payload,
        }
