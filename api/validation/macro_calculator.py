"""MacroCalculator — aggregates plan-item nutrition snapshots (RISK-04 related display)."""

from __future__ import annotations

from validation.types import (
    NutritionSummary,
    PlanDayView,
    PlanDraftView,
    PlanItemView,
    PlanNutritionSummary,
)


def _nz(value: float | None) -> float:
    return 0.0 if value is None else float(value)


class MacroCalculator:
    def compute_day_totals(
        self, plan_items: list[PlanItemView] | tuple[PlanItemView, ...]
    ) -> NutritionSummary:
        return NutritionSummary(
            calories=sum(_nz(i.calories) for i in plan_items),
            protein_g=sum(_nz(i.protein_g) for i in plan_items),
            carbs_g=sum(_nz(i.carbs_g) for i in plan_items),
            fat_g=sum(_nz(i.fat_g) for i in plan_items),
            fiber_g=sum(_nz(i.fiber_g) for i in plan_items),
        )

    def compute_plan_summary(
        self, plan_days: list[PlanDayView] | tuple[PlanDayView, ...] | PlanDraftView
    ) -> PlanNutritionSummary:
        days = plan_days.days if isinstance(plan_days, PlanDraftView) else plan_days
        if not days:
            empty = NutritionSummary(0.0, 0.0, 0.0, 0.0, 0.0)
            return PlanNutritionSummary(average=empty, per_day=())

        per_day = tuple(self.compute_day_totals(day.items) for day in days)
        n = len(per_day)
        average = NutritionSummary(
            calories=sum(d.calories for d in per_day) / n,
            protein_g=sum(d.protein_g for d in per_day) / n,
            carbs_g=sum(d.carbs_g for d in per_day) / n,
            fat_g=sum(d.fat_g for d in per_day) / n,
            fiber_g=sum(d.fiber_g for d in per_day) / n,
        )
        return PlanNutritionSummary(average=average, per_day=per_day)
