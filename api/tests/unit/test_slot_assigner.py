"""SlotAssigner — deterministic placement of recipes-with-known-macros."""

from __future__ import annotations

from uuid import uuid4

from validation.slot_assigner import AssignableRecipe, SlotAssigner, SlotSpec
from validation.types import (
    ExclusionView,
    MacroTargets,
    RecipeIngredientView,
)


def _recipe(
    title: str,
    *,
    calories: float = 670.0,
    protein_g: float = 27.0,
    carbs_g: float = 83.0,
    fat_g: float = 23.0,
    fiber_g: float = 10.0,
    prep_method: str = "raw",
    primary_protein: str = "legumes",
    slot_hint: str | None = None,
    ingredient: str = "chickpeas",
    is_saved: bool = False,
) -> AssignableRecipe:
    return AssignableRecipe(
        recipe_id=uuid4(),
        title=title,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        prep_method=prep_method,
        primary_protein=primary_protein,
        ingredients=(RecipeIngredientView(name=ingredient, ingredient_id=uuid4()),),
        slot_hint=slot_hint,
        is_saved=is_saved,
    )


def _targets() -> MacroTargets:
    return MacroTargets(
        calories=2000.0,
        protein_g=80.0,
        carbs_g=250.0,
        fat_g=70.0,
        fiber_g=30.0,
    )


def _week_slots(days: int = 3) -> list[SlotSpec]:
    slots: list[SlotSpec] = []
    for day in range(1, days + 1):
        for slot in ("breakfast", "lunch", "dinner"):
            slots.append(SlotSpec(day_number=day, slot=slot))
    return slots


def test_assigner_hits_macro_tolerance_with_balanced_pool() -> None:
    pool = [
        _recipe(
            f"meal-{i}",
            primary_protein="none",
            prep_method="raw" if i < 4 else "steamed",
            slot_hint=("breakfast", "lunch", "dinner")[i % 3],
            ingredient=f"ing-{i}",
        )
        for i in range(9)
    ]
    result = SlotAssigner().assign(_week_slots(3), pool, _targets(), "raw_50_cooked_50")
    assert result.feasible is True
    assert len(result.days) == 3
    for day in result.days:
        assert len(day.items) == 3
        calories = sum(i.calories or 0 for i in day.items)
        assert 1600 <= calories <= 2400
        for item in day.items:
            assert item.calories is not None
            assert item.calories > 0


def test_assigner_honors_hard_pin() -> None:
    pool = [
        _recipe(f"meal-{i}", ingredient=f"ing-{i}", primary_protein="none", prep_method="raw" if i < 4 else "steamed")
        for i in range(9)
    ]
    pinned = pool[0]
    slots = _week_slots(3)
    slots[0] = SlotSpec(day_number=1, slot="breakfast", pinned_recipe_id=pinned.recipe_id)
    result = SlotAssigner().assign(slots, pool, _targets(), "raw_50_cooked_50")
    assert result.feasible is True
    breakfast = next(i for i in result.days[0].items if i.slot == "breakfast")
    assert breakfast.recipe_id == pinned.recipe_id


def test_assigner_rejects_excluded_recipe() -> None:
    peanut_id = uuid4()
    dirty = _recipe("satay", ingredient="peanuts")
    dirty = AssignableRecipe(
        recipe_id=dirty.recipe_id,
        title=dirty.title,
        calories=dirty.calories,
        protein_g=dirty.protein_g,
        carbs_g=dirty.carbs_g,
        fat_g=dirty.fat_g,
        fiber_g=dirty.fiber_g,
        prep_method=dirty.prep_method,
        primary_protein=dirty.primary_protein,
        ingredients=(RecipeIngredientView(name="peanuts", ingredient_id=peanut_id),),
        slot_hint=dirty.slot_hint,
    )
    pool = [
        dirty,
        *[
            _recipe(f"clean-{i}", ingredient=f"ing-{i}", primary_protein="none", prep_method="raw" if i < 4 else "steamed")
            for i in range(9)
        ],
    ]
    result = SlotAssigner().assign(
        _week_slots(3),
        pool,
        _targets(),
        "raw_50_cooked_50",
        exclusions=(ExclusionView(raw_name="peanuts", ingredient_id=peanut_id),),
    )
    assert result.feasible is True
    ids = {i.recipe_id for d in result.days for i in d.items}
    assert dirty.recipe_id not in ids


def test_smoothie_slot_does_not_scale_servings() -> None:
    recipe = _recipe("green smoothie", calories=400.0, slot_hint="smoothie")
    result = SlotAssigner().assign(
        [SlotSpec(day_number=1, slot="smoothie")],
        [recipe],
        MacroTargets(calories=2000.0, protein_g=0.0, carbs_g=0.0, fat_g=0.0, fiber_g=0.0),
        "cooked_100",
    )
    assert result.feasible is True
    assert result.days[0].items[0].calories == 400.0


def test_assigner_infeasible_when_pool_too_light() -> None:
    pool = [
        _recipe(f"juice-{i}", calories=40.0, protein_g=1.0, carbs_g=8.0, fat_g=0.0, fiber_g=1.0)
        for i in range(6)
    ]
    result = SlotAssigner().assign(_week_slots(3), pool, _targets(), "cooked_100")
    # Soft-accept: still returns a plan, with calorie shortfall as warnings.
    assert result.feasible is True
    assert result.days
    assert result.warnings
    assert any("calories" in w.lower() or "infeasible pool" in w.lower() for w in result.warnings)


def test_prefer_saved_places_library_recipes_first() -> None:
    saved = [
        _recipe(
            f"saved-{i}",
            is_saved=True,
            primary_protein="none",
            prep_method="steamed",
            slot_hint=("breakfast", "lunch", "dinner")[i],
            ingredient=f"saved-ing-{i}",
        )
        for i in range(3)
    ]
    generated = [
        _recipe(
            f"new-{i}",
            is_saved=False,
            calories=680.0,
            primary_protein="none",
            prep_method="steamed",
            ingredient=f"new-ing-{i}",
        )
        for i in range(9)
    ]
    result = SlotAssigner().assign(
        _week_slots(3),
        saved + generated,
        _targets(),
        "cooked_100",
        sourcing_policy="prefer_saved",
    )
    assert result.feasible is True
    saved_ids = {r.recipe_id for r in saved}
    for day in result.days:
        for item in day.items:
            assert item.recipe_id in saved_ids


def test_prefer_new_places_generated_recipes_first() -> None:
    saved = [
        _recipe(
            f"saved-{i}",
            is_saved=True,
            primary_protein="none",
            prep_method="steamed",
            ingredient=f"saved-ing-{i}",
        )
        for i in range(3)
    ]
    generated = [
        _recipe(
            f"new-{i}",
            is_saved=False,
            primary_protein="none",
            prep_method="steamed",
            slot_hint=("breakfast", "lunch", "dinner")[i % 3],
            ingredient=f"new-ing-{i}",
        )
        for i in range(9)
    ]
    result = SlotAssigner().assign(
        _week_slots(3),
        saved + generated,
        _targets(),
        "cooked_100",
        sourcing_policy="prefer_new",
    )
    assert result.feasible is True
    generated_ids = {r.recipe_id for r in generated}
    for day in result.days:
        for item in day.items:
            assert item.recipe_id in generated_ids


def test_assigner_scales_light_recipes_to_hit_calorie_floor() -> None:
    """LLM often emits ~350 kcal meals; servings must scale to reach ~2000 kcal days."""
    pool = [
        _recipe(
            f"light-{i}",
            calories=350.0,
            protein_g=12.0,
            carbs_g=45.0,
            fat_g=10.0,
            fiber_g=6.0,
            primary_protein="none",
            prep_method="steamed" if i % 3 else "raw",
            slot_hint=("breakfast", "lunch", "dinner")[i % 3],
            ingredient=f"light-ing-{i}",
        )
        for i in range(12)
    ]
    targets = MacroTargets(
        calories=2050.0,
        protein_g=0.0,
        carbs_g=0.0,
        fat_g=0.0,
        fiber_g=0.0,
    )
    result = SlotAssigner().assign(_week_slots(3), pool, targets, "cooked_100")
    assert result.feasible is True
    for day in result.days:
        calories = sum(i.calories or 0 for i in day.items)
        assert calories >= 2050 * 0.80


def test_assigner_ignores_unset_macro_targets() -> None:
    pool = [
        _recipe(
            f"meal-{i}",
            calories=700.0,
            primary_protein="none",
            prep_method="steamed",
            slot_hint=("breakfast", "lunch", "dinner")[i % 3],
            ingredient=f"ing-{i}",
        )
        for i in range(9)
    ]
    targets = MacroTargets(
        calories=2000.0,
        protein_g=0.0,
        carbs_g=0.0,
        fat_g=0.0,
        fiber_g=0.0,
    )
    result = SlotAssigner().assign(_week_slots(3), pool, targets, "cooked_100")
    assert result.feasible is True
    assert not any("target is 0" in e for e in result.errors)


def test_assigner_balances_raw_80_cooking_type() -> None:
    pool = [
        _recipe(
            f"meal-{i}",
            calories=680.0,
            primary_protein="none",
            prep_method="raw" if i < 7 else "steamed",
            slot_hint=("breakfast", "lunch", "dinner")[i % 3],
            ingredient=f"ing-{i}",
        )
        for i in range(12)
    ]
    result = SlotAssigner().assign(
        _week_slots(3), pool, _targets(), "raw_80_cooked_20"
    )
    assert result.feasible is True
    items = [i for d in result.days for i in d.items]
    raw = sum(1 for i in items if i.prep_method == "raw")
    pct = (raw / len(items)) * 100.0
    assert abs(pct - 80.0) <= 10.0 + 1e-6


def test_assigner_never_moves_lunch_or_dinner_into_breakfast() -> None:
    oats = _recipe("Oats", slot_hint="breakfast", calories=200.0, ingredient="oats")
    pad_thai = _recipe(
        "Pad Thai", slot_hint="lunch", calories=900.0, ingredient="zucchini"
    )
    steaks = _recipe(
        "Steaks", slot_hint="dinner", calories=900.0, ingredient="cauliflower"
    )
    result = SlotAssigner().assign(
        [
            SlotSpec(day_number=1, slot="breakfast"),
            SlotSpec(day_number=1, slot="lunch"),
            SlotSpec(day_number=1, slot="dinner"),
        ],
        [oats, pad_thai, steaks],
        MacroTargets(
            calories=2500.0,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=0.0,
            fiber_g=0.0,
        ),
        "cooked_100",
    )
    assert result.feasible is True
    by_slot = {item.slot: item for item in result.days[0].items}
    assert by_slot["breakfast"].recipe_id == oats.recipe_id
    assert by_slot["lunch"].recipe_id in {pad_thai.recipe_id, steaks.recipe_id}
    assert by_slot["dinner"].recipe_id in {pad_thai.recipe_id, steaks.recipe_id}
    assert by_slot["lunch"].recipe_id != by_slot["dinner"].recipe_id


def test_assigner_leaves_breakfast_empty_rather_than_use_lunch() -> None:
    pad_thai = _recipe("Pad Thai", slot_hint="lunch")
    steaks = _recipe("Steaks", slot_hint="dinner")
    result = SlotAssigner().assign(
        [SlotSpec(day_number=1, slot="breakfast")],
        [pad_thai, steaks],
        MacroTargets(calories=0.0, protein_g=0.0, carbs_g=0.0, fat_g=0.0, fiber_g=0.0),
        "cooked_100",
    )
    assert result.feasible is False
    placed = [item for day in result.days for item in day.items]
    assert placed == []
