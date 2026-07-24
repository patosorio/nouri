"""PerDayMacroChecker — ±20% of daily targets (docs/7_TECH_SPEC.md §6.1)."""

from __future__ import annotations

from validation.macro_calculator import MacroCalculator
from validation.types import (
    DayMacroCheckResult,
    MacroTargets,
    PlanDayView,
    PlanDraftView,
)

MACRO_TOLERANCE = 0.20

_FIELDS = (
    ("calories", "calories"),
    ("protein_g", "protein_g"),
    ("carbs_g", "carbs_g"),
    ("fat_g", "fat_g"),
)


class PerDayMacroChecker:
    def __init__(self, calculator: MacroCalculator | None = None) -> None:
        self._calculator = calculator or MacroCalculator()

    def check(
        self,
        plan_days: list[PlanDayView] | tuple[PlanDayView, ...] | PlanDraftView,
        targets: MacroTargets,
    ) -> list[DayMacroCheckResult]:
        days = plan_days.days if isinstance(plan_days, PlanDraftView) else plan_days
        results: list[DayMacroCheckResult] = []

        for day in days:
            actual = self._calculator.compute_day_totals(day.items)
            errors: list[str] = []
            hints: list[str] = []

            for attr, label in _FIELDS:
                target_val = getattr(targets, attr)
                actual_val = getattr(actual, attr)
                if target_val == 0:
                    if actual_val != 0:
                        errors.append(
                            f"Day {day.day_number}: {label} actual {actual_val} "
                            f"but target is 0"
                        )
                    continue

                ratio = actual_val / target_val
                if ratio > 1.0 + MACRO_TOLERANCE:
                    pct = (ratio - 1.0) * 100
                    msg = (
                        f"Day {day.day_number}: {label} is {pct:.0f}% above target "
                        f"({actual_val:.1f} vs {target_val:.1f})"
                    )
                    errors.append(msg)
                    hints.append(
                        f"Reduce {label} on day {day.day_number} by about "
                        f"{actual_val - target_val * (1.0 + MACRO_TOLERANCE):.1f} "
                        f"to fall within ±{MACRO_TOLERANCE * 100:.0f}% of target."
                    )
                elif ratio < 1.0 - MACRO_TOLERANCE:
                    pct = (1.0 - ratio) * 100
                    msg = (
                        f"Day {day.day_number}: {label} is {pct:.0f}% below target "
                        f"({actual_val:.1f} vs {target_val:.1f})"
                    )
                    errors.append(msg)
                    hints.append(
                        f"Increase {label} on day {day.day_number} by about "
                        f"{target_val * (1.0 - MACRO_TOLERANCE) - actual_val:.1f} "
                        f"to fall within ±{MACRO_TOLERANCE * 100:.0f}% of target."
                    )

            results.append(
                DayMacroCheckResult(
                    day_number=day.day_number,
                    passed=len(errors) == 0,
                    actual=actual,
                    errors=tuple(errors),
                    repair_hints=tuple(hints),
                )
            )

        return results
