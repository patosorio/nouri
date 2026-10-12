"""VarietyChecker — protein rotation + meal novelty (tech spec §6.1 / test plan §3.1).

Ingredient frequency no longer fails on culinary staples (ginger, lemon, oil, …).
What we actually want to prevent is the same dinner (or lunch/breakfast) repeating
day after day — not shared aromatics across an otherwise varied week.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import pairwise

from validation.types import PlanDayView, PlanDraftView, VarietyCheckResult

# Max consecutive days the same primary protein may appear (test plan §3.1)
MAX_CONSECUTIVE_PROTEIN_DAYS = 2

# Max share of plan recipes a non-staple ingredient may appear in
MAX_INGREDIENT_RECIPE_SHARE = 0.75

# Aromatics / seasonings / bases that legitimately appear across many recipes
_STAPLE_TOKENS = frozenset(
    {
        "salt",
        "pepper",
        "water",
        "oil",
        "garlic",
        "ginger",
        "lemon",
        "lime",
        "onion",
        "shallot",
        "vinegar",
        "tamari",
        "soy",
        "herbs",
        "parsley",
        "cilantro",
        "coriander",
        "basil",
        "mint",
        "thyme",
        "oregano",
        "cumin",
        "turmeric",
        "chili",
        "chilli",
        "paprika",
        "sesame",
    }
)

_MEAL_SLOTS = frozenset({"breakfast", "lunch", "dinner"})


def _is_staple_ingredient(name: str) -> bool:
    tokens = [
        t for t in name.strip().lower().replace("-", " ").split() if t and t != "fresh"
    ]
    if not tokens:
        return False
    return any(token in _STAPLE_TOKENS for token in tokens)


class VarietyChecker:
    def check_protein_variety(
        self, plan_days: list[PlanDayView] | tuple[PlanDayView, ...] | PlanDraftView
    ) -> VarietyCheckResult:
        days = plan_days.days if isinstance(plan_days, PlanDraftView) else plan_days
        proteins_by_day: dict[int, set[str]] = {}
        for day in sorted(days, key=lambda d: d.day_number):
            proteins: set[str] = set()
            for item in day.items:
                if item.primary_protein and item.primary_protein != "none":
                    proteins.add(item.primary_protein)
            proteins_by_day[day.day_number] = proteins

        day_numbers = sorted(proteins_by_day.keys())
        errors: list[str] = []
        hints: list[str] = []

        all_proteins: set[str] = set()
        for prots in proteins_by_day.values():
            all_proteins |= prots

        for protein in sorted(all_proteins):
            run = 0
            run_start: int | None = None
            for day_num in day_numbers:
                if protein in proteins_by_day[day_num]:
                    if run == 0:
                        run_start = day_num
                    run += 1
                    if run > MAX_CONSECUTIVE_PROTEIN_DAYS:
                        msg = (
                            f"Protein '{protein}' appears on more than "
                            f"{MAX_CONSECUTIVE_PROTEIN_DAYS} consecutive days "
                            f"(run starting day {run_start})"
                        )
                        errors.append(msg)
                        hints.append(
                            f"Replace '{protein}' on day {day_num} with a different "
                            f"primary_protein_source to break the consecutive run."
                        )
                else:
                    run = 0
                    run_start = None

        passed = len(errors) == 0
        return VarietyCheckResult(
            passed=passed,
            errors=tuple(errors),
            repair_hints=tuple(hints),
        )

    def check_ingredient_variety(
        self, plan_days: list[PlanDayView] | tuple[PlanDayView, ...] | PlanDraftView
    ) -> VarietyCheckResult:
        days = plan_days.days if isinstance(plan_days, PlanDraftView) else plan_days
        recipe_keys: set[str] = set()
        ingredient_to_recipes: dict[str, set[str]] = defaultdict(set)

        for day in days:
            for item in day.items:
                recipe_key = str(item.recipe_id) if item.recipe_id else item.name
                recipe_keys.add(recipe_key)
                for ing in item.ingredients:
                    name = ing.name.strip().lower()
                    if _is_staple_ingredient(name):
                        continue
                    ingredient_to_recipes[name].add(recipe_key)

        total_recipes = len(recipe_keys)
        if total_recipes == 0:
            return VarietyCheckResult(passed=True)

        errors: list[str] = []
        hints: list[str] = []
        for name, recipes in sorted(ingredient_to_recipes.items()):
            share = len(recipes) / total_recipes
            if share > MAX_INGREDIENT_RECIPE_SHARE:
                pct = share * 100
                msg = (
                    f"Ingredient '{name}' appears in {pct:.0f}% of plan recipes "
                    f"(limit {MAX_INGREDIENT_RECIPE_SHARE * 100:.0f}%)"
                )
                errors.append(msg)
                day_hit = next(
                    (
                        d.day_number
                        for d in days
                        for i in d.items
                        for ing in i.ingredients
                        if ing.name.strip().lower() == name
                    ),
                    None,
                )
                hints.append(
                    f"Reduce use of ingredient '{name}'"
                    + (f" (seen on day {day_hit})" if day_hit is not None else "")
                    + f"; swap recipes so it appears in "
                    f"≤{MAX_INGREDIENT_RECIPE_SHARE * 100:.0f}% of plan recipes."
                )

        return VarietyCheckResult(
            passed=len(errors) == 0,
            errors=tuple(errors),
            repair_hints=tuple(hints),
        )

    def check_meal_repeat(
        self, plan_days: list[PlanDayView] | tuple[PlanDayView, ...] | PlanDraftView
    ) -> VarietyCheckResult:
        """Fail when the same breakfast/lunch/dinner repeats on consecutive days."""
        days = plan_days.days if isinstance(plan_days, PlanDraftView) else plan_days
        by_day_slot: dict[tuple[int, str], str] = {}
        for day in days:
            for item in day.items:
                if item.slot not in _MEAL_SLOTS:
                    continue
                key = (
                    str(item.recipe_id)
                    if item.recipe_id is not None
                    else item.name.strip().lower()
                )
                by_day_slot[(day.day_number, item.slot)] = key

        errors: list[str] = []
        hints: list[str] = []
        day_numbers = sorted({d for d, _ in by_day_slot})
        for slot in sorted(_MEAL_SLOTS):
            for prev, cur in pairwise(day_numbers):
                a = by_day_slot.get((prev, slot))
                b = by_day_slot.get((cur, slot))
                if a is not None and a == b:
                    errors.append(
                        f"Same {slot} on consecutive days {prev} and {cur}"
                    )
                    hints.append(
                        f"Use a different recipe for {slot} on day {cur} "
                        f"(avoid repeating day {prev})."
                    )

        return VarietyCheckResult(
            passed=len(errors) == 0,
            errors=tuple(errors),
            repair_hints=tuple(hints),
        )
