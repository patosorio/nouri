"""PlanGeneratorAgent wiring — snapshots on PlanItemView, assigner not LLM repair."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from agent.plan_generator import (
    BREAKFAST_EXAMPLES_BY_DIET,
    PlanGeneratorAgent,
    breakfast_protein_rule,
)
from db.models import CookingType, DietType, PreparationType, RecipeUsagePolicy
from schemas.agent import (
    GeneratedPlanData,
    GeneratedPlanDayAI,
    GeneratedPlanItemAI,
    PlanGenerationJob,
)
from search.recipe_search_service import MacroSummary, RecipeCandidate
from validation.types import PlanItemView
from worker.agent_to_service import map_generated_plan


def test_retry_messages_after_max_tokens_restarts_clean() -> None:
    messages = PlanGeneratorAgent._retry_messages_after_failure(
        user_prompt="Generate a plan",
        message=SimpleNamespace(
            stop_reason="max_tokens",
            content=[SimpleNamespace(type="tool_use", id="toolu_1", name="output_plan")],
        ),
        error=ValueError("truncated"),
    )
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    text = str(messages[0]["content"])
    assert "truncated" in text
    assert "reuse titles" not in text
    assert "reuse the same title" not in text


def test_retry_messages_after_validation_uses_tool_result() -> None:
    block = SimpleNamespace(type="tool_use", id="toolu_abc", name="output_plan", input={})
    message = SimpleNamespace(stop_reason="tool_use", content=[block])
    messages = PlanGeneratorAgent._retry_messages_after_failure(
        user_prompt="Generate a plan",
        message=message,
        error=ValueError("missing nutrition"),
    )
    assert messages[0]["role"] == "assistant"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"][0]["type"] == "tool_result"
    assert messages[1]["content"][0]["tool_use_id"] == "toolu_abc"
    assert messages[1]["content"][0]["is_error"] is True


def test_map_generated_plan_copies_item_snapshots() -> None:
    item = GeneratedPlanItemAI(
        slot_type="lunch",
        recipe_id=uuid4(),
        recipe_title="Bowl",
        calories=610.0,
        protein_g=22.0,
        carbs_g=70.0,
        fat_g=18.0,
        fiber_g=9.0,
        prep_method=PreparationType.RAW,
    )
    mapped = map_generated_plan(
        GeneratedPlanData(days=[GeneratedPlanDayAI(day_number=1, items=[item])]),
        saved_ids={item.recipe_id},
    )
    out = mapped.days[0].items[0]
    assert out.calories == Decimal("610.0")
    assert out.protein_g == Decimal("22.0")
    assert out.prep_method == PreparationType.RAW


def test_to_plan_draft_view_copies_snapshot_macros() -> None:
    item = GeneratedPlanItemAI(
        slot_type="breakfast",
        recipe_id=uuid4(),
        recipe_title="Oats",
        calories=420.0,
        protein_g=14.0,
        carbs_g=60.0,
        fat_g=12.0,
        fiber_g=8.0,
        prep_method=PreparationType.RAW,
        primary_protein="legumes",
    )
    plan = GeneratedPlanData(
        days=[GeneratedPlanDayAI(day_number=1, items=[item])],
        generated_recipes=[],
    )
    draft = PlanGeneratorAgent()._to_plan_draft_view(
        plan,
        {item.recipe_id: SimpleNamespace(ingredients=[])},
        {},
    )
    view: PlanItemView = draft.days[0].items[0]
    assert view.calories == 420.0
    assert view.protein_g == 14.0
    assert view.carbs_g == 60.0
    assert view.fat_g == 12.0
    assert view.fiber_g == 8.0
    assert view.prep_method == "raw"
    assert view.primary_protein == "legumes"


def _payload_3_day() -> dict:
    days = []
    recipes = []
    for day in range(1, 4):
        items = []
        for i, slot in enumerate(("breakfast", "lunch", "dinner")):
            title = f"Day{day} {slot}"
            items.append(
                {
                    "slot_type": slot,
                    "recipe_id": "generate_new",
                    "recipe_title": title,
                    "servings": 1,
                }
            )
            recipes.append(
                {
                    "title": title,
                    "slot_type": slot,
                    "diet_type": "plant_based",
                    "prep_type": "steamed",
                    "servings": 1,
                    "primary_protein": "none",
                    "ingredients": [
                        {
                            "ingredient_name": f"{slot}-base-{day}",
                            "quantity": 100,
                            "unit": "g",
                        }
                    ],
                    "steps": [{"step_number": 1, "instruction": "Prep."}],
                    "nutrition_per_serving": {
                        "calories_kcal": 670,
                        "protein_g": 27,
                        "fat_g": 23,
                        "carbohydrates_g": 83,
                        "fiber_g": 10,
                    },
                }
            )
        days.append({"day_number": day, "items": items})
    return {"days": days, "generated_recipes": recipes}


@pytest.mark.asyncio
async def test_generate_assigns_nonzero_macros_in_one_llm_call() -> None:
    payload = _payload_3_day()
    calls: list[object] = []

    class FakeClient:
        async def complete(self, *args, **kwargs):
            calls.append(1)
            block = SimpleNamespace(type="tool_use", name="output_plan", input=payload)
            return SimpleNamespace(
                content=[block],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=0, output_tokens=0),
            )

    class _Rows:
        def scalars(self) -> _Rows:
            return self

        def all(self) -> list[object]:
            return []

    class FakeSearch:
        async def planning_candidates(self, *args, **kwargs):
            return []

    profile = SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=2000,
        protein_g_target=80,
        carbs_g_target=250,
        fat_g_target=70,
        fiber_g_target=30,
        diet_type=DietType.PLANT_BASED,
    )
    agent = PlanGeneratorAgent(client=FakeClient(), recipe_search=FakeSearch())  # type: ignore[arg-type]
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=3,
        diet_type=DietType.PLANT_BASED,
        cooking_type=CookingType.COOKED_100,
        calorie_target=2000,
        protein_g_target=Decimal(80),
        carbs_g_target=Decimal(250),
        fat_g_target=Decimal(70),
        fiber_g_target=Decimal(30),
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        trace_id="test-assign",
    )

    with (
        patch("agent.plan_generator.ProfileService") as ps_cls,
        patch("agent.plan_generator.RecipeService") as rs_cls,
    ):
        ps_cls.return_value.get_profile = AsyncMock(return_value=profile)
        ps_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        rs_cls.return_value.list_recipes = AsyncMock(
            return_value=SimpleNamespace(data=[])
        )
        rs_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        result = await agent.generate(job, db=db)

    assert len(calls) == 1
    assert result.days
    for day in result.days:
        day_cal = sum(i.calories or 0 for i in day.items)
        assert day_cal > 0
        for item in day.items:
            assert item.calories is not None
            assert item.calories > 0
            assert item.prep_method is not None


def test_summarise_candidates_includes_meal_roles_and_recipe_type() -> None:
    recipe_id = uuid4()
    candidate = RecipeCandidate(
        recipe_id=recipe_id,
        title="Oats",
        diet_type="vegan",
        cooking_type="raw_100",
        macro_summary=MacroSummary(
            calories=300,
            protein_g=12,
            carbs_g=40,
            fat_g=8,
            fiber_g=6,
        ),
        similarity=0.0,
        meal_roles=["breakfast"],
        recipe_type="meal",
    )
    summaries = PlanGeneratorAgent._summarise_candidates(
        [candidate], {"R1": recipe_id}
    )
    assert summaries[0]["meal_roles"] == ["breakfast"]
    assert summaries[0]["recipe_type"] == "meal"
    assert summaries[0]["ref"] == "R1"
    assert "similarity" not in summaries[0]


def test_breakfast_rule_examples_follow_diet() -> None:
    assert set(BREAKFAST_EXAMPLES_BY_DIET) == set(DietType)
    vegan = breakfast_protein_rule(DietType.VEGAN)
    assert vegan.startswith(
        "Breakfast should still be protein-rich, using dishes allowed by the "
        "plan's diet_type."
    )
    assert "eggs" not in vegan.lower()
    assert "yoghurt" not in vegan.lower()
    assert "tofu scramble" in vegan
    assert "protein oats" in vegan
    for diet in (DietType.PLANT_BASED, DietType.WFPB):
        line = breakfast_protein_rule(diet)
        assert "eggs" not in line.lower()
        assert "yoghurt" not in line.lower()
    pescatarian = breakfast_protein_rule(DietType.PESCATARIAN)
    assert "eggs" in pescatarian
    assert "Greek yoghurt" in pescatarian
    assert "tofu scramble" in pescatarian
    assert "protein oats" in pescatarian


def _light_day_payload(
    *,
    calories: float,
    protein_g: float,
    diet: str,
) -> dict[str, object]:
    slots = (
        ("breakfast", "Protein oats"),
        ("lunch", "Zucchini pad thai"),
        ("dinner", "Cauliflower steaks"),
    )
    items = []
    recipes = []
    for slot, title in slots:
        items.append(
            {
                "slot_type": slot,
                "recipe_id": "generate_new",
                "recipe_title": title,
                "servings": 1,
            }
        )
        recipes.append(
            {
                "title": title,
                "slot_type": slot,
                "diet_type": diet,
                "prep_type": "steamed",
                "servings": 1,
                "primary_protein": "none",
                "ingredients": [
                    {"ingredient_name": f"{slot}-base", "quantity": 100, "unit": "g"}
                ],
                "steps": [{"step_number": 1, "instruction": "Prep."}],
                "nutrition_per_serving": {
                    "calories_kcal": calories,
                    "protein_g": protein_g,
                    "fat_g": 5,
                    "carbohydrates_g": (calories - (4 * protein_g + 9 * 5)) / 4,
                    "fiber_g": 4,
                },
            }
        )
    return {"days": [{"day_number": 1, "items": items}], "generated_recipes": recipes}


class _PromptClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.calls = 0
        self.systems: list[str] = []
        self.payload = payload

    async def complete(self, *args: object, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        system = kwargs.get("system")
        self.systems.append(system if isinstance(system, str) else "")
        block = SimpleNamespace(
            type="tool_use", name="output_plan", input=self.payload
        )
        return SimpleNamespace(
            content=[block],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


def _profile_for(
    *,
    diet: DietType,
    calorie_target: int | None,
    protein_g_target: int | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=calorie_target,
        protein_g_target=protein_g_target,
        carbs_g_target=None,
        fat_g_target=None,
        fiber_g_target=None,
        diet_type=diet,
    )


async def _generate_light_plan(
    *,
    diet: DietType,
    calorie_target: int | None,
    protein_g_target: int | None,
    meal_calories: float,
    meal_protein: float,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[GeneratedPlanData, _PromptClient]:
    monkeypatch.setattr(
        "agent.plan_generator.settings.plan_assigner_polish", False
    )
    client = _PromptClient(
        _light_day_payload(
            calories=meal_calories,
            protein_g=meal_protein,
            diet=diet.value,
        )
    )
    search = SimpleNamespace(planning_candidates=AsyncMock(return_value=[]))
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=search,  # type: ignore[arg-type]
    )
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=1,
        diet_type=diet,
        cooking_type=CookingType.COOKED_100,
        calorie_target=calorie_target,
        protein_g_target=(
            Decimal(protein_g_target) if protein_g_target is not None else None
        ),
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        trace_id="under-target",
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
    ):
        profiles.return_value.get_profile = AsyncMock(
            return_value=_profile_for(
                diet=diet,
                calorie_target=calorie_target,
                protein_g_target=protein_g_target,
            )
        )
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.list_recipes = AsyncMock(
            return_value=SimpleNamespace(data=[])
        )
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={})

        class _Rows:
            def scalars(self) -> _Rows:
                return self

            def all(self) -> list[object]:
                return []

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        result = await agent.generate(job, db=db)
    return result, client


@pytest.mark.asyncio
async def test_vegan_prompt_retries_once_when_the_day_is_far_off_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, client = await _generate_light_plan(
        diet=DietType.VEGAN,
        calorie_target=2000,
        protein_g_target=80,
        meal_calories=200,
        meal_protein=5,
        monkeypatch=monkeypatch,
    )
    assert client.calls == 2
    system = client.systems[0]
    assert breakfast_protein_rule(DietType.VEGAN) in system
    assert "The same dish (same ref or same generated title) never appears twice" in system
    assert "Breakfast slots take only breakfast dishes" in system
    assert "diet_type is this plan's chosen diet" in system
    assert "Breakfast is lighter; lunch and dinner carry most of the day's calories." in system
    assert "Leftovers may repeat on non-consecutive days" in system
    assert "Never repeat a juice or smoothie within the same day." in system
    assert "Aim each day within ±10% of its calorie target (and protein target when set)." in system
    assert "nudge servings" not in system
    assert "reuse the same title" not in system
    assert "one-third" not in system
    assert "eggs" not in system.lower()
    assert "yoghurt" not in system.lower()
    notes = result.review_notes or ""
    assert "Day 1 off target" in notes
    assert "Day 1 under target: kcal short by 1400" in notes
    assert "Day 1 under target: protein short by 65" in notes
    by_slot = {item.slot_type: item.recipe_title for item in result.days[0].items}
    assert by_slot["breakfast"] == "Protein oats"
    assert by_slot["lunch"] == "Zucchini pad thai"
    assert by_slot["dinner"] == "Cauliflower steaks"


@pytest.mark.asyncio
async def test_pescatarian_prompt_lists_eggs_and_yoghurt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _result, client = await _generate_light_plan(
        diet=DietType.PESCATARIAN,
        calorie_target=600,
        protein_g_target=15,
        meal_calories=200,
        meal_protein=5,
        monkeypatch=monkeypatch,
    )
    assert client.calls == 1
    system = client.systems[0]
    assert breakfast_protein_rule(DietType.PESCATARIAN) in system
    assert "eggs" in system
    assert "Greek yoghurt" in system


@pytest.mark.asyncio
async def test_day_with_no_target_has_no_under_target_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, client = await _generate_light_plan(
        diet=DietType.VEGAN,
        calorie_target=None,
        protein_g_target=None,
        meal_calories=200,
        meal_protein=5,
        monkeypatch=monkeypatch,
    )
    assert client.calls == 1
    assert "under target" not in (result.review_notes or "")
