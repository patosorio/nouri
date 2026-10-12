"""Plan DTOs for the service layer (ERD field names)."""

from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
from uuid import UUID

from db.models import (
    CookingType,
    DietType,
    JuiceTime,
    PlanItemSource,
    PlanSlot,
    PlanStatus,
    PreparationType,
    RecipeType,
    RecipeUsagePolicy,
)
from pydantic import BaseModel, Field

from schemas.recipes import RecipeDraft


class PlanGenerationParams(BaseModel):
    duration_days: int = Field(default=7, ge=1, le=14)
    diet_type: DietType
    cooking_type: CookingType | None = None
    calorie_target: int | None = None
    sourcing_policy: RecipeUsagePolicy = RecipeUsagePolicy.BALANCED
    include_juicing: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)
    cloned_from_plan_id: UUID | None = None
    week_start_date: Date | None = None
    conversation_id: UUID | None = None


class GeneratedPlanItem(BaseModel):
    slot_type: PlanSlot
    recipe_title: str
    recipe_id: UUID | None = None
    servings: int = 1
    recipe_type: RecipeType = RecipeType.MEAL
    prep_method: PreparationType | None = None
    item_source: PlanItemSource = PlanItemSource.AI_GENERATED
    description: str | None = None
    color: str | None = None
    prep_minutes: int | None = None
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    fiber_g: Decimal | None = None
    slot_order: int = 0
    juice_time: JuiceTime | None = None
    juice_size_ml: int | None = None
    nutrition_unknown: bool = False


class GeneratedPlanDay(BaseModel):
    day_number: int = Field(ge=1, le=31)
    items: list[GeneratedPlanItem] = Field(default_factory=list)
    date: Date | None = None
    totals_incomplete: bool = False


class GeneratedPlanData(BaseModel):
    days: list[GeneratedPlanDay]
    generated_recipes: list[RecipeDraft] = Field(default_factory=list)
    title: str | None = None
    review_notes: str | None = None


class MealPlanSummary(BaseModel):
    id: UUID
    status: PlanStatus
    num_days: int
    title: str | None = None
    week_start_date: Date
    scheduled_date: Date | None = None
    created_at: object
