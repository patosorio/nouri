"""Unit tests for the validation layer — docs/8_TEST_PLAN.md §3.1."""

from __future__ import annotations

from uuid import uuid4

import pytest

from exceptions import NutritionOutOfRangeError
from validation.exclusion_checker import ExclusionChecker
from validation.macro_calculator import MacroCalculator
from validation.nutrition_validator import NutritionValidator
from validation.per_day_macro_checker import PerDayMacroChecker
from validation.plan_validator import PlanValidator
from validation.ratio_checker import RatioChecker
from validation.repair_strategy import RepairStrategy
from validation.types import (
    ExclusionView,
    MacroTargets,
    NutritionPerServing,
    PlanDayView,
    PlanDraftView,
    PlanItemView,
    RecipeIngredientView,
    RecipeView,
    UserProfileView,
)
from validation.variety_checker import VarietyChecker

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PEANUT_ID = uuid4()
SPINACH_ID = uuid4()
TOFU_ID = uuid4()


@pytest.fixture
def exclusion_checker() -> ExclusionChecker:
    return ExclusionChecker()


@pytest.fixture
def macro_calculator() -> MacroCalculator:
    return MacroCalculator()


@pytest.fixture
def targets() -> MacroTargets:
    return MacroTargets(
        calories=2000.0,
        protein_g=80.0,
        carbs_g=250.0,
        fat_g=70.0,
        fiber_g=30.0,
    )


def _item(
    day: int,
    name: str,
    *,
    calories: float | None = 500.0,
    protein_g: float | None = 20.0,
    carbs_g: float | None = 60.0,
    fat_g: float | None = 15.0,
    fiber_g: float | None = 8.0,
    prep_method: str | None = "raw",
    primary_protein: str | None = "legumes",
    ingredients: tuple[RecipeIngredientView, ...] = (),
    recipe_id=None,
) -> PlanItemView:
    return PlanItemView(
        day_number=day,
        name=name,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        prep_method=prep_method,
        primary_protein=primary_protein,
        ingredients=ingredients,
        recipe_id=recipe_id,
    )


def _day(num: int, *items: PlanItemView) -> PlanDayView:
    return PlanDayView(day_number=num, items=items)


# ---------------------------------------------------------------------------
# ExclusionChecker
# ---------------------------------------------------------------------------


def test_check_recipe_clean(exclusion_checker: ExclusionChecker) -> None:
    recipe = RecipeView(
        id=uuid4(),
        ingredients=(
            RecipeIngredientView(name="spinach", ingredient_id=SPINACH_ID),
        ),
    )
    exclusions = (
        ExclusionView(raw_name="peanuts", ingredient_id=PEANUT_ID),
    )
    assert exclusion_checker.check_recipe(recipe, exclusions) is True


def test_check_recipe_excluded_by_ingredient_id(
    exclusion_checker: ExclusionChecker,
) -> None:
    recipe = RecipeView(
        id=uuid4(),
        ingredients=(
            RecipeIngredientView(name="peanuts", ingredient_id=PEANUT_ID),
        ),
    )
    exclusions = (
        ExclusionView(raw_name="peanuts", ingredient_id=PEANUT_ID),
    )
    assert exclusion_checker.check_recipe(recipe, exclusions) is False


def test_check_recipe_excluded_by_alias(exclusion_checker: ExclusionChecker) -> None:
    recipe = RecipeView(
        id=uuid4(),
        ingredients=(
            RecipeIngredientView(
                name="peanuts",
                ingredient_id=uuid4(),
                aliases=("groundnuts",),
            ),
        ),
    )
    exclusions = (
        ExclusionView(
            raw_name="groundnuts",
            ingredient_id=None,
            aliases=("peanuts", "groundnuts"),
        ),
    )
    assert exclusion_checker.check_recipe(recipe, exclusions) is False


def test_filter_candidates_removes_excluded(
    exclusion_checker: ExclusionChecker,
) -> None:
    clean = RecipeView(
        id=uuid4(),
        ingredients=(
            RecipeIngredientView(name="spinach", ingredient_id=SPINACH_ID),
        ),
    )
    dirty = RecipeView(
        id=uuid4(),
        ingredients=(
            RecipeIngredientView(name="peanuts", ingredient_id=PEANUT_ID),
        ),
    )
    exclusions = (
        ExclusionView(raw_name="peanuts", ingredient_id=PEANUT_ID),
    )
    result = exclusion_checker.filter_candidates([clean, dirty], exclusions)
    assert result == [clean]


def test_unresolved_ingredient_falls_back_to_name_match(
    exclusion_checker: ExclusionChecker,
) -> None:
    recipe = RecipeView(
        id=uuid4(),
        ingredients=(
            RecipeIngredientView(name="Peanuts", ingredient_id=None),
        ),
    )
    exclusions = (ExclusionView(raw_name="peanuts", ingredient_id=None),)
    assert exclusion_checker.check_recipe(recipe, exclusions) is False


# ---------------------------------------------------------------------------
# MacroCalculator
# ---------------------------------------------------------------------------


def test_compute_day_totals_sums_snapshots(
    macro_calculator: MacroCalculator,
) -> None:
    items = (
        _item(1, "a", calories=100, protein_g=10, carbs_g=20, fat_g=5, fiber_g=2),
        _item(1, "b", calories=200, protein_g=15, carbs_g=30, fat_g=8, fiber_g=3),
    )
    totals = macro_calculator.compute_day_totals(items)
    assert totals.calories == 300
    assert totals.protein_g == 25
    assert totals.carbs_g == 50
    assert totals.fat_g == 13
    assert totals.fiber_g == 5


def test_compute_day_totals_null_snapshots_treated_as_zero(
    macro_calculator: MacroCalculator,
) -> None:
    items = (
        _item(1, "a", calories=None, protein_g=None, carbs_g=None, fat_g=None, fiber_g=None),
        _item(1, "b", calories=100, protein_g=10, carbs_g=20, fat_g=5, fiber_g=1),
    )
    totals = macro_calculator.compute_day_totals(items)
    assert totals.calories == 100
    assert totals.protein_g == 10


def test_compute_plan_summary_averages_across_days(
    macro_calculator: MacroCalculator,
) -> None:
    days = (
        _day(1, _item(1, "a", calories=1000, protein_g=40, carbs_g=100, fat_g=30, fiber_g=10)),
        _day(2, _item(2, "b", calories=2000, protein_g=80, carbs_g=200, fat_g=60, fiber_g=20)),
    )
    summary = macro_calculator.compute_plan_summary(days)
    assert summary.average.calories == 1500
    assert summary.average.protein_g == 60
    assert len(summary.per_day) == 2


# ---------------------------------------------------------------------------
# PerDayMacroChecker
# ---------------------------------------------------------------------------


def test_within_tolerance_passes(targets: MacroTargets) -> None:
    # 10% above target — within ±20%
    days = (
        _day(
            1,
            _item(
                1,
                "meal",
                calories=2200,
                protein_g=88,
                carbs_g=275,
                fat_g=77,
                fiber_g=33,
            ),
        ),
    )
    results = PerDayMacroChecker().check(days, targets)
    assert len(results) == 1
    assert results[0].passed is True


def test_above_tolerance_fails_with_repair_hint(targets: MacroTargets) -> None:
    # 25% above calories target
    days = (
        _day(
            1,
            _item(
                1,
                "meal",
                calories=2500,
                protein_g=80,
                carbs_g=250,
                fat_g=70,
                fiber_g=30,
            ),
        ),
    )
    results = PerDayMacroChecker().check(days, targets)
    assert results[0].passed is False
    assert any("calories" in e and "above" in e for e in results[0].errors)
    assert any("day 1" in h.lower() for h in results[0].repair_hints)


def test_below_tolerance_fails_with_repair_hint(targets: MacroTargets) -> None:
    days = (
        _day(
            2,
            _item(
                2,
                "meal",
                calories=1000,
                protein_g=80,
                carbs_g=250,
                fat_g=70,
                fiber_g=30,
            ),
        ),
    )
    results = PerDayMacroChecker().check(days, targets)
    assert results[0].passed is False
    assert any("calories" in e and "below" in e for e in results[0].errors)
    assert any("day 2" in h.lower() for h in results[0].repair_hints)


# ---------------------------------------------------------------------------
# RatioChecker
# ---------------------------------------------------------------------------


def test_raw_percentage_within_tolerance_passes() -> None:
    # 80% target: 4 raw + 1 cooked = 80%; also 78% case: ~4 raw of ~5.1 ≈ use 7 raw + 2 cooked = 77.8%
    items_raw = [_item(1, f"r{i}", prep_method="raw") for i in range(7)]
    items_cooked = [_item(1, f"c{i}", prep_method="baked") for i in range(2)]
    days = (_day(1, *items_raw, *items_cooked),)
    result = RatioChecker().check_plan(days, "raw_80_cooked_20")
    assert result.passed is True
    assert abs(result.actual_raw_pct - 77.777) < 0.1 or abs(result.actual_raw_pct - 80.0) < 11


def test_raw_percentage_outside_tolerance_fails() -> None:
    # 80% target but 100% raw → outside ±10
    days = (_day(1, *[_item(1, f"r{i}", prep_method="raw") for i in range(5)]),)
    result = RatioChecker().check_plan(days, "raw_80_cooked_20")
    # 100% vs 80% = 20 points > 10 → fail
    assert result.passed is False
    assert result.repair_hints


# ---------------------------------------------------------------------------
# VarietyChecker
# ---------------------------------------------------------------------------


def test_protein_source_not_repeated_passes() -> None:
    days = (
        _day(1, _item(1, "a", primary_protein="tofu_soy")),
        _day(2, _item(2, "b", primary_protein="legumes")),
        _day(3, _item(3, "c", primary_protein="nuts_seeds")),
    )
    assert VarietyChecker().check_protein_variety(days).passed is True


def test_protein_source_repeated_3_consecutive_days_fails() -> None:
    days = (
        _day(1, _item(1, "a", primary_protein="tofu_soy")),
        _day(2, _item(2, "b", primary_protein="tofu_soy")),
        _day(3, _item(3, "c", primary_protein="tofu_soy")),
    )
    result = VarietyChecker().check_protein_variety(days)
    assert result.passed is False
    assert any("tofu_soy" in e for e in result.errors)


def test_repair_hint_identifies_repeated_ingredient_and_day() -> None:
    spinach = RecipeIngredientView(name="spinach", ingredient_id=SPINACH_ID)
    # 3 of 4 recipes contain spinach → 75% > 60%
    days = (
        _day(1, _item(1, "a", ingredients=(spinach,), recipe_id=uuid4())),
        _day(2, _item(2, "b", ingredients=(spinach,), recipe_id=uuid4())),
        _day(3, _item(3, "c", ingredients=(spinach,), recipe_id=uuid4())),
        _day(
            4,
            _item(
                4,
                "d",
                ingredients=(RecipeIngredientView(name="kale", ingredient_id=uuid4()),),
                recipe_id=uuid4(),
            ),
        ),
    )
    result = VarietyChecker().check_ingredient_variety(days)
    assert result.passed is False
    assert any("spinach" in h and "day" in h for h in result.repair_hints)


# ---------------------------------------------------------------------------
# NutritionValidator
# ---------------------------------------------------------------------------


def test_calories_within_bounds_passes() -> None:
    nutrition = NutritionPerServing(
        calories_kcal=320,
        protein_g=12,
        fat_g=8,
        carbohydrates_g=45,
    )
    assert NutritionValidator().check(nutrition).passed is True


def test_calories_above_max_raises_NutritionOutOfRangeError() -> None:
    nutrition = NutritionPerServing(
        calories_kcal=4000,
        protein_g=12,
        fat_g=8,
        carbohydrates_g=45,
    )
    with pytest.raises(NutritionOutOfRangeError) as exc:
        NutritionValidator().check(nutrition)
    assert exc.value.field == "calories_kcal"


def test_calories_below_min_raises_NutritionOutOfRangeError() -> None:
    nutrition = NutritionPerServing(
        calories_kcal=10,
        protein_g=12,
        fat_g=8,
        carbohydrates_g=45,
    )
    with pytest.raises(NutritionOutOfRangeError) as exc:
        NutritionValidator().check(nutrition)
    assert exc.value.field == "calories_kcal"


def test_protein_g_zero_passes() -> None:
    nutrition = NutritionPerServing(
        calories_kcal=200,
        protein_g=0,
        fat_g=5,
        carbohydrates_g=40,
    )
    assert NutritionValidator().check(nutrition).passed is True


def test_all_fields_checked() -> None:
    validator = NutritionValidator()
    # fat above max
    with pytest.raises(NutritionOutOfRangeError) as fat_exc:
        validator.check(
            NutritionPerServing(
                calories_kcal=200, protein_g=10, fat_g=150, carbohydrates_g=40
            )
        )
    assert fat_exc.value.field == "fat_g"

    # carbs above max
    with pytest.raises(NutritionOutOfRangeError) as carb_exc:
        validator.check(
            NutritionPerServing(
                calories_kcal=200, protein_g=10, fat_g=10, carbohydrates_g=250
            )
        )
    assert carb_exc.value.field == "carbohydrates_g"

    # protein above max (RISK-06 max 120)
    with pytest.raises(NutritionOutOfRangeError) as prot_exc:
        validator.check(
            NutritionPerServing(
                calories_kcal=200, protein_g=130, fat_g=10, carbohydrates_g=40
            )
        )
    assert prot_exc.value.field == "protein_g"

    # fiber above max (RISK-06 max 50)
    with pytest.raises(NutritionOutOfRangeError) as fiber_exc:
        validator.check(
            NutritionPerServing(
                calories_kcal=200,
                protein_g=10,
                fat_g=10,
                carbohydrates_g=40,
                fiber_g=60,
            )
        )
    assert fiber_exc.value.field == "fiber_g"


# ---------------------------------------------------------------------------
# PlanValidator + RepairStrategy
# ---------------------------------------------------------------------------


def _balanced_plan() -> PlanDraftView:
    """7 days, alternating proteins, ~50% raw, macros near 2000."""
    days = []
    proteins = ["legumes", "tofu_soy", "nuts_seeds", "none"]
    for d in range(1, 8):
        protein = proteins[(d - 1) % len(proteins)]
        # 2 raw + 2 cooked = 50%
        items = (
            _item(
                d,
                f"raw-{d}-a",
                calories=500,
                protein_g=20,
                carbs_g=62,
                fat_g=17,
                fiber_g=7,
                prep_method="raw",
                primary_protein=protein,
                ingredients=(
                    RecipeIngredientView(name=f"ing-{d}-a", ingredient_id=uuid4()),
                ),
                recipe_id=uuid4(),
            ),
            _item(
                d,
                f"raw-{d}-b",
                calories=500,
                protein_g=20,
                carbs_g=63,
                fat_g=18,
                fiber_g=8,
                prep_method="blended",
                primary_protein=protein,
                ingredients=(
                    RecipeIngredientView(name=f"ing-{d}-b", ingredient_id=uuid4()),
                ),
                recipe_id=uuid4(),
            ),
            _item(
                d,
                f"cooked-{d}-a",
                calories=500,
                protein_g=20,
                carbs_g=62,
                fat_g=17,
                fiber_g=7,
                prep_method="baked",
                primary_protein="none",
                ingredients=(
                    RecipeIngredientView(name=f"ing-{d}-c", ingredient_id=uuid4()),
                ),
                recipe_id=uuid4(),
            ),
            _item(
                d,
                f"cooked-{d}-b",
                calories=500,
                protein_g=20,
                carbs_g=63,
                fat_g=18,
                fiber_g=8,
                prep_method="steamed",
                primary_protein="none",
                ingredients=(
                    RecipeIngredientView(name=f"ing-{d}-d", ingredient_id=uuid4()),
                ),
                recipe_id=uuid4(),
            ),
        )
        days.append(_day(d, *items))
    return PlanDraftView(days=tuple(days))


def test_all_checkers_pass_returns_validation_passed_true(
    targets: MacroTargets,
) -> None:
    plan = _balanced_plan()
    profile = UserProfileView(cooking_type="raw_50_cooked_50", exclusions=())
    result = PlanValidator().validate(plan, profile, targets)
    assert result.passed is True
    assert result.repair_instructions.is_empty


def test_exclusion_failure_stops_validation_returns_passed_false(
    targets: MacroTargets,
) -> None:
    peanut = RecipeIngredientView(name="peanuts", ingredient_id=PEANUT_ID)
    plan = PlanDraftView(
        days=(
            _day(
                1,
                _item(
                    1,
                    "satay",
                    ingredients=(peanut,),
                    prep_method="baked",
                    primary_protein="nuts_seeds",
                ),
            ),
        )
    )
    profile = UserProfileView(
        cooking_type="cooked_100",
        exclusions=(ExclusionView(raw_name="peanuts", ingredient_id=PEANUT_ID),),
    )
    result = PlanValidator().validate(plan, profile, targets)
    assert result.passed is False
    assert len(result.checker_results) == 1
    assert result.checker_results[0].checker == "ExclusionChecker"


def test_multiple_checker_failures_all_reported_in_errors(
    targets: MacroTargets,
) -> None:
    # Bad macros + bad ratio (all raw vs cooked_100) + tofu 3 consecutive days
    days = (
        _day(
            1,
            _item(
                1,
                "a",
                calories=5000,
                protein_g=20,
                carbs_g=60,
                fat_g=15,
                prep_method="raw",
                primary_protein="tofu_soy",
                ingredients=(RecipeIngredientView(name="x1", ingredient_id=uuid4()),),
                recipe_id=uuid4(),
            ),
        ),
        _day(
            2,
            _item(
                2,
                "b",
                calories=5000,
                protein_g=20,
                carbs_g=60,
                fat_g=15,
                prep_method="raw",
                primary_protein="tofu_soy",
                ingredients=(RecipeIngredientView(name="x2", ingredient_id=uuid4()),),
                recipe_id=uuid4(),
            ),
        ),
        _day(
            3,
            _item(
                3,
                "c",
                calories=5000,
                protein_g=20,
                carbs_g=60,
                fat_g=15,
                prep_method="raw",
                primary_protein="tofu_soy",
                ingredients=(RecipeIngredientView(name="x3", ingredient_id=uuid4()),),
                recipe_id=uuid4(),
            ),
        ),
    )
    plan = PlanDraftView(days=days)
    profile = UserProfileView(cooking_type="cooked_100", exclusions=())
    result = PlanValidator().validate(plan, profile, targets)
    assert result.passed is False
    checkers = {r.checker for r in result.checker_results if not r.passed}
    assert "PerDayMacroChecker" in checkers
    assert "RatioChecker" in checkers
    assert "VarietyChecker" in checkers
    assert len(result.errors) >= 3


def test_repair_strategy_produces_non_empty_instructions_on_failure(
    targets: MacroTargets,
) -> None:
    days = (
        _day(
            1,
            _item(
                1,
                "heavy",
                calories=5000,
                protein_g=20,
                carbs_g=60,
                fat_g=15,
                prep_method="raw",
                primary_protein="legumes",
                recipe_id=uuid4(),
            ),
        ),
    )
    plan = PlanDraftView(days=days)
    profile = UserProfileView(cooking_type="cooked_100", exclusions=())
    result = PlanValidator().validate(plan, profile, targets)
    assert result.passed is False
    assert not result.repair_instructions.is_empty

    # Direct RepairStrategy coverage
    instructions = RepairStrategy().build_repair_instructions(result.checker_results)
    assert len(instructions.instructions) > 0
