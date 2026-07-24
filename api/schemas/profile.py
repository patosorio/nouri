"""Profile request/response DTOs for the service layer (ERD field names)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from db.models import CookingType, DietType, RecipeUsagePolicy


class ProfileCreate(BaseModel):
    display_name: str | None = None
    diet_type: DietType = DietType.VEGAN
    diet_subtypes: list[str] = Field(default_factory=list)
    cuisine_prefs: list[str] = Field(default_factory=list)
    cooking_type: CookingType = CookingType.RAW_50_COOKED_50
    calorie_target: int | None = None
    protein_g_target: int | None = None
    carbs_g_target: int | None = None
    fat_g_target: int | None = None
    fiber_g_target: int | None = None
    recipe_usage_policy: RecipeUsagePolicy = RecipeUsagePolicy.BALANCED
    juicing_enabled: bool = False
    free_text_preferences: str | None = None
    timezone: str = "UTC"


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    diet_type: DietType | None = None
    diet_subtypes: list[str] | None = None
    cuisine_prefs: list[str] | None = None
    cooking_type: CookingType | None = None
    calorie_target: int | None = None
    protein_g_target: int | None = None
    carbs_g_target: int | None = None
    fat_g_target: int | None = None
    fiber_g_target: int | None = None
    recipe_usage_policy: RecipeUsagePolicy | None = None
    juicing_enabled: bool | None = None
    free_text_preferences: str | None = None
    timezone: str | None = None
