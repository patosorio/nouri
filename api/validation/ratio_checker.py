"""RatioChecker — raw/cooked ratio within ±10 percentage points (RISK / tech spec §6.1)."""

from __future__ import annotations

from validation.types import PlanDayView, PlanDraftView, RatioCheckResult

# Target raw % from docs/3_ERD.md cooking_type_enum
COOKING_TYPE_RAW_PCT: dict[str, float] = {
    "raw_100": 100.0,
    "raw_80_cooked_20": 80.0,
    "raw_70_cooked_30": 70.0,
    "raw_50_cooked_50": 50.0,
    "cooked_100": 0.0,
}

RAW_PREP_METHODS = frozenset(
    {"raw", "juiced", "blended", "dehydrated", "sprouted", "fermented"}
)

RATIO_TOLERANCE_POINTS = 10.0


class RatioChecker:
    def check_plan(
        self,
        plan_days: list[PlanDayView] | tuple[PlanDayView, ...] | PlanDraftView,
        target_cooking_type: str,
    ) -> RatioCheckResult:
        days = plan_days.days if isinstance(plan_days, PlanDraftView) else plan_days
        target = COOKING_TYPE_RAW_PCT.get(target_cooking_type)
        if target is None:
            return RatioCheckResult(
                passed=False,
                target_raw_pct=0.0,
                actual_raw_pct=0.0,
                errors=(f"Unknown cooking_type: {target_cooking_type}",),
                repair_hints=(
                    f"Use a valid cooking_type enum value; got {target_cooking_type}",
                ),
            )

        total = 0
        raw_count = 0
        for day in days:
            for item in day.items:
                total += 1
                if item.prep_method is not None and item.prep_method in RAW_PREP_METHODS:
                    raw_count += 1

        actual = 0.0 if total == 0 else (raw_count / total) * 100.0
        delta = abs(actual - target)
        passed = delta <= RATIO_TOLERANCE_POINTS

        if passed:
            return RatioCheckResult(
                passed=True,
                target_raw_pct=target,
                actual_raw_pct=actual,
            )

        direction = "increase" if actual < target else "decrease"
        hint = (
            f"Raw percentage is {actual:.1f}% vs target {target:.1f}% "
            f"(tolerance ±{RATIO_TOLERANCE_POINTS:.0f} points). "
            f"Repair: {direction} raw prep_method slots."
        )
        return RatioCheckResult(
            passed=False,
            target_raw_pct=target,
            actual_raw_pct=actual,
            errors=(hint,),
            repair_hints=(hint,),
        )
