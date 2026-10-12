"""In-memory domain types for the validation layer (no DB / no AI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RecipeIngredientView:
    name: str
    ingredient_id: UUID | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecipeView:
    id: UUID
    ingredients: tuple[RecipeIngredientView, ...] = ()
    primary_protein: str | None = None


@dataclass(frozen=True, slots=True)
class ExclusionView:
    raw_name: str
    ingredient_id: UUID | None = None
    # Aliases of the excluded canonical ingredient (RISK-05)
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanItemView:
    day_number: int
    name: str
    slot: str = "lunch"
    prep_method: str | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    primary_protein: str | None = None
    recipe_id: UUID | None = None
    ingredients: tuple[RecipeIngredientView, ...] = ()
    nutrition_unknown: bool = False


@dataclass(frozen=True, slots=True)
class PlanDayView:
    day_number: int
    items: tuple[PlanItemView, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanDraftView:
    days: tuple[PlanDayView, ...] = ()


@dataclass(frozen=True, slots=True)
class UserProfileView:
    cooking_type: str
    exclusions: tuple[ExclusionView, ...] = ()


@dataclass(frozen=True, slots=True)
class MacroTargets:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float = 0.0


@dataclass(frozen=True, slots=True)
class NutritionSummary:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float = 0.0


@dataclass(frozen=True, slots=True)
class PlanNutritionSummary:
    average: NutritionSummary
    per_day: tuple[NutritionSummary, ...] = ()


@dataclass(frozen=True, slots=True)
class NutritionPerServing:
    calories_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float
    fiber_g: float = 0.0


@dataclass(frozen=True, slots=True)
class CheckResult:
    checker: str
    passed: bool
    errors: tuple[str, ...] = ()
    repair_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DayMacroCheckResult:
    day_number: int
    passed: bool
    actual: NutritionSummary
    errors: tuple[str, ...] = ()
    repair_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RatioCheckResult:
    passed: bool
    target_raw_pct: float
    actual_raw_pct: float
    errors: tuple[str, ...] = ()
    repair_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VarietyCheckResult:
    passed: bool
    errors: tuple[str, ...] = ()
    repair_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NutritionValidationResult:
    passed: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RepairInstruction:
    checker: str
    guidance: str


@dataclass(frozen=True, slots=True)
class RepairInstructions:
    instructions: tuple[RepairInstruction, ...] = ()

    @property
    def is_empty(self) -> bool:
        return len(self.instructions) == 0


@dataclass(frozen=True, slots=True)
class PlanValidationResult:
    passed: bool
    errors: tuple[str, ...] = ()
    repair_hints: tuple[str, ...] = ()
    checker_results: tuple[CheckResult, ...] = ()
    repair_instructions: RepairInstructions = field(
        default_factory=lambda: RepairInstructions()
    )
    day_totals: tuple[NutritionSummary, ...] = ()
    plan_summary: PlanNutritionSummary | None = None
