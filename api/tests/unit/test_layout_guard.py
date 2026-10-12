"""Layout guard — same-day repeats and breakfast roles. No model calls."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from db.models import DietType, JuiceTime, PreparationType
from planning.skeleton import build_skeleton
from schemas.agent import (
    GeneratedPlanData,
    GeneratedPlanDayAI,
    GeneratedPlanItemAI,
    GeneratedRecipeAI,
    NutritionPerServingAI,
    PlanSlotAI,
)
from validation.layout_guard import check_layout


def _nutrition() -> NutritionPerServingAI:
    return NutritionPerServingAI(
        calories_kcal=400,
        protein_g=20,
        fat_g=10,
        carbohydrates_g=30,
        fiber_g=5,
    )


def _generated(title: str, slot_type: str) -> GeneratedRecipeAI:
    return GeneratedRecipeAI(
        title=title,
        slot_type=slot_type,
        diet_type=DietType.PESCATARIAN,
        prep_type=PreparationType.STEAMED,
        nutrition_per_serving=_nutrition(),
    )


def _item(
    slot: PlanSlotAI,
    title: str,
    recipe_id: UUID | Literal["generate_new"],
    *,
    juice_time: JuiceTime | None = None,
) -> GeneratedPlanItemAI:
    return GeneratedPlanItemAI(
        slot_type=slot,
        recipe_id=recipe_id,
        recipe_title=title,
        juice_time=juice_time,
    )


def _pin(
    day: int,
    slot: str,
    order: int,
    recipe_id: UUID,
    juice_time: str = "",
) -> tuple[int, str, int, UUID, str]:
    return (day, slot, order, recipe_id, juice_time)


def _plan(
    items: list[GeneratedPlanItemAI],
    generated: list[GeneratedRecipeAI] | None = None,
) -> GeneratedPlanData:
    return GeneratedPlanData(
        days=[GeneratedPlanDayAI(day_number=1, items=items)],
        generated_recipes=generated or [],
    )


def test_same_day_salmon_is_an_error() -> None:
    salmon = uuid4()
    result = check_layout(
        _plan(
            [
                _item("lunch", "Salmon", salmon),
                _item("dinner", "Salmon", salmon),
            ]
        ),
        candidate_roles={salmon: ["lunch", "dinner"]},
        candidate_titles={salmon: "Salmon"},
        pinned_slots=set(),
    )
    assert result.errors
    assert any("Salmon" in error and "twice" in error for error in result.errors)
    assert result.warnings == []
    titled = check_layout(
        _plan(
            [
                _item("lunch", "Salmon", "generate_new"),
                _item("dinner", " salmon ", "generate_new"),
            ]
        ),
        candidate_roles={},
        candidate_titles={},
        pinned_slots=set(),
    )
    assert titled.errors
    assert titled.warnings == []


def test_dinner_only_saved_recipe_at_breakfast_is_an_error() -> None:
    steak = uuid4()
    result = check_layout(
        _plan([_item("breakfast", "Steaks", steak)]),
        candidate_roles={steak: ["dinner"]},
        candidate_titles={steak: "Steaks"},
        pinned_slots=set(),
    )
    assert result.errors
    assert result.warnings == []


def test_generated_dinner_at_breakfast_is_an_error() -> None:
    result = check_layout(
        _plan(
            [_item("breakfast", "Steaks", "generate_new")],
            [_generated("Steaks", "dinner")],
        ),
        candidate_roles={},
        candidate_titles={},
        pinned_slots=set(),
    )
    assert any("slot_type" in error for error in result.errors)
    assert result.warnings == []


def test_lunch_and_dinner_swap_passes() -> None:
    lunch = uuid4()
    dinner = uuid4()
    result = check_layout(
        _plan(
            [
                _item("lunch", "Steaks", dinner),
                _item("dinner", "Pad Thai", lunch),
            ]
        ),
        candidate_roles={lunch: ["lunch"], dinner: ["dinner"]},
        candidate_titles={lunch: "Pad Thai", dinner: "Steaks"},
        pinned_slots=set(),
    )
    assert result.errors == []
    assert result.warnings == []


def test_pinned_non_breakfast_at_breakfast_passes() -> None:
    steak = uuid4()
    result = check_layout(
        _plan([_item("breakfast", "Steaks", steak)]),
        candidate_roles={steak: ["dinner"]},
        candidate_titles={steak: "Steaks"},
        pinned_slots={_pin(1, "breakfast", 0, steak)},
    )
    assert result.errors == []
    assert result.warnings == []


def test_same_juice_twice_in_a_day_is_an_error() -> None:
    green = uuid4()
    result = check_layout(
        _plan(
            [
                _item("juice", "Green", green),
                _item("extra_morning", "Green", green),
            ]
        ),
        candidate_roles={},
        candidate_titles={green: "Green"},
        pinned_slots=set(),
    )
    assert result.errors
    assert any("Green" in error and "twice" in error for error in result.errors)


def test_same_juice_on_different_days_passes() -> None:
    green = uuid4()
    result = check_layout(
        GeneratedPlanData(
            days=[
                GeneratedPlanDayAI(
                    day_number=1, items=[_item("juice", "Green", green)]
                ),
                GeneratedPlanDayAI(
                    day_number=2, items=[_item("juice", "Green", green)]
                ),
            ]
        ),
        candidate_roles={},
        candidate_titles={green: "Green"},
        candidate_types={green: "juice"},
        pinned_slots=set(),
    )
    assert result.errors == []
    assert result.warnings == []


def test_pinned_morning_juice_repeated_at_pre_lunch_is_an_error() -> None:
    green = uuid4()
    result = check_layout(
        _plan(
            [
                _item("juice", "Green", green, juice_time=JuiceTime.MORNING),
                _item(
                    "juice",
                    "Green",
                    "generate_new",
                    juice_time=JuiceTime.PRE_LUNCH,
                ),
            ]
        ),
        candidate_roles={},
        candidate_titles={green: "Green"},
        pinned_slots={_pin(1, "juice", 0, green, "morning")},
    )
    assert result.errors
    assert any("twice" in error for error in result.errors)


def test_pinned_morning_juice_and_a_different_pre_lunch_passes() -> None:
    green = uuid4()
    result = check_layout(
        _plan(
            [
                _item("juice", "Green", green, juice_time=JuiceTime.MORNING),
                _item(
                    "juice",
                    "Ginger",
                    "generate_new",
                    juice_time=JuiceTime.PRE_LUNCH,
                ),
            ],
            [_generated("Ginger", "juice")],
        ),
        candidate_roles={},
        candidate_titles={green: "Green"},
        candidate_types={green: "juice"},
        pinned_slots={_pin(1, "juice", 0, green, "morning")},
    )
    assert result.errors == []
    assert result.warnings == []


def test_pinned_dish_repeated_in_another_slot_is_an_error() -> None:
    salmon = uuid4()
    result = check_layout(
        _plan(
            [
                _item("breakfast", "Salmon Bowl", salmon),
                _item("lunch", "salmon  bowl", "generate_new"),
            ]
        ),
        candidate_roles={salmon: ["breakfast"]},
        candidate_titles={salmon: "Salmon Bowl"},
        pinned_slots={_pin(1, "breakfast", 0, salmon)},
    )
    assert result.errors
    assert any("twice" in error for error in result.errors)


def test_two_pins_of_the_same_recipe_do_not_error() -> None:
    salmon = uuid4()
    result = check_layout(
        _plan(
            [
                _item("breakfast", "Salmon Bowl", salmon),
                _item("lunch", "Salmon Bowl", salmon),
            ]
        ),
        candidate_roles={salmon: ["breakfast", "lunch"]},
        candidate_titles={salmon: "Salmon Bowl"},
        pinned_slots={
            _pin(1, "breakfast", 0, salmon),
            _pin(1, "lunch", 1, salmon),
        },
    )
    assert result.errors == []
    assert result.warnings == []


def test_saved_and_generated_titles_match_after_normalizing() -> None:
    salmon = uuid4()
    result = check_layout(
        _plan(
            [
                _item("lunch", "ignored label", salmon),
                _item("dinner", "salmon  bowl", "generate_new"),
            ]
        ),
        candidate_roles={salmon: ["lunch", "dinner"]},
        candidate_titles={salmon: "Salmon Bowl"},
        pinned_slots=set(),
    )
    assert result.errors
    assert any("twice" in error for error in result.errors)


def test_saved_recipe_with_no_roles_at_breakfast_is_an_error() -> None:
    oats = uuid4()
    unknown = uuid4()
    empty = check_layout(
        _plan([_item("breakfast", "Oats", oats)]),
        candidate_roles={oats: []},
        candidate_titles={oats: "Oats"},
        pinned_slots=set(),
    )
    assert empty.errors
    assert any("no meal roles" in error for error in empty.errors)
    assert empty.warnings == []
    missing = check_layout(
        _plan([_item("breakfast", "Bowl", unknown)]),
        candidate_roles={},
        candidate_titles={},
        pinned_slots=set(),
    )
    assert missing.errors
    assert any("no meal roles" in error for error in missing.errors)
    assert missing.warnings == []


def test_pinned_role_less_breakfast_is_exempt() -> None:
    oats = uuid4()
    result = check_layout(
        _plan([_item("breakfast", "Oats", oats)]),
        candidate_roles={oats: []},
        candidate_titles={oats: "Oats"},
        pinned_slots={_pin(1, "breakfast", 0, oats)},
    )
    assert result.errors == []
    assert result.warnings == []


def test_meal_in_a_juice_slot_is_an_error() -> None:
    oats = uuid4()
    result = check_layout(
        _plan([_item("juice", "Oats", oats)]),
        candidate_roles={},
        candidate_titles={oats: "Oats"},
        candidate_types={oats: "meal"},
        pinned_slots=set(),
    )
    assert any("is a meal, not a juice" in error for error in result.errors)


def test_generated_juice_in_a_breakfast_slot_is_an_error() -> None:
    result = check_layout(
        _plan(
            [_item("breakfast", "Green", "generate_new")],
            [_generated("Green", "juice")],
        ),
        candidate_roles={},
        candidate_titles={},
        pinned_slots=set(),
    )
    assert any("is a juice, not a meal" in error for error in result.errors)


def test_juice_in_a_juice_slot_passes() -> None:
    green = uuid4()
    result = check_layout(
        _plan([_item("juice", "Green", green, juice_time=JuiceTime.MORNING)]),
        candidate_roles={},
        candidate_titles={green: "Green"},
        candidate_types={green: "juice"},
        pinned_slots=set(),
    )
    assert result.errors == []


def test_skeleton_missing_slot_and_extra_item_are_errors() -> None:
    skeleton = build_skeleton(
        duration_days=1,
        juicing_enabled=False,
        juice_configs=None,
        pins=(),
    )
    missing = check_layout(
        _plan(
            [
                _item("breakfast", "Oats", "generate_new"),
                _item("lunch", "Salad", "generate_new"),
            ]
        ),
        candidate_roles={},
        candidate_titles={},
        pinned_slots=set(),
        skeleton=skeleton,
    )
    assert any("missing dinner" in error for error in missing.errors)
    extra = check_layout(
        _plan(
            [
                _item("breakfast", "Oats", "generate_new"),
                _item("lunch", "Salad", "generate_new"),
                _item("dinner", "Steaks", "generate_new"),
                _item("snack", "Nuts", "generate_new"),
            ]
        ),
        candidate_roles={},
        candidate_titles={},
        pinned_slots=set(),
        skeleton=skeleton,
    )
    assert any("extra snack" in error for error in extra.errors)
