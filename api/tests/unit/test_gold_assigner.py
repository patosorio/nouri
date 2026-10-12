"""Deterministic gold set for SlotAssigner — docs/8_TEST_PLAN.md §8.2.

Not live AI. Default `pytest tests/unit/` includes this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from validation.slot_assigner import AssignableRecipe, SlotAssigner, SlotSpec
from validation.types import MacroTargets, RecipeIngredientView

_GOLD = Path(__file__).resolve().parents[1] / "evals" / "gold" / "profiles.jsonl"


def _recipe(
    title: str,
    *,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    fiber_g: float,
    prep_method: str,
    is_saved: bool,
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
        primary_protein="none",
        ingredients=(RecipeIngredientView(name=title, ingredient_id=uuid4()),),
        is_saved=is_saved,
    )


def _pool(cooking_type: str, calories: float) -> list[AssignableRecipe]:
    per_slot = max(calories / 3.0, 400.0)
    scale = per_slot / 670.0
    prep_raw = "raw" if cooking_type.startswith("raw") else "steamed"
    prep_cooked = "steamed"
    pool: list[AssignableRecipe] = []
    for i in range(9):
        prep = prep_raw if i % 2 == 0 else prep_cooked
        if cooking_type == "cooked_100":
            prep = "steamed"
        pool.append(
            _recipe(
                f"saved-{i}",
                calories=per_slot,
                protein_g=27.0 * scale,
                carbs_g=83.0 * scale,
                fat_g=23.0 * scale,
                fiber_g=10.0 * scale,
                prep_method=prep,
                is_saved=True,
            )
        )
    for i in range(9):
        prep = prep_raw if i % 2 == 1 else prep_cooked
        if cooking_type == "cooked_100":
            prep = "steamed"
        pool.append(
            _recipe(
                f"new-{i}",
                calories=per_slot,
                protein_g=27.0 * scale,
                carbs_g=83.0 * scale,
                fat_g=23.0 * scale,
                fiber_g=10.0 * scale,
                prep_method=prep,
                is_saved=False,
            )
        )
    return pool


def _slots(days: int) -> list[SlotSpec]:
    slots: list[SlotSpec] = []
    for day in range(1, days + 1):
        for slot in ("breakfast", "lunch", "dinner"):
            slots.append(SlotSpec(day_number=day, slot=slot))
    return slots


def test_gold_profiles_assigner_hits_macro_tolerance() -> None:
    lines = _GOLD.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 8
    for line in lines:
        profile = json.loads(line)
        targets = MacroTargets(
            calories=float(profile["calorie_target"]),
            protein_g=float(profile["protein_g"]),
            carbs_g=float(profile["carbs_g"]),
            fat_g=float(profile["fat_g"]),
            fiber_g=float(profile["fiber_g"]),
        )
        result = SlotAssigner().assign(
            _slots(int(profile["days"])),
            _pool(profile["cooking_type"], targets.calories),
            targets,
            profile["cooking_type"],
            sourcing_policy=profile["sourcing_policy"],
        )
        assert result.feasible is True, profile["id"] + ": " + "; ".join(result.errors)
        floor = targets.calories * 0.80
        ceiling = targets.calories * 1.20
        for day in result.days:
            calories = sum(i.calories or 0 for i in day.items)
            assert floor <= calories <= ceiling, f"{profile['id']} day {day.day_number}"
