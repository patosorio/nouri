"""PlanExplainerAgent — docs/7_TECH_SPEC.md §5.8."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.client import AnthropicClient
from config import AgentTask, route_model
from db.models import PlanDay, PlanItem
from services.plan_service import PlanService
from services.profile_service import ProfileService

logger = structlog.get_logger(__name__)

_MAX_TOKENS = 400


class PlanExplainerAgent:
    def __init__(self, client: AnthropicClient | None = None) -> None:
        self._client = client or AnthropicClient()

    async def explain(
        self, plan_id: UUID, user_id: UUID, db: AsyncSession
    ) -> AsyncIterator[str]:
        plan = await PlanService().get_plan(plan_id, user_id, db)
        profile = await ProfileService().get_profile(user_id, db)
        exclusions = await ProfileService().get_exclusions(user_id, db)

        days_result = await db.execute(
            select(PlanDay)
            .where(PlanDay.plan_id == plan_id)
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

        structured_context: dict[str, Any] = {
            "plan": {
                "id": str(plan.id),
                "title": plan.title,
                "num_days": plan.num_days,
                "diet_type": plan.diet_type_snapshot.value
                if plan.diet_type_snapshot
                else None,
                "cooking_type": plan.cooking_type_snapshot.value
                if plan.cooking_type_snapshot
                else None,
                "calorie_target": plan.calorie_target_snapshot,
                "protein_g_target": str(plan.protein_g_target_snapshot)
                if plan.protein_g_target_snapshot is not None
                else None,
                "carbs_g_target": str(plan.carbs_g_target_snapshot)
                if plan.carbs_g_target_snapshot is not None
                else None,
                "fat_g_target": str(plan.fat_g_target_snapshot)
                if plan.fat_g_target_snapshot is not None
                else None,
                "fiber_g_target": str(plan.fiber_g_target_snapshot)
                if plan.fiber_g_target_snapshot is not None
                else None,
            },
            "user_profile": {
                "diet_type": profile.diet_type.value,
                "cooking_type": profile.cooking_type.value,
                "calorie_target": profile.calorie_target,
                "exclusions": [
                    e.ingredient_name_raw for e in exclusions if e.ingredient_name_raw
                ],
            },
            "days": [
                {
                    "day_number": day.day_number,
                    "calories_actual": float(day.calories_actual)
                    if day.calories_actual is not None
                    else None,
                    "items": [
                        {
                            "slot": item.slot.value,
                            "name": item.name,
                            "calories": float(item.calories)
                            if item.calories is not None
                            else None,
                            "prep_method": item.prep_method.value
                            if item.prep_method
                            else None,
                        }
                        for item in items_by_day.get(day.id, [])
                    ],
                }
                for day in days
            ],
        }

        system_prompt = (
            "You are Nouri, explaining a meal plan you already built for this "
            "user. Write a short, natural-language explanation of why this plan "
            "fits them — conversational and knowledgeable, not clinical, not a "
            "bulleted report. No JSON, no headers, no emoji.\n\n"
            "Cover, in flowing prose: how the week's nutrition lines up with their "
            "calorie and macro targets, how the raw/cooked balance matches their "
            "preference, what kind of variety they'll get across the week, how "
            "their exclusions were respected, and one or two genuine highlights "
            "worth calling out. You don't need to hit every point as a checklist — "
            "write it as you'd actually explain it to someone, weaving in what "
            "matters most for this plan.\n\n"
            "Max 400 tokens. Do not restate the full day-by-day plan — the user can "
            "already see it."
        )
        user_prompt = (
            "Explain this meal plan.\n"
            f"<plan_context>{json.dumps(structured_context, default=str)}</plan_context>"
        )

        model = route_model(AgentTask.PLAN_EXPLANATION)
        async for item in self._client.stream_text(
            [{"role": "user", "content": user_prompt}],
            model=model,
            tools=None,
            max_tokens=_MAX_TOKENS,
            system=system_prompt,
        ):
            if isinstance(item, str):
                yield item
