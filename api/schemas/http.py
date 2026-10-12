"""HTTP request/response DTOs aligned with docs/4_API_DESIGN.yaml."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from db.models import (
    CookingType,
    DietType,
    PlanStatus,
    PreparationType,
    RecipeType,
    RecipeUsagePolicy,
)
from pydantic import BaseModel, Field

from schemas.profile import ProfileCreate, ProfileUpdate
from schemas.recipes import RecipeDraft, RecipeUpdate


class ExclusionPayload(BaseModel):
    ingredient_name_raw: str


class PlanGenerationRequest(BaseModel):
    """OpenAPI PlanGenerationParams (num_days / recipe_usage_policy)."""

    num_days: int = Field(default=7, ge=1, le=14)
    diet_type: DietType
    cooking_type: CookingType | None = None
    calorie_target: int | None = None
    recipe_usage_policy: RecipeUsagePolicy = RecipeUsagePolicy.BALANCED
    include_juicing: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    cloned_from_plan_id: UUID | None = None
    week_start_date: date | None = None
    conversation_id: UUID | None = None


class PlanStatusUpdate(BaseModel):
    status: PlanStatus


class SwapPayload(BaseModel):
    recipe_id: UUID | None = None
    reason: str | None = None


class RecipeSavePayload(BaseModel):
    draft: RecipeDraft


class RecipeExpandPayload(BaseModel):
    instruction: str = Field(max_length=1000)


class PantryItemPayload(BaseModel):
    ingredient_name_raw: str
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = None
    notes: str | None = None
    expires_at: date | None = None


class CalendarAssignPayload(BaseModel):
    plan_id: UUID


class ChatRequest(BaseModel):
    message: str = Field(max_length=4000)
    conversation_id: UUID | None = None
    context: dict[str, Any] | None = None


class OnboardingPayload(ProfileCreate):
    exclusion_names: list[str] = Field(default_factory=list)


# Re-exports for router convenience
__all__ = [
    "CalendarAssignPayload",
    "ChatRequest",
    "ExclusionPayload",
    "OnboardingPayload",
    "PantryItemPayload",
    "PlanGenerationRequest",
    "PlanStatusUpdate",
    "PreparationType",
    "ProfileUpdate",
    "RecipeExpandPayload",
    "RecipeSavePayload",
    "RecipeType",
    "RecipeUpdate",
    "SwapPayload",
]
