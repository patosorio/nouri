"""Every recipe id is owned before insert. Unknown ids are never labeled saved."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from db.models import JuiceTime, PlanDay, PlanItem, PlanItemSource, PlanSlot, RecipeType
from exceptions import PlanGenerationFailedError
from schemas.agent import GeneratedPlanData as AgentPlan
from schemas.agent import (
    GeneratedPlanDayAI,
    GeneratedPlanItemAI,
    GeneratedRecipeAI,
    NutritionPerServingAI,
)
from schemas.plans import GeneratedPlanData, GeneratedPlanDay, GeneratedPlanItem
from services.plan_service import PlanService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from worker.agent_to_service import map_generated_plan

from tests.factories import make_plan, make_recipe, make_user


def _agent_item(recipe_id) -> GeneratedPlanItemAI:
    return GeneratedPlanItemAI(
        slot_type="lunch",
        recipe_id=recipe_id,
        recipe_title="Bowl",
        servings=1,
        calories=500,
    )


def test_unknown_id_is_not_labeled_saved() -> None:
    unknown = uuid4()
    plan = AgentPlan(
        days=[GeneratedPlanDayAI(day_number=1, items=[_agent_item(unknown)])],
        generated_recipes=[],
    )
    with pytest.raises(PlanGenerationFailedError, match="not a saved or generated"):
        map_generated_plan(plan, saved_ids=set())


def test_saved_id_is_labeled_saved_and_generated_id_stays_generated() -> None:
    saved = uuid4()
    generated = uuid4()
    plan = AgentPlan(
        days=[
            GeneratedPlanDayAI(
                day_number=1,
                items=[_agent_item(saved), _agent_item(generated)],
            )
        ],
        generated_recipes=[
            GeneratedRecipeAI(
                title="New bowl",
                slot_type="lunch",
                diet_type="plant_based",
                prep_type="steamed",
                servings=1,
                primary_protein="none",
                assigned_id=generated,
                ingredients=[],
                steps=[],
                nutrition_per_serving=NutritionPerServingAI(
                    calories_kcal=500,
                    protein_g=20,
                    fat_g=10,
                    carbohydrates_g=40,
                    fiber_g=5,
                ),
            )
        ],
    )
    mapped = map_generated_plan(plan, saved_ids={saved})
    sources = {item.recipe_id: item.item_source for item in mapped.days[0].items}
    assert sources[saved] == PlanItemSource.SAVED_RECIPE
    assert sources[generated] == PlanItemSource.AI_GENERATED


def _service_item(recipe_id, *, juice: bool = False) -> GeneratedPlanItem:
    return GeneratedPlanItem(
        slot_type=PlanSlot.JUICE if juice else PlanSlot.LUNCH,
        recipe_title="Green" if juice else "Bowl",
        recipe_id=recipe_id,
        recipe_type=RecipeType.JUICE if juice else RecipeType.MEAL,
        item_source=PlanItemSource.SAVED_RECIPE,
        calories=Decimal(120) if juice else Decimal(500),
        juice_time=JuiceTime.MORNING if juice else None,
        juice_size_ml=500 if juice else None,
        nutrition_unknown=not juice,
    )


@pytest.mark.asyncio
async def test_write_rejects_foreign_and_missing_ids(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="plan-owner@nouri.app")
    other = await make_user(db_session, email="plan-other@nouri.app")
    plan = await make_plan(db_session, owner.id, num_days=1, with_meals=False)
    foreign = await make_recipe(db_session, other.id, name="Not hers")
    service = PlanService()

    before = (
        await db_session.execute(select(PlanDay).where(PlanDay.plan_id == plan.id))
    ).scalars().all()
    assert len(before) == 1

    for recipe_id in (foreign.id, uuid4()):
        generated = GeneratedPlanData(
            days=[
                GeneratedPlanDay(
                    day_number=1,
                    items=[_service_item(recipe_id)],
                )
            ]
        )
        with pytest.raises(PlanGenerationFailedError, match="not owned"):
            await service.write_generated_plan(plan.id, generated, db_session)
        after = (
            await db_session.execute(select(PlanDay).where(PlanDay.plan_id == plan.id))
        ).scalars().all()
        assert len(after) == 1
        assert after[0].id == before[0].id


@pytest.mark.asyncio
async def test_juice_fields_round_trip(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="juice-owner@nouri.app")
    recipe = await make_recipe(db_session, owner.id, name="Morning greens")
    plan = await make_plan(db_session, owner.id, num_days=1, with_meals=False)
    generated = GeneratedPlanData(
        days=[
            GeneratedPlanDay(
                day_number=1,
                totals_incomplete=True,
                items=[
                    _service_item(recipe.id, juice=True),
                    GeneratedPlanItem(
                        slot_type=PlanSlot.BREAKFAST,
                        recipe_title="Unmeasured",
                        recipe_id=None,
                        item_source=PlanItemSource.AI_GENERATED,
                        nutrition_unknown=True,
                    ),
                ],
            )
        ]
    )
    await PlanService().write_generated_plan(plan.id, generated, db_session)
    day = (
        await db_session.execute(select(PlanDay).where(PlanDay.plan_id == plan.id))
    ).scalars().one()
    items = (
        await db_session.execute(
            select(PlanItem).where(PlanItem.plan_day_id == day.id)
        )
    ).scalars().all()
    juice = next(item for item in items if item.slot == PlanSlot.JUICE)
    unknown = next(item for item in items if item.nutrition_unknown)
    assert day.totals_incomplete is True
    assert juice.juice_time == JuiceTime.MORNING
    assert juice.juice_size_ml == 500
    assert juice.nutrition_unknown is False
    assert unknown.calories is None
