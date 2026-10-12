"""Pins are placed by id. An excluded pin never calls the model."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from agent.plan_generator import PlanGeneratorAgent
from db.models import (
    CookingType,
    DietType,
    PreparationType,
    Recipe,
    RecipeSource,
    RecipeType,
    RecipeUsagePolicy,
)
from exceptions import PlanGenerationFailedError
from preprocessing.notes_preprocessor import NotesPreprocessor, RecipeTitleRef
from schemas.agent import PlanGenerationJob
from schemas.recipes import PinnedRecipeSnapshot, RecipeIngredientSnapshot
from services.recipe_service import RecipeService
from sqlalchemy.ext.asyncio import AsyncSession
from worker.retry_policy import failure_should_retry

from tests.factories import make_recipe, make_user


def _job(*, user_id, plan_id, notes: str, days: int = 1) -> PlanGenerationJob:
    return PlanGenerationJob(
        user_id=user_id,
        plan_id=plan_id,
        duration_days=days,
        diet_type=DietType.PLANT_BASED,
        cooking_type=CookingType.COOKED_100,
        calorie_target=2000,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        notes=notes,
        trace_id="pins",
    )


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=2000,
        protein_g_target=80,
        carbs_g_target=250,
        fat_g_target=70,
        fiber_g_target=30,
        diet_type=DietType.PLANT_BASED,
    )


def _generated(title: str, slot: str) -> dict[str, object]:
    return {
        "title": title,
        "slot_type": slot,
        "diet_type": "plant_based",
        "prep_type": "steamed",
        "servings": 1,
        "primary_protein": "none",
        "ingredients": [
            {"ingredient_name": "oats", "quantity": 1, "unit": "cup"}
        ],
        "steps": [{"step_number": 1, "instruction": "Cook."}],
        "nutrition_per_serving": {
            "calories_kcal": 670,
            "protein_g": 27,
            "fat_g": 23,
            "carbohydrates_g": 83,
            "fiber_g": 10,
        },
    }


class _Client:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.calls = 0
        self.payload = payload

    async def complete(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if self.payload is None:
            raise AssertionError("model must not be called")
        block = SimpleNamespace(type="tool_use", name="output_plan", input=self.payload)
        return SimpleNamespace(
            content=[block],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


def _meals_payload() -> dict[str, object]:
    recipes = []
    items = []
    for slot in ("breakfast", "lunch", "dinner"):
        title = f"New {slot}"
        items.append(
            {
                "slot_type": slot,
                "recipe_id": "generate_new",
                "recipe_title": title,
                "servings": 1,
            }
        )
        recipes.append(_generated(title, slot))
    return {"days": [{"day_number": 1, "items": items}], "generated_recipes": recipes}


@pytest.mark.asyncio
async def test_excluded_pin_is_terminal_and_skips_the_model() -> None:
    user_id = uuid4()
    recipe_id = uuid4()
    client = _Client(None)
    pin = PinnedRecipeSnapshot(
        recipe_id=recipe_id,
        title="Peanut Bowl",
        recipe_type=RecipeType.MEAL,
        ingredients=[
            RecipeIngredientSnapshot(name="peanut butter", ingredient_id=uuid4())
        ],
        calories=400,
        protein_g=12,
        carbs_g=30,
        fat_g=18,
        fiber_g=4,
    )
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )
    exclusion = SimpleNamespace(
        ingredient_name_raw="peanut",
        ingredient_id=None,
        user_id=user_id,
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
        patch.object(
            PlanGeneratorAgent,
            "_load_recipe_titles",
            AsyncMock(return_value=[RecipeTitleRef(id=recipe_id, name="Peanut Bowl")]),
        ),
        patch.object(PlanGeneratorAgent, "_load_juice_configs", AsyncMock(return_value=[])),
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=_profile())
        profiles.return_value.get_exclusions = AsyncMock(return_value=[exclusion])
        recipes.return_value.load_pinned_recipes = AsyncMock(return_value={recipe_id: pin})
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={})
        with pytest.raises(PlanGenerationFailedError, match="Peanut Bowl") as raised:
            await agent.generate(
                _job(user_id=user_id, plan_id=uuid4(), notes="Day 1 breakfast Peanut Bowl"),
                db=AsyncMock(),
            )

    assert client.calls == 0
    assert "peanut" in str(raised.value)
    job = SimpleNamespace(job_type="plan_generation", llm_output=None, plan_attempt_state=None)
    assert failure_should_retry(job, timed_out=False, exc=raised.value) is False


@pytest.mark.asyncio
async def test_no_nutrition_pin_marks_the_day_incomplete() -> None:
    user_id = uuid4()
    recipe_id = uuid4()
    client = _Client(_meals_payload())
    pin = PinnedRecipeSnapshot(
        recipe_id=recipe_id,
        title="Unmeasured Soup",
        recipe_type=RecipeType.MEAL,
        ingredients=[RecipeIngredientSnapshot(name="carrot", ingredient_id=uuid4())],
        calories=None,
    )
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
        patch.object(
            PlanGeneratorAgent,
            "_load_recipe_titles",
            AsyncMock(
                return_value=[RecipeTitleRef(id=recipe_id, name="Unmeasured Soup")]
            ),
        ),
        patch.object(PlanGeneratorAgent, "_load_juice_configs", AsyncMock(return_value=[])),
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=_profile())
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_pinned_recipes = AsyncMock(return_value={recipe_id: pin})
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={})
        result = await agent.generate(
            _job(user_id=user_id, plan_id=uuid4(), notes="Day 1 breakfast Unmeasured Soup"),
            db=AsyncMock(),
        )

    breakfast = next(item for item in result.days[0].items if item.slot_type == "breakfast")
    assert breakfast.recipe_id == recipe_id
    assert breakfast.nutrition_unknown is True
    assert breakfast.calories is None
    assert result.review_notes is not None
    assert "Day 1 totals incomplete: Unmeasured Soup has no nutrition" in result.review_notes
    assert client.calls == 1


@pytest.mark.asyncio
async def test_missing_and_foreign_pins_raise(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="pin-owner@nouri.app")
    other = await make_user(db_session, email="pin-other@nouri.app")
    foreign = await make_recipe(db_session, other.id, name="Secret Soup")
    missing = uuid4()
    service = RecipeService()

    with pytest.raises(PlanGenerationFailedError, match="Secret Soup"):
        await service.load_pinned_recipes(
            owner.id,
            [foreign.id],
            db_session,
            names={foreign.id: "Secret Soup"},
        )
    with pytest.raises(PlanGenerationFailedError, match="Gone Recipe"):
        await service.load_pinned_recipes(
            owner.id,
            [missing],
            db_session,
            names={missing: "Gone Recipe"},
        )


@pytest.mark.asyncio
async def test_pin_on_the_150th_recipe_is_found(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="library-150@nouri.app")
    target_id = None
    for index in range(150):
        name = "Pin Target Alpha" if index == 149 else f"Filler {index:03d}"
        recipe = Recipe(
            user_id=user.id,
            name=name,
            recipe_type=RecipeType.MEAL,
            cooking_type=CookingType.COOKED_100,
            source=RecipeSource.AI_GENERATED,
            prep_method=PreparationType.STEAMED,
        )
        db_session.add(recipe)
        if index == 149:
            await db_session.flush()
            target_id = recipe.id
    await db_session.flush()

    titles = await PlanGeneratorAgent._load_recipe_titles(user.id, db_session)
    assert len(titles) >= 150
    assert any(title.id == target_id for title in titles)
    extracted = NotesPreprocessor().extract(
        "Monday breakfast Pin Target Alpha",
        titles,
        duration_days=7,
    )
    assert any(
        assignment.recipe_id == target_id
        for assignment in extracted.hard_slot_assignments
    )
