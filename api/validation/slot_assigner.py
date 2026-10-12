"""Greedy slot assignment — recipes-with-known-macros onto (day, slot).

The LLM proposes recipe content. This module places those recipes so daily
macros, raw/cooked ratio, and protein rotation can actually be satisfied.
docs/7_TECH_SPEC.md §6; plan-generation audit 2026-08-13.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal
from uuid import UUID

from validation.exclusion_checker import ExclusionChecker
from validation.plan_validator import PlanValidator
from validation.ratio_checker import COOKING_TYPE_RAW_PCT, RAW_PREP_METHODS
from validation.types import (
    ExclusionView,
    MacroTargets,
    PlanDayView,
    PlanDraftView,
    PlanItemView,
    RecipeIngredientView,
    RecipeView,
    UserProfileView,
)
from validation.variety_checker import MAX_CONSECUTIVE_PROTEIN_DAYS

# Main meals may need 3 servings when the LLM emits light (~300–500 kcal) recipes
# against a ~2000 kcal day with only breakfast/lunch/dinner slots.
_MAX_SERVINGS = 3
_JUICE_SLOTS = frozenset({"juice", "smoothie"})
_LUNCH_DINNER_SLOTS = frozenset({"lunch", "dinner"})
_SWAP_PASSES = 3
_CALORIE_SCORE_WEIGHT = 3.0
_RATIO_SCORE_WEIGHT = 4.0

SourcingPolicy = Literal["prefer_saved", "balanced", "prefer_new"]


@dataclass(frozen=True, slots=True)
class AssignableRecipe:
    recipe_id: UUID
    title: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    prep_method: str | None = None
    primary_protein: str | None = None
    ingredients: tuple[RecipeIngredientView, ...] = ()
    slot_hint: str | None = None
    is_saved: bool = False

    def scaled(self, servings: int) -> AssignableRecipe:
        if servings == 1:
            return self
        factor = float(servings)
        return replace(
            self,
            calories=self.calories * factor,
            protein_g=self.protein_g * factor,
            carbs_g=self.carbs_g * factor,
            fat_g=self.fat_g * factor,
            fiber_g=self.fiber_g * factor,
        )


@dataclass(frozen=True, slots=True)
class SlotSpec:
    day_number: int
    slot: str
    pinned_recipe_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AssignmentResult:
    days: tuple[PlanDayView, ...]
    feasible: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_draft(self) -> PlanDraftView:
        return PlanDraftView(days=self.days)


def _role_allows(recipe: AssignableRecipe, slot: str) -> bool:
    """Place a dish only in a slot its role allows.

    Lunch and dinner are one pair: either may fill the other, and neither
    may move into breakfast. A missing role does not invent a block.
    """
    role = recipe.slot_hint
    if not role:
        return True
    if role == slot:
        return True
    return role in _LUNCH_DINNER_SLOTS and slot in _LUNCH_DINNER_SLOTS


class SlotAssigner:
    def __init__(
        self,
        exclusion_checker: ExclusionChecker | None = None,
        plan_validator: PlanValidator | None = None,
    ) -> None:
        self._exclusions = exclusion_checker or ExclusionChecker()
        self._validator = plan_validator or PlanValidator()

    def assign(
        self,
        slots: list[SlotSpec] | tuple[SlotSpec, ...],
        pool: list[AssignableRecipe] | tuple[AssignableRecipe, ...],
        targets: MacroTargets,
        cooking_type: str,
        exclusions: tuple[ExclusionView, ...] = (),
        sourcing_policy: SourcingPolicy = "balanced",
    ) -> AssignmentResult:
        slot_list = list(slots)
        if not slot_list:
            return AssignmentResult(days=(), feasible=False, errors=("No slots to fill",))

        eligible = self._eligible_pool(pool, exclusions)
        by_id = {r.recipe_id: r for r in eligible}
        if not eligible:
            return AssignmentResult(
                days=(),
                feasible=False,
                errors=("No recipes with known nutrition remain after exclusion filter",),
            )

        soft_warnings: list[str] = []
        preflight = self._preflight(slot_list, eligible, targets)
        if preflight is not None:
            # Still assign best-effort; surface as a review note instead of failing.
            soft_warnings.append(preflight)

        items = self._greedy(
            slot_list, eligible, by_id, targets, cooking_type, sourcing_policy
        )
        if items is None:
            return AssignmentResult(
                days=(),
                feasible=False,
                errors=("Greedy assignment could not fill every slot from the pool",),
            )

        items = self._top_up_calories(items, by_id, targets)
        items = self._densify_days(
            items, eligible, by_id, targets, sourcing_policy=sourcing_policy
        )
        items = self._local_swaps(
            items, eligible, targets, cooking_type, sourcing_policy
        )
        items = self._top_up_calories(items, by_id, targets)
        items = self._densify_days(
            items, eligible, by_id, targets, sourcing_policy=sourcing_policy
        )
        days = self._group_days(items)
        draft = PlanDraftView(days=days)
        result = self._validator.validate(
            draft, UserProfileView(cooking_type=cooking_type, exclusions=()), targets
        )
        if result.passed:
            return AssignmentResult(
                days=days, feasible=True, warnings=tuple(soft_warnings)
            )
        # Soft-accept: exclusions already filtered from the pool. Macro / ratio /
        # variety misses become review notes so the user still gets a plan.
        return AssignmentResult(
            days=days,
            feasible=True,
            warnings=(*soft_warnings, *result.errors),
        )

    def _eligible_pool(
        self,
        pool: list[AssignableRecipe] | tuple[AssignableRecipe, ...],
        exclusions: tuple[ExclusionView, ...],
    ) -> list[AssignableRecipe]:
        eligible: list[AssignableRecipe] = []
        for recipe in pool:
            if recipe.calories <= 0:
                continue
            view = RecipeView(id=recipe.recipe_id, ingredients=recipe.ingredients)
            if exclusions and not self._exclusions.check_recipe(view, exclusions):
                continue
            eligible.append(recipe)
        return eligible

    def _preflight(
        self,
        slots: list[SlotSpec],
        pool: list[AssignableRecipe],
        targets: MacroTargets,
    ) -> str | None:
        if targets.calories <= 0:
            return None
        slots_per_day: dict[int, int] = {}
        for slot in slots:
            slots_per_day[slot.day_number] = slots_per_day.get(slot.day_number, 0) + 1
        max_slots = max(slots_per_day.values())
        ranked = sorted((r.calories * _MAX_SERVINGS for r in pool), reverse=True)
        best_day = sum(ranked[:max_slots])
        floor = targets.calories * 0.80
        if best_day + 1e-6 < floor:
            return (
                f"Infeasible pool: best-case day calories {best_day:.0f} "
                f"cannot reach 80% of target {targets.calories:.0f}"
            )
        return None

    def _greedy(
        self,
        slots: list[SlotSpec],
        pool: list[AssignableRecipe],
        by_id: dict[UUID, AssignableRecipe],
        targets: MacroTargets,
        cooking_type: str,
        sourcing_policy: SourcingPolicy,
    ) -> list[PlanItemView] | None:
        items: list[PlanItemView] = []
        used_today: dict[int, set[UUID]] = {}
        proteins_by_day: dict[int, set[str]] = {}

        by_day: dict[int, list[SlotSpec]] = {}
        for slot in slots:
            by_day.setdefault(slot.day_number, []).append(slot)

        for day_number in sorted(by_day):
            day_slots = by_day[day_number]
            remaining = [
                targets.calories,
                targets.protein_g,
                targets.carbs_g,
                targets.fat_g,
                targets.fiber_g,
            ]
            left = len(day_slots)
            used_today[day_number] = set()
            proteins_by_day[day_number] = set()

            for slot in day_slots:
                choice = self._pick(
                    slot=slot,
                    pool=pool,
                    by_id=by_id,
                    remaining=remaining,
                    slots_left=left,
                    used_today=used_today[day_number],
                    proteins_by_day=proteins_by_day,
                    cooking_type=cooking_type,
                    placed=items,
                    targets=targets,
                    sourcing_policy=sourcing_policy,
                )
                if choice is None:
                    return None
                recipe, servings = choice
                scaled = recipe.scaled(servings)
                items.append(
                    PlanItemView(
                        day_number=day_number,
                        name=recipe.title,
                        slot=slot.slot,
                        prep_method=recipe.prep_method,
                        calories=scaled.calories,
                        protein_g=scaled.protein_g,
                        carbs_g=scaled.carbs_g,
                        fat_g=scaled.fat_g,
                        fiber_g=scaled.fiber_g,
                        primary_protein=recipe.primary_protein,
                        recipe_id=recipe.recipe_id,
                        ingredients=recipe.ingredients,
                    )
                )
                used_today[day_number].add(recipe.recipe_id)
                if recipe.primary_protein and recipe.primary_protein != "none":
                    proteins_by_day[day_number].add(recipe.primary_protein)
                remaining[0] -= scaled.calories
                remaining[1] -= scaled.protein_g
                remaining[2] -= scaled.carbs_g
                remaining[3] -= scaled.fat_g
                remaining[4] -= scaled.fiber_g
                left -= 1

        return items

    def _pick(
        self,
        *,
        slot: SlotSpec,
        pool: list[AssignableRecipe],
        by_id: dict[UUID, AssignableRecipe],
        remaining: list[float],
        slots_left: int,
        used_today: set[UUID],
        proteins_by_day: dict[int, set[str]],
        cooking_type: str,
        placed: list[PlanItemView],
        targets: MacroTargets,
        sourcing_policy: SourcingPolicy,
    ) -> tuple[AssignableRecipe, int] | None:
        if slot.pinned_recipe_id is not None:
            pinned = by_id.get(slot.pinned_recipe_id)
            if pinned is None:
                return None
            return pinned, 1

        preferred = self._policy_pool(pool, sourcing_policy)
        if preferred:
            choice = self._best_from(
                slot=slot,
                pool=preferred,
                remaining=remaining,
                slots_left=slots_left,
                used_today=used_today,
                proteins_by_day=proteins_by_day,
                cooking_type=cooking_type,
                placed=placed,
                targets=targets,
            )
            if choice is not None:
                return choice
        if preferred is pool:
            return None
        return self._best_from(
            slot=slot,
            pool=pool,
            remaining=remaining,
            slots_left=slots_left,
            used_today=used_today,
            proteins_by_day=proteins_by_day,
            cooking_type=cooking_type,
            placed=placed,
            targets=targets,
        )

    @staticmethod
    def _policy_pool(
        pool: list[AssignableRecipe], sourcing_policy: SourcingPolicy
    ) -> list[AssignableRecipe]:
        """Filter by sourcing preference. Empty means 'none left', not 'use everything'."""
        if sourcing_policy == "prefer_saved":
            return [r for r in pool if r.is_saved]
        if sourcing_policy == "prefer_new":
            return [r for r in pool if not r.is_saved]
        return pool

    def _best_from(
        self,
        *,
        slot: SlotSpec,
        pool: list[AssignableRecipe],
        remaining: list[float],
        slots_left: int,
        used_today: set[UUID],
        proteins_by_day: dict[int, set[str]],
        cooking_type: str,
        placed: list[PlanItemView],
        targets: MacroTargets,
    ) -> tuple[AssignableRecipe, int] | None:
        best: tuple[float, AssignableRecipe, int] | None = None
        max_servings = 1 if slot.slot in _JUICE_SLOTS else _MAX_SERVINGS
        for recipe in pool:
            if recipe.recipe_id in used_today:
                continue
            if not _role_allows(recipe, slot.slot):
                continue
            for servings in range(1, max_servings + 1):
                scaled = recipe.scaled(servings)
                score = self._score(
                    slot, recipe, scaled, remaining, slots_left, cooking_type, placed, targets
                )
                if self._protein_blocked(
                    slot.day_number, recipe.primary_protein, proteins_by_day
                ):
                    score += 5.0
                if best is None or score < best[0]:
                    best = (score, recipe, servings)
        if best is None:
            return None
        return best[1], best[2]

    def _protein_blocked(
        self,
        day_number: int,
        protein: str | None,
        proteins_by_day: dict[int, set[str]],
    ) -> bool:
        if not protein or protein == "none":
            return False
        run = 0
        for offset in range(1, MAX_CONSECUTIVE_PROTEIN_DAYS + 1):
            prev = proteins_by_day.get(day_number - offset, set())
            if protein in prev:
                run += 1
            else:
                break
        return run >= MAX_CONSECUTIVE_PROTEIN_DAYS

    def _score(
        self,
        slot: SlotSpec,
        recipe: AssignableRecipe,
        scaled: AssignableRecipe,
        remaining: list[float],
        slots_left: int,
        cooking_type: str,
        placed: list[PlanItemView],
        targets: MacroTargets,
    ) -> float:
        if slots_left <= 0:
            return 1e9
        fields = (
            (scaled.calories, remaining[0], targets.calories, _CALORIE_SCORE_WEIGHT),
            (scaled.protein_g, remaining[1], targets.protein_g, 1.0),
            (scaled.carbs_g, remaining[2], targets.carbs_g, 1.0),
            (scaled.fat_g, remaining[3], targets.fat_g, 1.0),
            (scaled.fiber_g, remaining[4], targets.fiber_g, 1.0),
        )
        score = 0.0
        for actual, rem, target, weight in fields:
            if target <= 0:
                continue
            denom = max(abs(target), 1.0)
            ideal = rem / slots_left
            score += weight * abs(actual - ideal) / denom

        if recipe.slot_hint and recipe.slot_hint == slot.slot:
            score -= 0.15

        target_raw = COOKING_TYPE_RAW_PCT.get(cooking_type)
        if target_raw is not None:
            total = len(placed) + 1
            raw = sum(
                1
                for item in placed
                if item.prep_method is not None and item.prep_method in RAW_PREP_METHODS
            )
            if scaled.prep_method is not None and scaled.prep_method in RAW_PREP_METHODS:
                raw += 1
            actual_pct = (raw / total) * 100.0
            score += _RATIO_SCORE_WEIGHT * abs(actual_pct - target_raw) / 100.0

        return score

    def _top_up_calories(
        self,
        items: list[PlanItemView],
        by_id: dict[UUID, AssignableRecipe],
        targets: MacroTargets,
    ) -> list[PlanItemView]:
        """Increase servings on under-target days until ≥80% of calorie target."""
        if targets.calories <= 0:
            return items
        floor = targets.calories * 0.80
        ceiling = targets.calories * 1.20
        result = list(items)
        by_day: dict[int, list[int]] = {}
        for idx, item in enumerate(result):
            by_day.setdefault(item.day_number, []).append(idx)

        for idxs in by_day.values():
            guard = 0
            while guard < 20:
                guard += 1
                day_cal = sum(result[i].calories or 0.0 for i in idxs)
                if day_cal + 1e-6 >= floor:
                    break
                best_i: int | None = None
                best_key: tuple[float, float] | None = None
                for i in idxs:
                    item = result[i]
                    if item.recipe_id is None or item.slot in _JUICE_SLOTS:
                        continue
                    base = by_id.get(item.recipe_id)
                    if base is None or base.calories <= 0:
                        continue
                    current = max(1, round((item.calories or 0.0) / base.calories))
                    if current >= _MAX_SERVINGS:
                        continue
                    next_day = day_cal + base.calories
                    overshoot = max(0.0, next_day - ceiling)
                    # Prefer bumps that close the gap with least overshoot.
                    key = (overshoot, -base.calories)
                    if best_key is None or key < best_key:
                        best_key = key
                        best_i = i
                if best_i is None:
                    break
                item = result[best_i]
                assert item.recipe_id is not None
                base = by_id[item.recipe_id]
                current = max(1, round((item.calories or 0.0) / base.calories))
                scaled = base.scaled(current + 1)
                result[best_i] = replace(
                    item,
                    calories=scaled.calories,
                    protein_g=scaled.protein_g,
                    carbs_g=scaled.carbs_g,
                    fat_g=scaled.fat_g,
                    fiber_g=scaled.fiber_g,
                )
        return result

    def _densify_days(
        self,
        items: list[PlanItemView],
        pool: list[AssignableRecipe],
        by_id: dict[UUID, AssignableRecipe],
        targets: MacroTargets,
        *,
        sourcing_policy: SourcingPolicy = "balanced",
    ) -> list[PlanItemView]:
        """Swap light meals for denser unused recipes when a day is still under floor."""
        if targets.calories <= 0:
            return items
        floor = targets.calories * 0.80
        result = list(items)
        by_day: dict[int, list[int]] = {}
        for idx, item in enumerate(result):
            by_day.setdefault(item.day_number, []).append(idx)

        for idxs in by_day.values():
            guard = 0
            while guard < len(idxs):
                guard += 1
                day_cal = sum(result[i].calories or 0.0 for i in idxs)
                if day_cal + 1e-6 >= floor:
                    break
                used = {
                    result[i].recipe_id
                    for i in range(len(result))
                    if result[i].recipe_id is not None
                }
                preferred = self._policy_pool(
                    [r for r in pool if r.recipe_id not in used], sourcing_policy
                )
                if sourcing_policy in ("prefer_saved", "prefer_new"):
                    # Do not break sourcing preference just to chase calories.
                    candidates = sorted(
                        preferred, key=lambda r: r.calories, reverse=True
                    )
                else:
                    fallback = [r for r in pool if r.recipe_id not in used]
                    candidates = sorted(
                        preferred if preferred else fallback,
                        key=lambda r: r.calories,
                        reverse=True,
                    )
                if not candidates:
                    break
                light_i = min(idxs, key=lambda i: result[i].calories or 0.0)
                light = result[light_i]
                if light.slot in _JUICE_SLOTS:
                    non_juice = [
                        i for i in idxs if result[i].slot not in _JUICE_SLOTS
                    ]
                    if not non_juice:
                        break
                    light_i = min(non_juice, key=lambda i: result[i].calories or 0.0)
                    light = result[light_i]
                improved = False
                for recipe in candidates:
                    if not _role_allows(recipe, light.slot):
                        continue
                    for servings in range(_MAX_SERVINGS, 0, -1):
                        scaled = recipe.scaled(servings)
                        if scaled.calories <= (light.calories or 0.0) + 1e-6:
                            continue
                        result[light_i] = PlanItemView(
                            day_number=light.day_number,
                            name=recipe.title,
                            slot=light.slot,
                            prep_method=recipe.prep_method,
                            calories=scaled.calories,
                            protein_g=scaled.protein_g,
                            carbs_g=scaled.carbs_g,
                            fat_g=scaled.fat_g,
                            fiber_g=scaled.fiber_g,
                            primary_protein=recipe.primary_protein,
                            recipe_id=recipe.recipe_id,
                            ingredients=recipe.ingredients,
                        )
                        improved = True
                        break
                    if improved:
                        break
                if not improved:
                    break
        return result

    def _local_swaps(
        self,
        items: list[PlanItemView],
        pool: list[AssignableRecipe],
        targets: MacroTargets,
        cooking_type: str,
        sourcing_policy: SourcingPolicy,
    ) -> list[PlanItemView]:
        current = list(items)
        best_cost = self._cost(current, targets, cooking_type)
        if best_cost == 0.0:
            return current

        n = len(current)
        for _ in range(_SWAP_PASSES):
            improved = False
            for i in range(n):
                for j in range(i + 1, n):
                    if current[i].day_number == current[j].day_number:
                        continue
                    if current[i].slot != current[j].slot:
                        continue
                    trial = list(current)
                    a, b = trial[i], trial[j]
                    trial[i] = replace(a, day_number=b.day_number)
                    trial[j] = replace(b, day_number=a.day_number)
                    cost = self._cost(trial, targets, cooking_type)
                    if cost < best_cost:
                        current = trial
                        best_cost = cost
                        improved = True
                        if best_cost == 0.0:
                            return current
            if not improved:
                break

        if best_cost == 0.0:
            return current

        # Replace a high-error item with an unused pool member of the same slot hint.
        used = {item.recipe_id for item in current if item.recipe_id is not None}
        unused = self._policy_pool(
            [r for r in pool if r.recipe_id not in used], sourcing_policy
        )
        if not unused and sourcing_policy == "balanced":
            unused = [r for r in pool if r.recipe_id not in used]
        for idx, item in enumerate(list(current)):
            for recipe in unused:
                if not _role_allows(recipe, item.slot):
                    continue
                scaled = recipe.scaled(1)
                trial = list(current)
                trial[idx] = PlanItemView(
                    day_number=item.day_number,
                    name=recipe.title,
                    slot=item.slot,
                    prep_method=recipe.prep_method,
                    calories=scaled.calories,
                    protein_g=scaled.protein_g,
                    carbs_g=scaled.carbs_g,
                    fat_g=scaled.fat_g,
                    fiber_g=scaled.fiber_g,
                    primary_protein=recipe.primary_protein,
                    recipe_id=recipe.recipe_id,
                    ingredients=recipe.ingredients,
                )
                cost = self._cost(trial, targets, cooking_type)
                if cost < best_cost:
                    current = trial
                    best_cost = cost
                    used_now = {
                        it.recipe_id
                        for it in current
                        if it.recipe_id is not None
                    }
                    unused = self._policy_pool(
                        [r for r in pool if r.recipe_id not in used_now],
                        sourcing_policy,
                    )
                    if not unused and sourcing_policy == "balanced":
                        unused = [r for r in pool if r.recipe_id not in used_now]
                    if best_cost == 0.0:
                        return current
                    break
        return current

    def _cost(
        self,
        items: list[PlanItemView],
        targets: MacroTargets,
        cooking_type: str,
    ) -> float:
        draft = PlanDraftView(days=self._group_days(items))
        result = self._validator.validate(
            draft, UserProfileView(cooking_type=cooking_type, exclusions=()), targets
        )
        if result.passed:
            return 0.0
        return float(len(result.errors))

    @staticmethod
    def _group_days(items: list[PlanItemView]) -> tuple[PlanDayView, ...]:
        grouped: dict[int, list[PlanItemView]] = {}
        for item in items:
            grouped.setdefault(item.day_number, []).append(item)
        return tuple(
            PlanDayView(day_number=day, items=tuple(grouped[day]))
            for day in sorted(grouped)
        )
