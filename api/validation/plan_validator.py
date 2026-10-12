"""PlanValidator — orchestrates deterministic checkers (docs/7_TECH_SPEC.md §6.1)."""

from __future__ import annotations

from validation.exclusion_checker import ExclusionChecker
from validation.macro_calculator import MacroCalculator
from validation.per_day_macro_checker import PerDayMacroChecker
from validation.ratio_checker import RatioChecker
from validation.repair_strategy import RepairStrategy
from validation.types import (
    CheckResult,
    MacroTargets,
    PlanDraftView,
    PlanValidationResult,
    RecipeView,
    UserProfileView,
)
from validation.variety_checker import VarietyChecker


class PlanValidator:
    def __init__(
        self,
        exclusion_checker: ExclusionChecker | None = None,
        macro_calculator: MacroCalculator | None = None,
        per_day_macro_checker: PerDayMacroChecker | None = None,
        ratio_checker: RatioChecker | None = None,
        variety_checker: VarietyChecker | None = None,
        repair_strategy: RepairStrategy | None = None,
    ) -> None:
        self._exclusions = exclusion_checker or ExclusionChecker()
        self._macros = macro_calculator or MacroCalculator()
        self._per_day = per_day_macro_checker or PerDayMacroChecker(self._macros)
        self._ratio = ratio_checker or RatioChecker()
        self._variety = variety_checker or VarietyChecker()
        self._repair = repair_strategy or RepairStrategy()

    def validate(
        self,
        plan: PlanDraftView,
        user_profile: UserProfileView,
        targets: MacroTargets,
    ) -> PlanValidationResult:
        checker_results: list[CheckResult] = []

        # 1. ExclusionChecker — hard failure; stop early (test plan §3.1)
        exclusion_result = self._check_exclusions(plan, user_profile)
        checker_results.append(exclusion_result)
        if not exclusion_result.passed:
            repair = self._repair.build_repair_instructions(checker_results)
            return PlanValidationResult(
                passed=False,
                errors=exclusion_result.errors,
                repair_hints=exclusion_result.repair_hints,
                checker_results=tuple(checker_results),
                repair_instructions=repair,
            )

        # 2. MacroCalculator — compute totals (not a pass/fail gate by itself)
        plan_summary = self._macros.compute_plan_summary(plan.days)
        day_totals = plan_summary.per_day

        # 3. PerDayMacroChecker
        day_results = self._per_day.check(plan.days, targets)
        macro_errors: list[str] = []
        macro_hints: list[str] = []
        for day_result in day_results:
            macro_errors.extend(day_result.errors)
            macro_hints.extend(day_result.repair_hints)
        checker_results.append(
            CheckResult(
                checker="PerDayMacroChecker",
                passed=all(r.passed for r in day_results),
                errors=tuple(macro_errors),
                repair_hints=tuple(macro_hints),
            )
        )

        # 4. RatioChecker
        ratio = self._ratio.check_plan(plan.days, user_profile.cooking_type)
        checker_results.append(
            CheckResult(
                checker="RatioChecker",
                passed=ratio.passed,
                errors=ratio.errors,
                repair_hints=ratio.repair_hints,
            )
        )

        # 5. VarietyChecker (protein run + non-staple ingredient share + meal repeat)
        protein = self._variety.check_protein_variety(plan.days)
        ingredient = self._variety.check_ingredient_variety(plan.days)
        meal_repeat = self._variety.check_meal_repeat(plan.days)
        variety_passed = (
            protein.passed and ingredient.passed and meal_repeat.passed
        )
        checker_results.append(
            CheckResult(
                checker="VarietyChecker",
                passed=variety_passed,
                errors=protein.errors + ingredient.errors + meal_repeat.errors,
                repair_hints=(
                    protein.repair_hints
                    + ingredient.repair_hints
                    + meal_repeat.repair_hints
                ),
            )
        )

        passed = all(r.passed for r in checker_results)
        all_errors = tuple(e for r in checker_results for e in r.errors)
        all_hints = tuple(h for r in checker_results for h in r.repair_hints)
        repair = (
            self._repair.build_repair_instructions(checker_results)
            if not passed
            else RepairStrategy().build_repair_instructions(())
        )

        return PlanValidationResult(
            passed=passed,
            errors=all_errors,
            repair_hints=all_hints,
            checker_results=tuple(checker_results),
            repair_instructions=repair,
            day_totals=day_totals,
            plan_summary=plan_summary,
        )

    def _check_exclusions(
        self, plan: PlanDraftView, user_profile: UserProfileView
    ) -> CheckResult:
        if not user_profile.exclusions:
            return CheckResult(checker="ExclusionChecker", passed=True)

        errors: list[str] = []
        for day in plan.days:
            for item in day.items:
                from uuid import NAMESPACE_URL, uuid5

                recipe_id = item.recipe_id or uuid5(NAMESPACE_URL, item.name)
                recipe = RecipeView(id=recipe_id, ingredients=item.ingredients)
                if not self._exclusions.check_recipe(recipe, user_profile.exclusions):
                    errors.append(
                        f"Day {day.day_number} item '{item.name}' contains an "
                        f"excluded ingredient"
                    )

        if not errors:
            return CheckResult(checker="ExclusionChecker", passed=True)

        return CheckResult(
            checker="ExclusionChecker",
            passed=False,
            errors=tuple(errors),
            repair_hints=(
                (
                    "Remove or replace items containing excluded ingredients. "
                    "Exclusion violations cannot be soft-repaired — regenerate without them."
                ),
            ),
        )
