"""Plan invariants for layout, types, calories, and stored rows. No model calls."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from agent.plan_generator import PlanGeneratorAgent
from db.models import (
    CookingType,
    DietType,
    JuiceTime,
    PlanDay,
    PlanItem,
    PlanItemSource,
    PlanSlot,
    PreparationType,
    RecipeType,
    RecipeUsagePolicy,
)
from exceptions import PlanGenerationFailedError
from planning.skeleton import JuiceSlotConfig, Pin, PlanSkeleton, build_skeleton
from schemas.agent import GeneratedPlanData, PlanGenerationJob
from schemas.plans import GeneratedPlanData as StoredPlan
from schemas.plans import GeneratedPlanDay, GeneratedPlanItem
from services.plan_service import PlanService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from validation.layout_guard import (
    PinnedSlot,
    check_layout,
    consecutive_main_dish_notes,
    match_skeleton,
    slot_kind,
)
from worker.agent_to_service import map_generated_plan

from tests.factories import make_plan, make_recipe, make_user


def assert_plan_invariants(
    plan: GeneratedPlanData,
    skeleton: PlanSkeleton,
    *,
    plan_diet: str | None = None,
    candidate_roles: Mapping[UUID, list[str]] | None = None,
    candidate_types: Mapping[UUID, str] | None = None,
    candidate_titles: Mapping[UUID, str] | None = None,
    pinned_slots: set[PinnedSlot] | None = None,
) -> None:
    """Structural checks for a plan that has already been stamped onto its skeleton.

    TODO(E4): diet_checker. plan_diet is accepted and not enforced until that
    checker exists.
    """
    _ = plan_diet
    roles = candidate_roles or {}
    types = candidate_types or {}
    titles = candidate_titles or {}
    pins = pinned_slots or set()
    pairs, coverage_errors = match_skeleton(plan, skeleton)
    assert coverage_errors == []
    assert len(pairs) == len(skeleton.slots)
    item_count = sum(len(day.items) for day in plan.days)
    assert item_count == len(skeleton.slots)
    layout = check_layout(
        plan,
        candidate_roles=roles,
        candidate_titles=titles,
        candidate_types=types,
        pinned_slots=pins,
        skeleton=skeleton,
    )
    assert layout.errors == []

    for slot, item in pairs:
        assert slot_kind(item.slot_type) == slot.kind
        if slot.kind == "meal":
            assert item.juice_time is None
            assert item.juice_size_ml is None
        if slot.juice_time is not None:
            assert item.juice_time is not None
            assert item.juice_time.value == slot.juice_time
        if slot.juice_size_ml is not None:
            assert item.juice_size_ml == slot.juice_size_ml
        assert item.servings >= 1
        nutrition = _per_serving(plan, item.recipe_id)
        if nutrition is not None and not item.nutrition_unknown:
            calories, protein, carbs, fat, fiber = nutrition
            assert _close(item.calories, calories * item.servings)
            assert _close(item.protein_g, protein * item.servings)
            assert _close(item.carbs_g, carbs * item.servings)
            assert _close(item.fat_g, fat * item.servings)
            assert _close(item.fiber_g, fiber * item.servings)

    _assert_stored_recipe_types(plan, types)
    for note in consecutive_main_dish_notes(plan):
        assert plan.review_notes is not None
        assert note in plan.review_notes


def _assert_stored_recipe_types(
    plan: GeneratedPlanData,
    candidate_types: Mapping[UUID, str],
) -> None:
    generated_ids = {
        recipe.assigned_id
        for recipe in plan.generated_recipes
        if recipe.assigned_id is not None
    }
    saved_ids = {
        item.recipe_id
        for day in plan.days
        for item in day.items
        if isinstance(item.recipe_id, UUID) and item.recipe_id not in generated_ids
    }
    mapped = map_generated_plan(plan, saved_ids=saved_ids)
    by_id = {
        recipe.assigned_id: recipe
        for recipe in plan.generated_recipes
        if recipe.assigned_id is not None
    }
    for day, mapped_day in zip(plan.days, mapped.days, strict=True):
        for item, stored in zip(day.items, mapped_day.items, strict=True):
            if not isinstance(item.recipe_id, UUID):
                continue
            generated = by_id.get(item.recipe_id)
            if generated is not None:
                assert stored.recipe_type.value == slot_kind(generated.slot_type)
                continue
            raw = candidate_types.get(item.recipe_id)
            if raw:
                assert stored.recipe_type.value == slot_kind(raw)


def _per_serving(
    plan: GeneratedPlanData, recipe_id: object
) -> tuple[float, float, float, float, float] | None:
    if not isinstance(recipe_id, UUID):
        return None
    for recipe in plan.generated_recipes:
        if recipe.assigned_id != recipe_id:
            continue
        nutrition = recipe.nutrition_per_serving
        return (
            float(nutrition.calories_kcal),
            float(nutrition.protein_g),
            float(nutrition.carbohydrates_g),
            float(nutrition.fat_g),
            float(nutrition.fiber_g),
        )
    return None


def _close(actual: float | None, expected: float) -> bool:
    if actual is None:
        return False
    return abs(float(actual) - expected) <= 1e-6 * max(1.0, abs(expected))


def _recipe(title: str, slot: str, *, calories: float = 400) -> dict[str, object]:
    protein = 20.0
    fat = 10.0
    carbs = (calories - (4 * protein + 9 * fat)) / 4
    return {
        "title": title,
        "slot_type": slot,
        "diet_type": "pescatarian",
        "prep_type": "steamed",
        "servings": 1,
        "primary_protein": "none",
        "ingredients": [{"ingredient_name": "oats", "quantity": 1, "unit": "cup"}],
        "steps": [{"step_number": 1, "instruction": "Cook."}],
        "nutrition_per_serving": {
            "calories_kcal": calories,
            "protein_g": protein,
            "fat_g": fat,
            "carbohydrates_g": carbs,
            "fiber_g": 5,
        },
    }


def _item(slot: str, title: str, *, juice_time: str | None = None) -> dict[str, object]:
    row: dict[str, object] = {
        "slot_type": slot,
        "recipe_id": "generate_new",
        "recipe_title": title,
        "servings": 1,
    }
    if juice_time is not None:
        row["juice_time"] = juice_time
    return row


class _CountingClient:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.calls = 0
        self.payload = payload

    async def complete(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if self.calls > 2:
            raise AssertionError("plan generation billed a third model call")
        if self.payload is None:
            raise AssertionError("model must not be called")
        block = SimpleNamespace(type="tool_use", name="output_plan", input=self.payload)
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


def _profile(*, calories: int | None = 2000) -> SimpleNamespace:
    return SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=calories,
        protein_g_target=80,
        carbs_g_target=250,
        fat_g_target=70,
        fiber_g_target=30,
        diet_type=DietType.PESCATARIAN,
    )


async def _generate(
    payload: dict[str, object] | None,
    *,
    days: int = 1,
    include_juicing: bool = False,
    calorie_target: int | None = 2000,
    saved: dict[str, object] | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
    calls: list[_CountingClient] | None = None,
) -> tuple[GeneratedPlanData, _CountingClient]:
    if monkeypatch is not None:
        monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    client = _CountingClient(payload if saved is None else None)
    if calls is not None:
        calls.append(client)
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=days,
        diet_type=DietType.PESCATARIAN,
        cooking_type=CookingType.COOKED_100,
        calorie_target=calorie_target,
        protein_g_target=Decimal(80) if calorie_target is not None else None,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=include_juicing,
        trace_id="invariants",
    )
    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
    ):
        profiles.return_value.get_profile = AsyncMock(
            return_value=_profile(calories=calorie_target)
        )
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        result = await agent.generate(job, db=db, saved_llm_output=saved)
    return result, client


def _meals_payload(
    days: int = 1,
    *,
    calories: float = 400,
    lunch_title: str | None = None,
) -> dict[str, object]:
    plan_days: list[dict[str, object]] = []
    recipes: list[dict[str, object]] = []
    for day in range(1, days + 1):
        items = []
        for slot in ("breakfast", "lunch", "dinner"):
            if slot == "lunch" and lunch_title is not None:
                title = lunch_title
            else:
                title = f"Day{day} {slot}"
            items.append(_item(slot, title))
            if not any(recipe["title"] == title for recipe in recipes):
                recipes.append(_recipe(title, slot, calories=calories))
        plan_days.append({"day_number": day, "items": items})
    return {"days": plan_days, "generated_recipes": recipes}


def _juicing_payload() -> dict[str, object]:
    items = [
        _item("breakfast", "Oats"),
        _item("lunch", "Salad"),
        _item("dinner", "Steaks"),
        _item("juice", "Green", juice_time="morning"),
        _item("juice", "Ginger", juice_time="pre_lunch"),
    ]
    recipes = [
        _recipe("Oats", "breakfast"),
        _recipe("Salad", "lunch"),
        _recipe("Steaks", "dinner"),
        _recipe("Green", "juice"),
        _recipe("Ginger", "juice"),
    ]
    return {"days": [{"day_number": 1, "items": items}], "generated_recipes": recipes}


@pytest.mark.asyncio
async def test_juicing_on_plan_matches_skeleton_and_pre_lunch_is_250(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    result, client = await _generate(
        _juicing_payload(),
        include_juicing=True,
        calorie_target=2000,
        monkeypatch=monkeypatch,
    )
    assert client.calls == 1
    skeleton = build_skeleton(
        duration_days=1,
        juicing_enabled=True,
        juice_configs=None,
        pins=(),
    )
    juices = [slot for slot in skeleton.slots if slot.kind == "juice"]
    assert [(slot.juice_time, slot.juice_size_ml) for slot in juices] == [
        ("morning", 500),
        ("pre_lunch", 250),
    ]
    assert_plan_invariants(result, skeleton, plan_diet="pescatarian")
    pre_lunch = next(
        item
        for day in result.days
        for item in day.items
        if item.juice_time == JuiceTime.PRE_LUNCH
    )
    assert pre_lunch.juice_size_ml == 250
    assert pre_lunch.slot_type == "juice"
    for day in result.days:
        for item in day.items:
            if item.slot_type == "juice":
                assert slot_kind(item.slot_type) == "juice"
            else:
                assert slot_kind(item.slot_type) == "meal"


@pytest.mark.asyncio
async def test_day_more_than_20_percent_off_retries_once_then_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, client = await _generate(
        _meals_payload(calories=200),
        calorie_target=2000,
        monkeypatch=monkeypatch,
    )
    assert client.calls == 2
    notes = result.review_notes or ""
    assert "Day 1 off target" in notes
    skeleton = build_skeleton(
        duration_days=1,
        juicing_enabled=False,
        juice_configs=None,
        pins=(),
    )
    assert_plan_invariants(result, skeleton)


@pytest.mark.asyncio
async def test_day_exactly_20_percent_off_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, client = await _generate(
        _meals_payload(calories=240),
        calorie_target=900,
        monkeypatch=monkeypatch,
    )
    assert client.calls == 1
    assert "off target" not in (result.review_notes or "")


@pytest.mark.asyncio
async def test_day_without_a_calorie_target_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _result, client = await _generate(
        _meals_payload(calories=200),
        calorie_target=None,
        monkeypatch=monkeypatch,
    )
    assert client.calls == 1


@pytest.mark.asyncio
async def test_missing_skeleton_slot_retries_once_then_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _meals_payload()
    day = payload["days"]
    assert isinstance(day, list)
    items = day[0]["items"]
    assert isinstance(items, list)
    day[0]["items"] = [item for item in items if item["slot_type"] != "dinner"]
    calls: list[_CountingClient] = []
    with pytest.raises(PlanGenerationFailedError, match="Layout:"):
        await _generate(payload, monkeypatch=monkeypatch, calls=calls)
    assert calls[0].calls == 2


@pytest.mark.asyncio
async def test_type_mismatch_retries_once_then_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _juicing_payload()
    recipes = payload["generated_recipes"]
    assert isinstance(recipes, list)
    for recipe in recipes:
        if recipe["title"] == "Green":
            recipe["slot_type"] = "lunch"
    calls: list[_CountingClient] = []
    with pytest.raises(PlanGenerationFailedError, match="Layout:"):
        await _generate(
            payload,
            include_juicing=True,
            monkeypatch=monkeypatch,
            calls=calls,
        )
    assert calls[0].calls == 2


@pytest.mark.asyncio
async def test_bad_checkpoint_is_rejected_with_zero_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = {
        "output": _meals_payload(),
        "handles": {},
        "roles": {},
        "titles": {},
        "types": {},
    }
    output = saved["output"]
    assert isinstance(output, dict)
    days = output["days"]
    assert isinstance(days, list)
    days[0]["items"] = [
        item for item in days[0]["items"] if item["slot_type"] != "dinner"
    ]
    calls: list[_CountingClient] = []
    with pytest.raises(PlanGenerationFailedError, match="Layout:"):
        await _generate(None, saved=saved, monkeypatch=monkeypatch, calls=calls)
    assert calls[0].calls == 0


@pytest.mark.asyncio
async def test_same_main_dish_on_consecutive_days_is_a_soft_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, client = await _generate(
        _meals_payload(days=2, lunch_title="Zucchini pad thai"),
        days=2,
        calorie_target=1200,
        monkeypatch=monkeypatch,
    )
    assert client.calls == 1
    assert "Day 2 repeats Zucchini pad thai from day 1" in (result.review_notes or "")
    skeleton = build_skeleton(
        duration_days=2,
        juicing_enabled=False,
        juice_configs=None,
        pins=(),
    )
    assert_plan_invariants(result, skeleton)
    assert result.days


@pytest.mark.asyncio
async def test_layout_failure_never_bills_a_third_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _juicing_payload()
    recipes = payload["generated_recipes"]
    assert isinstance(recipes, list)
    for recipe in recipes:
        if recipe["title"] == "Oats":
            recipe["slot_type"] = "dinner"
    calls: list[_CountingClient] = []
    with pytest.raises(PlanGenerationFailedError, match="Layout:"):
        await _generate(
            payload, include_juicing=False, monkeypatch=monkeypatch, calls=calls
        )
    assert calls[0].calls == 2


@pytest.mark.asyncio
async def test_juicing_on_stored_item_slot_matches_recipe_type(
    db_session: AsyncSession,
) -> None:
    owner = await make_user(db_session, email="juice-layout@nouri.app")
    oats = await make_recipe(
        db_session, owner.id, name="Oats", recipe_type=RecipeType.MEAL, calories=400
    )
    salad = await make_recipe(
        db_session, owner.id, name="Salad", recipe_type=RecipeType.MEAL, calories=400
    )
    steaks = await make_recipe(
        db_session, owner.id, name="Steaks", recipe_type=RecipeType.MEAL, calories=400
    )
    green = await make_recipe(
        db_session,
        owner.id,
        name="Green",
        recipe_type=RecipeType.JUICE,
        calories=80,
        prep_method=PreparationType.JUICED,
    )
    ginger = await make_recipe(
        db_session,
        owner.id,
        name="Ginger",
        recipe_type=RecipeType.JUICE,
        calories=60,
        prep_method=PreparationType.JUICED,
    )
    plan = await make_plan(db_session, owner.id, num_days=1, with_meals=False)
    recipes = {
        oats.id: oats,
        salad.id: salad,
        steaks.id: steaks,
        green.id: green,
        ginger.id: ginger,
    }
    generated = StoredPlan(
        days=[
            GeneratedPlanDay(
                day_number=1,
                items=[
                    _stored(oats.id, PlanSlot.BREAKFAST, "Oats", calories=400),
                    _stored(salad.id, PlanSlot.LUNCH, "Salad", calories=400),
                    _stored(steaks.id, PlanSlot.DINNER, "Steaks", calories=400),
                    _stored(
                        green.id,
                        PlanSlot.JUICE,
                        "Green",
                        calories=80,
                        juice_time=JuiceTime.MORNING,
                        juice_size_ml=500,
                        recipe_type=RecipeType.MEAL,
                    ),
                    _stored(
                        ginger.id,
                        PlanSlot.JUICE,
                        "Ginger",
                        calories=60,
                        juice_time=JuiceTime.PRE_LUNCH,
                        juice_size_ml=250,
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
        await db_session.execute(select(PlanItem).where(PlanItem.plan_day_id == day.id))
    ).scalars().all()
    assert len(items) == 5
    for item in items:
        recipe = recipes[item.recipe_id]
        assert item.recipe_type == recipe.recipe_type
        if recipe.recipe_type == RecipeType.JUICE:
            assert item.slot == PlanSlot.JUICE
        else:
            assert item.slot in {PlanSlot.BREAKFAST, PlanSlot.LUNCH, PlanSlot.DINNER}
    green_item = next(item for item in items if item.recipe_id == green.id)
    assert green_item.recipe_type == RecipeType.JUICE
    assert green_item.juice_size_ml == 500
    ginger_item = next(item for item in items if item.recipe_id == ginger.id)
    assert ginger_item.juice_size_ml == 250


def _stored(
    recipe_id: UUID,
    slot: PlanSlot,
    title: str,
    *,
    calories: int,
    juice_time: JuiceTime | None = None,
    juice_size_ml: int | None = None,
    recipe_type: RecipeType = RecipeType.MEAL,
) -> GeneratedPlanItem:
    return GeneratedPlanItem(
        slot_type=slot,
        recipe_title=title,
        recipe_id=recipe_id,
        recipe_type=recipe_type,
        item_source=PlanItemSource.SAVED_RECIPE,
        calories=Decimal(calories),
        protein_g=Decimal(10),
        carbs_g=Decimal(20),
        fat_g=Decimal(5),
        fiber_g=Decimal(2),
        juice_time=juice_time,
        juice_size_ml=juice_size_ml,
    )


def test_custom_juice_sizes_are_what_the_skeleton_stores() -> None:
    skeleton = build_skeleton(
        duration_days=1,
        juicing_enabled=True,
        juice_configs=(
            JuiceSlotConfig(time_of_day="morning", size_ml=500, slot_order=0),
            JuiceSlotConfig(time_of_day="pre_lunch", size_ml=250, slot_order=1),
        ),
        pins=(Pin(1, "breakfast", uuid4(), "meal"),),
    )
    assert [slot.juice_size_ml for slot in skeleton.slots if slot.kind == "juice"] == [
        500,
        250,
    ]
