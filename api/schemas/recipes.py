"""Recipe DTOs for the service layer (ERD field names)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from db.models import (
    CookingType,
    DietType,
    JuiceColor,
    JuiceSize,
    JuiceStyle,
    MealRole,
    PreparationType,
    PrimaryProtein,
    RecipeSource,
    RecipeType,
)
from pydantic import BaseModel, Field


class RecipeIngredientDraft(BaseModel):
    ingredient_name: str
    amount: Decimal
    unit: str
    ingredient_id: UUID | None = None
    notes: str | None = None
    is_optional: bool = False
    sort_order: int = 0


class RecipeStepDraft(BaseModel):
    step_number: int
    instruction: str
    duration_minutes: int | None = None
    tips: str | None = None


class RecipeNutritionDraft(BaseModel):
    calories_per_serving: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal
    sat_fat_g: Decimal | None = None
    sugar_g: Decimal | None = None
    nutritional_highlights: list[dict[str, object]] = Field(default_factory=list)


class RecipeDraft(BaseModel):
    # Pre-assigned by plan generation so plan_items can reference the row (worker).
    id: UUID | None = None
    name: str
    recipe_type: RecipeType = RecipeType.MEAL
    source: RecipeSource = RecipeSource.MANUAL
    servings: int = 1
    ingredients: list[RecipeIngredientDraft] = Field(default_factory=list)
    steps: list[RecipeStepDraft] = Field(default_factory=list)
    description: str | None = None
    prep_method: PreparationType | None = None
    cooking_type: CookingType = CookingType.COOKED_100
    color: str | None = None
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    diet_subtypes: list[str] = Field(default_factory=list)
    cuisine: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    diet_types: list[DietType] = Field(default_factory=list)
    nutrition: RecipeNutritionDraft | None = None
    # Meal-only
    primary_protein_source: PrimaryProtein = PrimaryProtein.NONE
    meal_roles: list[MealRole] = Field(default_factory=list)
    # Juice-only
    juice_style: JuiceStyle = JuiceStyle.JUICE
    juice_color: JuiceColor | None = None
    juice_default_size: JuiceSize = JuiceSize.OZ16_ML500


class RecipeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    recipe_type: RecipeType | None = None
    prep_method: PreparationType | None = None
    cooking_type: CookingType | None = None
    color: str | None = None
    servings: int | None = None
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    diet_subtypes: list[str] | None = None
    cuisine: list[str] | None = None
    tags: list[str] | None = None
    steps: list[RecipeStepDraft] | None = None
    ingredients: list[RecipeIngredientDraft] | None = None
    nutrition: RecipeNutritionDraft | None = None
    primary_protein_source: PrimaryProtein | None = None
    meal_roles: list[MealRole] | None = None


class RecipeFilters(BaseModel):
    q: str | None = None
    recipe_type: RecipeType | None = None
    prep_method: PreparationType | None = None
    cooking_type: CookingType | None = None
    diet_type: DietType | None = None
    offset: int = 0
    limit: int = Field(default=30, ge=1, le=100)


class RecipeIngredientSnapshot(BaseModel):
    name: str
    ingredient_id: UUID | None = None


class PinnedRecipeSnapshot(BaseModel):
    """Saved recipe pinned into a plan. Nutrition may be missing."""

    recipe_id: UUID
    title: str
    recipe_type: RecipeType
    ingredients: list[RecipeIngredientSnapshot] = Field(default_factory=list)
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    prep_method: PreparationType | None = None
    primary_protein: str | None = None
    slot_hint: str | None = None


class RecipePlanSnapshot(BaseModel):
    """Nutrition + prep view for slot assignment (saved recipes)."""

    recipe_id: UUID
    title: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    prep_method: PreparationType | None = None
    primary_protein: str | None = None
    slot_hint: str | None = None
    ingredients: list[RecipeIngredientSnapshot] = Field(default_factory=list)
