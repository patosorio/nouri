"""Planning retrieval is SQL-filtered, deterministic, and makes no embedding calls."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from db.models import (
    CookingType,
    DietType,
    MealRole,
    PlanDay,
    PlanItem,
    PlanItemSource,
    PlanSlot,
    PreparationType,
    PrimaryProtein,
    Recipe,
    RecipeDietCompatibility,
    RecipeIngredient,
    RecipeMealDetails,
    RecipeNutrition,
    RecipeSource,
    RecipeType,
)
from search.recipe_search_service import RecipeSearchService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_ingredient, make_plan, make_user


async def _recipe(
    db: AsyncSession,
    user_id: UUID,
    *,
    name: str,
    role: MealRole | None = MealRole.BREAKFAST,
    protein: PrimaryProtein = PrimaryProtein.LEGUMES,
    diet: DietType = DietType.PLANT_BASED,
    recipe_type: RecipeType = RecipeType.MEAL,
    with_nutrition: bool = True,
    ingredient_id: UUID | None = None,
    created_at: datetime | None = None,
) -> Recipe:
    recipe = Recipe(
        user_id=user_id,
        name=name,
        recipe_type=recipe_type,
        cooking_type=CookingType.COOKED_100,
        source=RecipeSource.AI_GENERATED,
        prep_method=PreparationType.STEAMED,
        servings=1,
        steps=[{"step_number": 1, "instruction": "Cook."}],
    )
    db.add(recipe)
    await db.flush()
    if created_at is not None:
        recipe.created_at = created_at
    db.add(RecipeDietCompatibility(recipe_id=recipe.id, diet_type=diet))
    if with_nutrition:
        db.add(
            RecipeNutrition(
                recipe_id=recipe.id,
                calories_per_serving=Decimal(400),
                protein_g=Decimal(12),
                carbs_g=Decimal(40),
                fat_g=Decimal(10),
                fiber_g=Decimal(6),
            )
        )
    if role is not None and recipe_type == RecipeType.MEAL:
        db.add(
            RecipeMealDetails(
                recipe_id=recipe.id,
                meal_roles=[role],
                primary_protein_source=protein,
            )
        )
    if ingredient_id is not None:
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient_id,
                amount=Decimal(1),
                unit="cup",
                sort_order=0,
            )
        )
    await db.flush()
    return recipe


@pytest.mark.asyncio
async def test_planning_candidates_filters_order_and_cap(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, email="planning@nouri.app")
    other = await make_user(db_session, email="planning-other@nouri.app")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    peanut = await make_ingredient(db_session, name="planning peanut")

    lunch_tofu = await _recipe(
        db_session,
        user.id,
        name="Lunch tofu",
        role=MealRole.LUNCH,
        protein=PrimaryProtein.TOFU_SOY,
        created_at=base,
    )
    breakfast_legumes = await _recipe(
        db_session,
        user.id,
        name="Breakfast lentils",
        role=MealRole.BREAKFAST,
        protein=PrimaryProtein.LEGUMES,
        created_at=base + timedelta(minutes=1),
    )
    lunch_legumes = await _recipe(
        db_session,
        user.id,
        name="Lunch lentils",
        role=MealRole.LUNCH,
        protein=PrimaryProtein.LEGUMES,
        created_at=base + timedelta(minutes=2),
    )
    breakfast_tofu = await _recipe(
        db_session,
        user.id,
        name="Breakfast tofu",
        role=MealRole.BREAKFAST,
        protein=PrimaryProtein.TOFU_SOY,
        created_at=base + timedelta(minutes=3),
    )
    await _recipe(
        db_session,
        user.id,
        name="Vegan only",
        diet=DietType.VEGAN,
        created_at=base + timedelta(minutes=4),
    )
    await _recipe(
        db_session,
        user.id,
        name="Snack only",
        role=MealRole.SNACK,
        created_at=base + timedelta(minutes=5),
    )
    await _recipe(
        db_session,
        user.id,
        name="No nutrition",
        with_nutrition=False,
        created_at=base + timedelta(minutes=6),
    )
    await _recipe(
        db_session,
        user.id,
        name="Has peanut",
        ingredient_id=peanut.id,
        created_at=base + timedelta(minutes=7),
    )
    juice = await _recipe(
        db_session,
        user.id,
        name="Morning juice",
        role=None,
        recipe_type=RecipeType.JUICE,
        created_at=base + timedelta(minutes=8),
    )
    await _recipe(
        db_session,
        other.id,
        name="Someone else",
        created_at=base + timedelta(minutes=9),
    )

    used = await _recipe(
        db_session,
        user.id,
        name="Used breakfast",
        created_at=base - timedelta(days=2),
    )
    never = await _recipe(
        db_session,
        user.id,
        name="Never breakfast",
        created_at=base + timedelta(days=1),
    )
    plan = await make_plan(db_session, user.id, num_days=1, with_meals=False)
    day = (
        await db_session.execute(select(PlanDay).where(PlanDay.plan_id == plan.id))
    ).scalars().one()
    db_session.add(
        PlanItem(
            plan_day_id=day.id,
            slot=PlanSlot.BREAKFAST,
            slot_order=0,
            recipe_id=used.id,
            item_source=PlanItemSource.SAVED_RECIPE,
            name=used.name,
            recipe_type=RecipeType.MEAL,
        )
    )
    await db_session.flush()

    oldest_ids = []
    for index in range(61):
        recipe = await _recipe(
            db_session,
            user.id,
            name=f"Cap {index:02d}",
            protein=PrimaryProtein.NUTS_SEEDS,
            created_at=base + timedelta(days=10, seconds=index),
        )
        oldest_ids.append(recipe.id)

    search = RecipeSearchService(voyage_client=object())

    async def _embed(*_args: object, **_kwargs: object) -> list[list[float]]:
        raise AssertionError("planning must not embed")

    search.embed_texts = _embed  # type: ignore[method-assign]

    roles = ("breakfast", "lunch", "dinner")
    first = await search.planning_candidates(
        user.id,
        "plant_based",
        roles,
        [peanut.id],
        db_session,
        juicing_enabled=False,
    )
    second = await search.planning_candidates(
        user.id,
        "plant_based",
        roles,
        [peanut.id],
        db_session,
        juicing_enabled=False,
    )
    ids = [row.recipe_id for row in first]
    assert ids == [row.recipe_id for row in second]
    assert all(row.similarity == 0.0 for row in first)

    titles = {row.recipe_id: row.title for row in first}
    assert "Vegan only" not in titles.values()
    assert "Snack only" not in titles.values()
    assert "No nutrition" not in titles.values()
    assert "Has peanut" not in titles.values()
    assert "Morning juice" not in titles.values()
    assert "Someone else" not in titles.values()

    rotated = [
        breakfast_legumes.id,
        breakfast_tofu.id,
        lunch_legumes.id,
        lunch_tofu.id,
    ]
    assert ids[:4] != [
        lunch_tofu.id,
        breakfast_legumes.id,
        lunch_legumes.id,
        breakfast_tofu.id,
    ]
    positions = [ids.index(recipe_id) for recipe_id in rotated]
    assert positions == sorted(positions)

    assert ids.index(never.id) < ids.index(used.id)
    assert len(ids) == 60
    assert oldest_ids[-1] not in ids
    assert oldest_ids[0] in ids

    with_juice = await search.planning_candidates(
        user.id,
        "plant_based",
        roles,
        [peanut.id],
        db_session,
        juicing_enabled=True,
    )
    assert juice.id in {row.recipe_id for row in with_juice}

    via_find = await search.find_candidates(user.id, "plant_based", 7, db_session)
    assert all(row.similarity == 0.0 for row in via_find)


@pytest.mark.asyncio
async def test_planning_rows_are_sql_limited_and_still_cap_at_60(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, email="planning-pool@nouri.app")
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    created = []
    for index in range(301):
        recipe = await _recipe(
            db_session,
            user.id,
            name=f"Pool {index:03d}",
            protein=PrimaryProtein.EGGS,
            created_at=base + timedelta(seconds=index),
        )
        created.append(recipe.id)

    search = RecipeSearchService(voyage_client=object())

    async def _embed(*_args: object, **_kwargs: object) -> list[list[float]]:
        raise AssertionError("planning must not embed")

    search.embed_texts = _embed  # type: ignore[method-assign]
    roles = ("breakfast", "lunch", "dinner")
    rows = await search._planning_rows(
        user.id, DietType.PLANT_BASED, roles, (), db_session, juicing_enabled=False
    )
    assert len(rows) == 300
    assert created[-1] not in {row.recipe_id for row in rows}

    first = await search.planning_candidates(
        user.id, "plant_based", roles, (), db_session
    )
    second = await search.planning_candidates(
        user.id, "plant_based", roles, (), db_session
    )
    ids = [row.recipe_id for row in first]
    assert ids == [row.recipe_id for row in second]
    assert len(ids) == 60
    assert ids[0] == created[0]
    assert created[60] not in ids
