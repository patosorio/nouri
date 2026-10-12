"""Model-estimated nutrition checks. Flags are estimates, not a nutrition database."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from validation.nutrition_validator import BOUNDS

_GRAM_UNITS = frozenset({"g", "gram", "grams"})
_KCAL_TOLERANCE = 1.0
_GRAM_TOLERANCE = 0.5
_ATWATER_TOLERANCE = 0.15


@dataclass(frozen=True, slots=True)
class DishNutrition:
    """Per-serving estimate for one dish."""

    name: str
    path: str
    calories_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float
    fiber_g: float
    ingredient_grams: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class ServingNutrition:
    """Per-serving values. Day totals multiply these by servings."""

    servings: float
    calories_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float
    fiber_g: float


@dataclass(frozen=True, slots=True)
class DayTotals:
    calories_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float
    fiber_g: float


def grams_from_ingredients(ingredients: Sequence[object]) -> tuple[float, ...] | None:
    """Gram weights, or None when any line is missing grams."""
    if not ingredients:
        return None
    grams: list[float] = []
    for ingredient in ingredients:
        unit = str(getattr(ingredient, "unit", "") or "").strip().casefold()
        quantity = getattr(ingredient, "quantity", None)
        if unit not in _GRAM_UNITS or quantity is None:
            return None
        grams.append(float(quantity))
    return tuple(grams)


def check_dish_nutrition(dish: DishNutrition) -> list[str]:
    """All four dish flags. An empty list means the estimate is internally consistent."""
    return [message for _rule, message in _dish_flags(dish)]


def hard_dish_flags(dish: DishNutrition) -> list[str]:
    """Rules 1 and 3. Generated dishes raise on these; saved dishes only log them."""
    return [message for rule, message in _dish_flags(dish) if rule in (1, 3)]


def check_day_totals(
    day_number: int,
    items: Sequence[ServingNutrition],
    totals: DayTotals,
) -> list[str]:
    """Flag a day whose declared totals are not the sum of per-serving values times servings."""
    expected = _sum_items(items)
    flags: list[str] = []
    _compare_total(
        flags,
        day_number,
        "calories",
        totals.calories_kcal,
        expected.calories_kcal,
        _KCAL_TOLERANCE,
    )
    _compare_total(
        flags,
        day_number,
        "protein_g",
        totals.protein_g,
        expected.protein_g,
        _GRAM_TOLERANCE,
    )
    _compare_total(
        flags,
        day_number,
        "fat_g",
        totals.fat_g,
        expected.fat_g,
        _GRAM_TOLERANCE,
    )
    _compare_total(
        flags,
        day_number,
        "carbohydrates_g",
        totals.carbohydrates_g,
        expected.carbohydrates_g,
        _GRAM_TOLERANCE,
    )
    _compare_total(
        flags,
        day_number,
        "fiber_g",
        totals.fiber_g,
        expected.fiber_g,
        _GRAM_TOLERANCE,
    )
    return flags


def _dish_flags(dish: DishNutrition) -> list[tuple[int, str]]:
    flags: list[tuple[int, str]] = []
    atwater = _atwater_flag(dish)
    if atwater is not None:
        flags.append((1, atwater))
    density = _density_flag(dish)
    if density is not None:
        flags.append((2, density))
    flags.extend((3, message) for message in _consistency_flags(dish))
    flags.extend((4, message) for message in _bounds_flags(dish))
    return flags


def _atwater_flag(dish: DishNutrition) -> str | None:
    expected = 4 * dish.protein_g + 4 * dish.carbohydrates_g + 9 * dish.fat_g
    calories = dish.calories_kcal
    if expected == 0:
        if calories == 0:
            return None
        return (
            f"{dish.path} '{dish.name}': calories {_num(calories)} vs "
            f"4P+4C+9F {_num(expected)}"
        )
    gap = abs(calories - expected) / abs(expected)
    if gap <= _ATWATER_TOLERANCE:
        return None
    pct = round(abs(calories - expected) / abs(expected) * 100)
    sign = "+" if calories >= expected else "-"
    return (
        f"{dish.path} '{dish.name}': calories {_num(calories)} vs "
        f"4P+4C+9F {_num(expected)} ({sign}{pct}%)"
    )


def _density_flag(dish: DishNutrition) -> str | None:
    grams = dish.ingredient_grams
    if grams is None:
        return None
    total = sum(grams)
    if total <= 0:
        return None
    per_100 = dish.calories_kcal / total * 100
    if 20 <= per_100 <= 900:
        return None
    return (
        f"{dish.path} '{dish.name}': {_num(per_100)} kcal/100g "
        f"is outside 20–900"
    )


def _consistency_flags(dish: DishNutrition) -> list[str]:
    flags: list[str] = []
    for field_name, value in (
        ("calories_kcal", dish.calories_kcal),
        ("protein_g", dish.protein_g),
        ("fat_g", dish.fat_g),
        ("carbohydrates_g", dish.carbohydrates_g),
        ("fiber_g", dish.fiber_g),
    ):
        if value < 0:
            flags.append(
                f"{dish.path} '{dish.name}': {field_name} {_num(value)} is negative"
            )
    if dish.fiber_g > dish.carbohydrates_g:
        flags.append(
            f"{dish.path} '{dish.name}': fiber_g {_num(dish.fiber_g)} > "
            f"carbohydrates_g {_num(dish.carbohydrates_g)}"
        )
    return flags


def _bounds_flags(dish: DishNutrition) -> list[str]:
    values = {
        "calories_kcal": dish.calories_kcal,
        "protein_g": dish.protein_g,
        "fat_g": dish.fat_g,
        "carbohydrates_g": dish.carbohydrates_g,
        "fiber_g": dish.fiber_g,
    }
    flags: list[str] = []
    for field_name, (low, high) in BOUNDS.items():
        value = values[field_name]
        if value < low or value > high:
            flags.append(
                f"{dish.path} '{dish.name}': {field_name} {_num(value)} "
                f"outside {_num(low)}–{_num(high)}"
            )
    return flags


def _sum_items(items: Sequence[ServingNutrition]) -> DayTotals:
    calories = protein = fat = carbs = fiber = 0.0
    for item in items:
        servings = item.servings
        calories += item.calories_kcal * servings
        protein += item.protein_g * servings
        fat += item.fat_g * servings
        carbs += item.carbohydrates_g * servings
        fiber += item.fiber_g * servings
    return DayTotals(
        calories_kcal=calories,
        protein_g=protein,
        fat_g=fat,
        carbohydrates_g=carbs,
        fiber_g=fiber,
    )


def _compare_total(
    flags: list[str],
    day_number: int,
    field_name: str,
    declared: float,
    expected: float,
    tolerance: float,
) -> None:
    if abs(declared - expected) > tolerance:
        flags.append(
            f"Day {day_number} {field_name} {_num(declared)} != "
            f"item sum {_num(expected)}"
        )


def _num(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 0.05:
        return str(int(rounded))
    return f"{value:.1f}"
