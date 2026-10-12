"""Applying estimated nutrition clears the unknown flag and the day total."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from db.models import PlanDay, PlanItem, PlanItemSource, PlanSlot, RecipeType
from services.plan_service import PlanService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_plan, make_recipe, make_user


def _nutrition() -> SimpleNamespace:
    return SimpleNamespace(
        calories_per_serving=Decimal(400),
        protein_g=Decimal(12),
        carbs_g=Decimal(40),
        fat_g=Decimal(10),
        fiber_g=Decimal(6),
    )


async def _unknown_item(
    db: AsyncSession, day: PlanDay, recipe_id: object, *, name: str, order: int
) -> PlanItem:
    item = PlanItem(
        plan_day_id=day.id,
        slot=PlanSlot.BREAKFAST if order == 0 else PlanSlot.LUNCH,
        slot_order=order,
        recipe_id=recipe_id,
        item_source=PlanItemSource.SAVED_RECIPE,
        name=name,
        recipe_type=RecipeType.MEAL,
        nutrition_unknown=True,
    )
    db.add(item)
    await db.flush()
    return item


@pytest.mark.asyncio
async def test_apply_clears_unknown_nutrition_and_day_flag(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, email="apply-one@nouri.app")
    recipe = await make_recipe(db_session, user.id, name="Unmeasured soup")
    plan = await make_plan(db_session, user.id, num_days=1, with_meals=False)
    day = (
        await db_session.execute(select(PlanDay).where(PlanDay.plan_id == plan.id))
    ).scalars().one()
    day.totals_incomplete = True
    item = await _unknown_item(db_session, day, recipe.id, name=recipe.name, order=0)

    await PlanService().apply_recipe_nutrition_to_items(recipe.id, _nutrition(), db_session)
    await db_session.refresh(item)
    await db_session.refresh(day)

    assert item.nutrition_unknown is False
    assert item.calories == Decimal(400)
    assert day.totals_incomplete is False
    assert day.calories_actual == Decimal(400)


@pytest.mark.asyncio
async def test_apply_one_of_two_unknown_items_leaves_the_day_incomplete(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, email="apply-two@nouri.app")
    first = await make_recipe(db_session, user.id, name="Soup")
    second = await make_recipe(db_session, user.id, name="Stew")
    plan = await make_plan(db_session, user.id, num_days=1, with_meals=False)
    day = (
        await db_session.execute(select(PlanDay).where(PlanDay.plan_id == plan.id))
    ).scalars().one()
    day.totals_incomplete = True
    stamped = await _unknown_item(db_session, day, first.id, name=first.name, order=0)
    other = await _unknown_item(db_session, day, second.id, name=second.name, order=1)

    await PlanService().apply_recipe_nutrition_to_items(first.id, _nutrition(), db_session)
    await db_session.refresh(stamped)
    await db_session.refresh(other)
    await db_session.refresh(day)

    assert stamped.nutrition_unknown is False
    assert stamped.calories == Decimal(400)
    assert other.nutrition_unknown is True
    assert other.calories is None
    assert day.totals_incomplete is True
    assert day.calories_actual == Decimal(400)
