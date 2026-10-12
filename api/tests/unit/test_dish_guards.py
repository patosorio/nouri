"""Dish nutrition flags and the generated-dish retry. No model calls."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from agent.plan_generator import PlanGeneratorAgent
from db.models import CookingType, DietType, RecipeUsagePolicy
from exceptions import PlanGenerationFailedError
from schemas.agent import PlanGenerationJob
from schemas.recipes import RecipePlanSnapshot
from validation.dish_guards import (
    DayTotals,
    DishNutrition,
    ServingNutrition,
    check_day_totals,
    check_dish_nutrition,
    hard_dish_flags,
)


def _dish(**overrides: object) -> DishNutrition:
    values: dict[str, object] = {
        "name": "Miso Cod",
        "path": "day2.lunch",
        "calories_kcal": 290,
        "protein_g": 20,
        "fat_g": 10,
        "carbohydrates_g": 30,
        "fiber_g": 5,
        "ingredient_grams": None,
    }
    values.update(overrides)
    return DishNutrition(**values)  # type: ignore[arg-type]


def test_atwater_within_15_percent_is_quiet() -> None:
    assert check_dish_nutrition(_dish()) == []


def test_atwater_mismatch_names_the_field_path() -> None:
    flags = check_dish_nutrition(
        _dish(calories_kcal=820, protein_g=45, fat_g=30, carbohydrates_g=40, fiber_g=5)
    )
    assert flags == ["day2.lunch 'Miso Cod': calories 820 vs 4P+4C+9F 610 (+34%)"]
    assert hard_dish_flags(
        _dish(calories_kcal=820, protein_g=45, fat_g=30, carbohydrates_g=40, fiber_g=5)
    ) == flags


def test_density_skips_when_any_ingredient_lacks_grams() -> None:
    assert check_dish_nutrition(_dish(ingredient_grams=None)) == []


def test_density_flags_kcal_per_100g_outside_20_to_900() -> None:
    flags = check_dish_nutrition(_dish(ingredient_grams=(10.0,)))
    assert flags == ["day2.lunch 'Miso Cod': 2900 kcal/100g is outside 20–900"]
    assert hard_dish_flags(_dish(ingredient_grams=(10.0,))) == []


def test_fiber_above_carbs_and_negatives_are_hard() -> None:
    dish = _dish(fiber_g=40, protein_g=-1)
    flags = check_dish_nutrition(dish)
    hard = hard_dish_flags(dish)
    assert "day2.lunch 'Miso Cod': protein_g -1 is negative" in hard
    assert "day2.lunch 'Miso Cod': fiber_g 40 > carbohydrates_g 30" in hard
    assert all("outside" not in flag for flag in hard)
    assert "day2.lunch 'Miso Cod': protein_g -1 outside 0–120" in flags


def test_bounds_reuse_the_nutrition_validator_table() -> None:
    dish = _dish(calories_kcal=730, protein_g=130, fat_g=10, carbohydrates_g=30, fiber_g=5)
    flags = check_dish_nutrition(dish)
    assert flags == ["day2.lunch 'Miso Cod': protein_g 130 outside 0–120"]
    assert hard_dish_flags(dish) == []


def test_day_totals_must_match_per_serving_times_servings() -> None:
    items = [
        ServingNutrition(1, 290, 20, 10, 30, 5),
        ServingNutrition(2, 100, 5, 2, 10, 1),
    ]
    assert check_day_totals(1, items, DayTotals(490, 30, 14, 50, 7)) == []
    flags = check_day_totals(2, items, DayTotals(400, 30, 14, 50, 7))
    assert flags == ["Day 2 calories 400 != item sum 490"]


def _recipe(title: str, slot: str, **nutrition: float) -> dict[str, object]:
    values = {
        "calories_kcal": 290.0,
        "protein_g": 20.0,
        "fat_g": 10.0,
        "carbohydrates_g": 30.0,
        "fiber_g": 5.0,
    }
    values.update(nutrition)
    return {
        "title": title,
        "slot_type": slot,
        "diet_type": "pescatarian",
        "prep_type": "steamed",
        "servings": 1,
        "primary_protein": "none",
        "ingredients": [{"ingredient_name": title, "quantity": 1, "unit": "cup"}],
        "steps": [{"step_number": 1, "instruction": "Cook."}],
        "nutrition_per_serving": values,
    }


def _day(recipes: list[dict[str, object]]) -> dict[str, object]:
    items = [
        {
            "slot_type": recipe["slot_type"],
            "recipe_id": "generate_new",
            "recipe_title": recipe["title"],
            "servings": 1,
        }
        for recipe in recipes
    ]
    return {"days": [{"day_number": 1, "items": items}], "generated_recipes": recipes}


def _good_day() -> dict[str, object]:
    return _day(
        [
            _recipe("Oats", "breakfast"),
            _recipe("Salad", "lunch"),
            _recipe("Steaks", "dinner"),
        ]
    )


def _bad_day() -> dict[str, object]:
    return _day(
        [
            _recipe("Oats", "breakfast"),
            _recipe(
                "Miso Cod",
                "lunch",
                calories_kcal=820,
                protein_g=45,
                fat_g=30,
                carbohydrates_g=40,
                fiber_g=5,
            ),
            _recipe("Steaks", "dinner"),
        ]
    )


class _Seq:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls = 0

    async def complete(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if self.calls > 2:
            raise AssertionError("plan generation billed a third model call")
        payload = self.payloads[min(self.calls, len(self.payloads)) - 1]
        block = SimpleNamespace(type="tool_use", name="output_plan", input=payload)
        return SimpleNamespace(
            content=[block],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )


class _Rows:
    def scalars(self) -> _Rows:
        return self

    def all(self) -> list[object]:
        return []


async def _run(
    payloads: list[dict[str, object]] | None,
    *,
    saved: dict[str, object] | None = None,
    calorie_target: int = 870,
    snapshots: dict[object, RecipePlanSnapshot] | None = None,
) -> tuple[object, _Seq]:
    client = _Seq(payloads or [])
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=1,
        diet_type=DietType.PESCATARIAN,
        cooking_type=CookingType.COOKED_100,
        calorie_target=calorie_target,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        trace_id="dish-guards",
    )
    profile = SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=calorie_target,
        protein_g_target=60,
        carbs_g_target=90,
        fat_g_target=30,
        fiber_g_target=15,
        diet_type=DietType.PESCATARIAN,
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=profile)
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value=snapshots or {})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        result = await agent.generate(job, db=db, saved_llm_output=saved)
    return result, client


@pytest.mark.asyncio
async def test_inconsistent_generated_macros_retry_then_pass() -> None:
    result, client = await _run([_bad_day(), _good_day()])
    assert client.calls == 2
    titles = [item.recipe_title for item in result.days[0].items]  # type: ignore[attr-defined]
    assert "Miso Cod" not in titles
    assert "Salad" in titles


@pytest.mark.asyncio
async def test_inconsistent_generated_macros_retry_then_fail() -> None:
    client = _Seq([_bad_day(), _bad_day()])
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=1,
        diet_type=DietType.PESCATARIAN,
        cooking_type=CookingType.COOKED_100,
        calorie_target=870,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        trace_id="dish-guards-fail",
    )
    profile = SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=870,
        protein_g_target=None,
        carbs_g_target=None,
        fat_g_target=None,
        fiber_g_target=None,
        diet_type=DietType.PESCATARIAN,
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
        pytest.raises(PlanGenerationFailedError, match="day1.lunch 'Miso Cod'") as raised,
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=profile)
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        await agent.generate(job, db=db)
    assert client.calls == 2
    assert "4P+4C+9F" in str(raised.value)


@pytest.mark.asyncio
async def test_inconsistent_generated_macros_fail_without_calling_twice() -> None:
    client = _Seq([])
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )
    saved = {"output": _bad_day(), "handles": {}, "roles": {}, "titles": {}, "types": {}}
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=1,
        diet_type=DietType.PESCATARIAN,
        cooking_type=CookingType.COOKED_100,
        calorie_target=870,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        trace_id="dish-guards-resume",
    )
    profile = SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=870,
        protein_g_target=None,
        carbs_g_target=None,
        fat_g_target=None,
        fiber_g_target=None,
        diet_type=DietType.PESCATARIAN,
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
        pytest.raises(PlanGenerationFailedError, match="4P\\+4C\\+9F"),
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=profile)
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        await agent.generate(job, db=db, saved_llm_output=saved)
    assert client.calls == 0


@pytest.mark.asyncio
async def test_bounds_on_a_generated_dish_are_logged_not_rejected() -> None:
    payload = _day(
        [
            _recipe("Oats", "breakfast"),
            _recipe(
                "Huge steak",
                "lunch",
                calories_kcal=730,
                protein_g=130,
                fat_g=10,
                carbohydrates_g=30,
                fiber_g=5,
            ),
            _recipe("Steaks", "dinner"),
        ]
    )
    client = _Seq([payload])
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=1,
        diet_type=DietType.OMNIVORE,
        cooking_type=CookingType.COOKED_100,
        calorie_target=1310,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        trace_id="bounds",
    )
    profile = SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=1310,
        protein_g_target=None,
        carbs_g_target=None,
        fat_g_target=None,
        fiber_g_target=None,
        diet_type=DietType.OMNIVORE,
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=profile)
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        await agent.generate(job, db=db)
    assert client.calls == 1
    assert any("protein_g 130 outside" in flag for flag in agent.dish_flags)


@pytest.mark.asyncio
async def test_saved_recipe_atwater_flag_does_not_reject() -> None:
    saved_id = uuid4()
    from search.recipe_search_service import MacroSummary, RecipeCandidate

    candidate = RecipeCandidate(
        recipe_id=saved_id,
        title="Saved cod",
        diet_type="pescatarian",
        cooking_type="cooked_100",
        macro_summary=MacroSummary(820, 45, 40, 30, 5),
        similarity=1,
        meal_roles=["lunch"],
        recipe_type="meal",
    )
    payload = {
        "days": [
            {
                "day_number": 1,
                "items": [
                    {
                        "slot_type": "breakfast",
                        "recipe_id": "generate_new",
                        "recipe_title": "Oats",
                        "servings": 1,
                    },
                    {
                        "slot_type": "lunch",
                        "recipe_id": "R1",
                        "recipe_title": "Saved cod",
                        "servings": 1,
                    },
                    {
                        "slot_type": "dinner",
                        "recipe_id": "generate_new",
                        "recipe_title": "Steaks",
                        "servings": 1,
                    },
                ],
            }
        ],
        "generated_recipes": [_recipe("Oats", "breakfast"), _recipe("Steaks", "dinner")],
    }
    client = _Seq([payload])
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(  # type: ignore[arg-type]
            planning_candidates=AsyncMock(return_value=[candidate])
        ),
    )
    snap = RecipePlanSnapshot(
        recipe_id=saved_id,
        title="Saved cod",
        calories=820,
        protein_g=45,
        carbs_g=40,
        fat_g=30,
        fiber_g=5,
    )
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=1,
        diet_type=DietType.PESCATARIAN,
        cooking_type=CookingType.COOKED_100,
        calorie_target=1400,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        trace_id="saved-flag",
    )
    profile = SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=1400,
        protein_g_target=None,
        carbs_g_target=None,
        fat_g_target=None,
        fiber_g_target=None,
        diet_type=DietType.PESCATARIAN,
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=profile)
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={saved_id: snap})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        await agent.generate(job, db=db)
    assert client.calls == 1
    assert any("4P+4C+9F" in flag for flag in agent.dish_flags)
