"""NutritionValidator — plausibility bounds (docs/6_DATA_INTEGRITY.md RISK-06)."""

from __future__ import annotations

from exceptions import NutritionOutOfRangeError
from validation.types import NutritionPerServing, NutritionValidationResult

# Authoritative bounds: docs/6_DATA_INTEGRITY.md RISK-06
BOUNDS: dict[str, tuple[float, float]] = {
    "calories_kcal": (20.0, 1500.0),
    "protein_g": (0.0, 120.0),
    "fat_g": (0.0, 100.0),
    "carbohydrates_g": (0.0, 200.0),
    "fiber_g": (0.0, 50.0),
}


class NutritionValidator:
    def check(self, nutrition: NutritionPerServing) -> NutritionValidationResult:
        for field_name, (low, high) in BOUNDS.items():
            value = float(getattr(nutrition, field_name))
            if value < low or value > high:
                raise NutritionOutOfRangeError(
                    message=f"{field_name} out of range: {value}",
                    field=field_name,
                    value=value,
                )
        return NutritionValidationResult(passed=True, errors=())
