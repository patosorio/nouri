"""Deterministic layout checks on a model's meal plan before it is saved.

Same-day repeats, breakfast-role mismatches, type/slot mismatches, and
skeleton gaps are errors. A saved recipe with no known meal roles at
breakfast is an error. Only the exact pinned item is exempt from the
breakfast rule, and its dish still counts so a later copy that day is an error.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from planning.skeleton import PlanSkeleton, SkeletonSlot
from schemas.agent import GeneratedPlanData, GeneratedPlanItemAI, GeneratedRecipeAI

# Empty: juice and smoothie slots are checked for same-day repeats.
REPEAT_CHECK_SKIP_SLOTS: frozenset[str] = frozenset()

# day, slot_type, slot_order, recipe_id, juice_time ("" when the slot is a meal)
PinnedSlot = tuple[int, str, int, UUID, str]

_MEAL_SLOT_ORDER = {
    "breakfast": 0,
    "lunch": 1,
    "dinner": 2,
    "snack": 3,
    "extra_morning": 4,
    "extra_afternoon": 5,
    "extra_evening": 6,
}

_JUICE_KINDS = frozenset({"juice", "smoothie"})


def normalize_title(value: str) -> str:
    return " ".join(value.split()).casefold()


def slot_kind(slot: str) -> str:
    """juice and smoothie stay themselves. Every other slot is a meal."""
    if slot in _JUICE_KINDS:
        return slot
    return "meal"


@dataclass(frozen=True, slots=True)
class LayoutResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_layout(
    plan: GeneratedPlanData,
    *,
    candidate_roles: Mapping[UUID, list[str]],
    candidate_titles: Mapping[UUID, str],
    pinned_slots: set[PinnedSlot],
    candidate_types: Mapping[UUID, str] | None = None,
    skeleton: PlanSkeleton | None = None,
) -> LayoutResult:
    errors: list[str] = []
    warnings: list[str] = []
    generated = _generated_by_title(plan)
    generated_by_id = _generated_by_id(plan)
    types = candidate_types or {}
    if skeleton is not None:
        errors.extend(skeleton_coverage_errors(plan, skeleton))
    for day in plan.days:
        _same_day_repeats(
            day.day_number,
            day.items,
            candidate_titles,
            pinned_slots,
            errors,
        )
        for item in day.items:
            _type_vs_slot(
                day.day_number,
                item,
                generated,
                generated_by_id,
                types,
                errors,
            )
            if item.slot_type != "breakfast":
                continue
            if _is_exact_pin(day.day_number, item, pinned_slots):
                continue
            _breakfast_item(
                day.day_number,
                item,
                candidate_roles,
                generated,
                generated_by_id,
                errors,
            )
    return LayoutResult(errors=errors, warnings=warnings)


def skeleton_coverage_errors(
    plan: GeneratedPlanData, skeleton: PlanSkeleton
) -> list[str]:
    """Every skeleton slot has one item, and every item is one of those slots."""
    _pairs, errors = match_skeleton(plan, skeleton)
    return errors


def match_skeleton(
    plan: GeneratedPlanData,
    skeleton: PlanSkeleton,
) -> tuple[list[tuple[SkeletonSlot, GeneratedPlanItemAI]], list[str]]:
    """Pair each skeleton slot with one unused item. Extras and gaps are errors.

    A juice item with no juice_time can fill the next juice slot of that day.
    An item whose juice_time disagrees with the slot is left for another slot.
    """
    errors: list[str] = []
    pairs: list[tuple[SkeletonSlot, GeneratedPlanItemAI]] = []
    used: set[tuple[int, int]] = set()
    items_by_day = {day.day_number: day.items for day in plan.days}
    for slot in skeleton.slots:
        items = items_by_day.get(slot.day_number, [])
        found: int | None = None
        for index, item in enumerate(items):
            if (slot.day_number, index) in used or item.slot_type != slot.slot:
                continue
            if (
                slot.juice_time
                and item.juice_time is not None
                and item.juice_time.value != slot.juice_time
            ):
                continue
            found = index
            break
        if found is None:
            errors.append(f"Day {slot.day_number} missing {_slot_label(slot)}")
            continue
        used.add((slot.day_number, found))
        pairs.append((slot, items[found]))
    for day in plan.days:
        for index, item in enumerate(day.items):
            if (day.day_number, index) in used:
                continue
            title = item.recipe_title.strip() or item.slot_type
            errors.append(
                f"Day {day.day_number} extra {item.slot_type} '{title}'"
            )
    return pairs, errors


def dish_kind(
    item: GeneratedPlanItemAI,
    generated: Mapping[str, GeneratedRecipeAI],
    generated_by_id: Mapping[UUID, GeneratedRecipeAI],
    candidate_types: Mapping[UUID, str],
) -> str | None:
    """meal / juice / smoothie from the recipe, or None when it is unknown.

    Generated dishes use the generated recipe's slot_type. Saved dishes use
    the recipe's recipe_type.
    """
    if item.recipe_id == "generate_new":
        recipe = generated.get(normalize_title(item.recipe_title))
        if recipe is None:
            return None
        return slot_kind(recipe.slot_type)
    if not isinstance(item.recipe_id, UUID):
        return None
    generated_recipe = generated_by_id.get(item.recipe_id)
    if generated_recipe is not None:
        return slot_kind(generated_recipe.slot_type)
    raw = candidate_types.get(item.recipe_id)
    if not raw:
        return None
    return slot_kind(str(raw))


def consecutive_main_dish_notes(plan: GeneratedPlanData) -> list[str]:
    """Soft flags when the same meal (not a juice or smoothie) is on day N and N-1."""
    by_day: dict[int, dict[str, str]] = {}
    for day in plan.days:
        dishes: dict[str, str] = {}
        for item in day.items:
            if slot_kind(item.slot_type) != "meal":
                continue
            key = normalize_title(item.recipe_title)
            if not key or key in dishes:
                continue
            dishes[key] = item.recipe_title.strip()
        by_day[day.day_number] = dishes
    notes: list[str] = []
    for day_number in sorted(by_day):
        previous = by_day.get(day_number - 1, {})
        for key, label in by_day[day_number].items():
            if key not in previous:
                continue
            notes.append(
                f"Day {day_number} repeats {label} from day {day_number - 1}"
            )
    return notes


def _slot_label(slot: SkeletonSlot) -> str:
    if slot.juice_time:
        return f"{slot.slot} {slot.juice_time}"
    return slot.slot


def _same_day_repeats(
    day_number: int,
    items: list[GeneratedPlanItemAI],
    candidate_titles: Mapping[UUID, str],
    pinned_slots: set[PinnedSlot],
    errors: list[str],
) -> None:
    seen: dict[str, str] = {}
    pinned_items: list[GeneratedPlanItemAI] = []
    open_items: list[GeneratedPlanItemAI] = []
    for item in items:
        if item.slot_type in REPEAT_CHECK_SKIP_SLOTS:
            continue
        if _is_exact_pin(day_number, item, pinned_slots):
            pinned_items.append(item)
        else:
            open_items.append(item)
    for item in pinned_items:
        key = _dish_key(item, candidate_titles)
        if key is None:
            continue
        seen[key] = item.recipe_title.strip() or key
    for item in open_items:
        key = _dish_key(item, candidate_titles)
        if key is None:
            continue
        label = item.recipe_title.strip() or key
        if key in seen:
            errors.append(f"Day {day_number}: '{label}' appears twice")
            continue
        seen[key] = label


def _is_exact_pin(
    day_number: int,
    item: GeneratedPlanItemAI,
    pinned_slots: set[PinnedSlot],
) -> bool:
    """True only when this item is the pinned recipe in that pinned slot."""
    item_juice = item.juice_time.value if item.juice_time is not None else ""
    if not isinstance(item.recipe_id, UUID):
        return False
    for day, slot_type, slot_order, recipe_id, juice_time in pinned_slots:
        if day != day_number or slot_type != item.slot_type:
            continue
        if item.recipe_id != recipe_id:
            continue
        if juice_time:
            at_position = item_juice == juice_time
        else:
            at_position = _MEAL_SLOT_ORDER.get(item.slot_type) == slot_order
        if at_position:
            return True
    return False


def _dish_key(
    item: GeneratedPlanItemAI,
    candidate_titles: Mapping[UUID, str],
) -> str | None:
    title = item.recipe_title
    if isinstance(item.recipe_id, UUID):
        title = candidate_titles.get(item.recipe_id) or item.recipe_title
    normalized = normalize_title(title or "")
    if not normalized:
        return None
    return normalized


def _type_vs_slot(
    day_number: int,
    item: GeneratedPlanItemAI,
    generated: Mapping[str, GeneratedRecipeAI],
    generated_by_id: Mapping[UUID, GeneratedRecipeAI],
    candidate_types: Mapping[UUID, str],
    errors: list[str],
) -> None:
    expected = slot_kind(item.slot_type)
    kind = dish_kind(item, generated, generated_by_id, candidate_types)
    title = item.recipe_title.strip() or item.slot_type
    if kind is None:
        if expected in _JUICE_KINDS:
            errors.append(
                f"Day {day_number} {item.slot_type}: '{title}' has no recipe type"
            )
        return
    if kind != expected:
        errors.append(
            f"Day {day_number} {item.slot_type}: '{title}' is a {kind}, not a {expected}"
        )


def _breakfast_item(
    day_number: int,
    item: GeneratedPlanItemAI,
    candidate_roles: Mapping[UUID, list[str]],
    generated: Mapping[str, GeneratedRecipeAI],
    generated_by_id: Mapping[UUID, GeneratedRecipeAI],
    errors: list[str],
) -> None:
    title = item.recipe_title.strip() or "breakfast"
    recipe: GeneratedRecipeAI | None = None
    if isinstance(item.recipe_id, UUID):
        recipe = generated_by_id.get(item.recipe_id)
    if recipe is None and item.recipe_id == "generate_new":
        recipe = generated.get(normalize_title(title))
    if recipe is not None:
        if normalize_title(recipe.slot_type) != "breakfast":
            errors.append(
                f"Day {day_number} breakfast: generated '{title}' has slot_type "
                f"'{recipe.slot_type}', not breakfast"
            )
        return
    if not isinstance(item.recipe_id, UUID):
        return
    roles = candidate_roles.get(item.recipe_id)
    if not roles:
        errors.append(f"Day {day_number} breakfast: '{title}' has no meal roles")
        return
    if "breakfast" not in {role.casefold() for role in roles}:
        errors.append(
            f"Day {day_number} breakfast: '{title}' is not a breakfast dish"
        )


def _generated_by_title(plan: GeneratedPlanData) -> dict[str, GeneratedRecipeAI]:
    by_title: dict[str, GeneratedRecipeAI] = {}
    for recipe in plan.generated_recipes:
        key = normalize_title(recipe.title)
        if key and key not in by_title:
            by_title[key] = recipe
    return by_title


def _generated_by_id(plan: GeneratedPlanData) -> dict[UUID, GeneratedRecipeAI]:
    by_id: dict[UUID, GeneratedRecipeAI] = {}
    for recipe in plan.generated_recipes:
        if recipe.assigned_id is not None:
            by_id[recipe.assigned_id] = recipe
    return by_id
