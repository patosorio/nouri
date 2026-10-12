"""Pydantic V2 models for agent I/O — docs/7_TECH_SPEC.md §5."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from db.models import (
    CookingType,
    DietType,
    JuiceTime,
    PreparationType,
    PrimaryProtein,
    RecipeUsagePolicy,
    UserTier,
)
from pydantic import BaseModel, Field

# AI output slot vocabulary — docs/7_TECH_SPEC.md §5.4 (aligned with ERD PlanSlot).
PlanSlotAI = Literal[
    "breakfast",
    "lunch",
    "dinner",
    "snack",
    "juice",
    "smoothie",
    "extra_morning",
    "extra_afternoon",
    "extra_evening",
]

SSEEventType = Literal["text_delta", "tool_call", "done", "error", "plan_proposal"]


class AgentContext(BaseModel):
    """Per-turn context injected into ChatAgent (docs/7_TECH_SPEC.md §5.3)."""

    current_plan_id: UUID | None = None
    active_recipe_id: UUID | None = None
    diet_type: DietType | None = None
    cooking_type: CookingType | None = None
    calorie_target: int | None = None
    tier: UserTier | None = None
    exclusions: list[str] = Field(default_factory=list)
    trace_id: str | None = None


class PlanProposal(BaseModel):
    """Params for the generate form — chat does not enqueue generation."""

    num_days: int = Field(ge=1, le=14)
    diet_type: DietType
    cooking_type: CookingType | None = None
    calorie_target: int | None = None
    recipe_usage_policy: RecipeUsagePolicy | None = None
    include_juicing: bool = False
    notes: str | None = None


class SSEEvent(BaseModel):
    type: SSEEventType
    text: str | None = None
    conversation_id: UUID | None = None
    tool_name: str | None = None
    tool_use_id: str | None = None
    error: str | None = None
    code: str | None = None
    plan_proposal: PlanProposal | None = None


class PlanGenerationJob(BaseModel):
    """Payload for PlanGeneratorAgent.generate() (worker job)."""

    user_id: UUID
    plan_id: UUID
    duration_days: int = Field(default=7, ge=1, le=14)
    diet_type: DietType
    cooking_type: CookingType | None = None
    calorie_target: int | None = None
    protein_g_target: Decimal | None = None
    carbs_g_target: Decimal | None = None
    fat_g_target: Decimal | None = None
    fiber_g_target: Decimal | None = None
    sourcing_policy: RecipeUsagePolicy = RecipeUsagePolicy.BALANCED
    include_juicing: bool = False
    notes: str | None = None
    trace_id: str | None = None


class GeneratedPlanItemAI(BaseModel):
    """One slot in a generated plan day — docs/7_TECH_SPEC.md §5.4.

    Macro / prep / protein snapshot fields are filled by SlotAssigner after
    the LLM call. They are stripped from the output_plan tool schema so the
    model cannot invent them.
    """

    slot_type: PlanSlotAI
    recipe_id: UUID | Literal["generate_new"]
    recipe_title: str
    servings: int = 1
    juice_time: JuiceTime | None = None
    juice_size_ml: int | None = None
    nutrition_unknown: bool = False
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    prep_method: PreparationType | None = None
    primary_protein: str | None = None


class GeneratedPlanDayAI(BaseModel):
    day_number: int = Field(ge=1, le=31)
    items: list[GeneratedPlanItemAI] = Field(default_factory=list)


class RecipeIngredientAI(BaseModel):
    """Ingredient line in AI recipe output — docs/7_TECH_SPEC.md §5.5."""

    ingredient_name: str
    quantity: Decimal
    unit: str
    prep_type: PreparationType | None = None
    notes: str | None = None
    ingredient_id: UUID | None = None


class RecipeStepAI(BaseModel):
    step_number: int
    instruction: str
    duration_minutes: int | None = None
    tips: str | None = None


class NutritionPerServingAI(BaseModel):
    calories_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float
    fiber_g: float = 0.0
    sugar_g: float | None = None
    sodium_mg: float | None = None


class GeneratedRecipeAI(BaseModel):
    """Recipe stub produced alongside plan generation — docs/7_TECH_SPEC.md §5.4."""

    title: str
    slot_type: str
    diet_type: DietType
    prep_type: PreparationType
    servings: int = 1
    ingredients: list[RecipeIngredientAI] = Field(default_factory=list)
    steps: list[RecipeStepAI] = Field(default_factory=list)
    assigned_id: UUID | None = None
    # Required for SlotAssigner — truncated max_tokens outputs often omit this and
    # produce an empty nutrition pool (plan_assignment_infeasible).
    nutrition_per_serving: NutritionPerServingAI
    primary_protein: PrimaryProtein | None = None


class GeneratedPlanData(BaseModel):
    """Structured plan generation output — docs/7_TECH_SPEC.md §5.4."""

    days: list[GeneratedPlanDayAI]
    generated_recipes: list[GeneratedRecipeAI] = Field(default_factory=list)
    review_notes: str | None = None


class RecipeDraft(BaseModel):
    """AI recipe draft — docs/7_TECH_SPEC.md §5.5 / §5.6."""

    title: str
    description: str | None = None
    servings: int = 1
    prep_time_minutes: int | None = None
    total_time_minutes: int | None = None
    diet_type: DietType
    prep_type: PreparationType
    is_juicing: bool = False
    ingredients: list[RecipeIngredientAI] = Field(default_factory=list)
    steps: list[RecipeStepAI] = Field(default_factory=list)
    nutrition_per_serving: NutritionPerServingAI
    nutrition_flagged: bool = False
    unresolved_ingredient_names: list[str] = Field(default_factory=list)


class RecipeGenerationRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    diet_type: DietType | None = None
    prep_type: PreparationType | None = None
    is_juicing: bool = False
    recipe_id: UUID | None = None


class RepairInstructionItem(BaseModel):
    checker: str
    guidance: str


class RepairInstructions(BaseModel):
    """Serializable repair hints for plan re-generation prompts."""

    instructions: list[RepairInstructionItem] = Field(default_factory=list)

    @classmethod
    def from_validation(
        cls, repair: Any
    ) -> RepairInstructions:
        """Convert validation.types.RepairInstructions dataclass → Pydantic."""
        items = getattr(repair, "instructions", ()) or ()
        return cls(
            instructions=[
                RepairInstructionItem(checker=i.checker, guidance=i.guidance)
                for i in items
            ]
        )


# ---------------------------------------------------------------------------
# Chat tool input schemas — docs/2_SAD.md §6.4 (derived via model_json_schema)
# ---------------------------------------------------------------------------


class TriggerPlanGenerationInput(BaseModel):
    duration_days: int = Field(default=7, ge=1, le=14)
    diet_type: DietType | None = None
    cooking_type: CookingType | None = None
    calorie_target: int | None = None
    sourcing_policy: RecipeUsagePolicy | None = None
    include_juicing: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class GetPlanInput(BaseModel):
    plan_id: UUID


class SwapMealInput(BaseModel):
    plan_id: UUID
    item_id: UUID
    new_recipe_id: UUID


class GenerateRecipeInput(BaseModel):
    title: str | None = None
    description: str | None = None
    diet_type: DietType | None = None
    prep_type: PreparationType | None = None
    is_juicing: bool = False


class GetRecipeInput(BaseModel):
    recipe_id: UUID


class SearchRecipesInput(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=30)


class SaveRecipeInput(BaseModel):
    """Draft fields the model proposes; persisted via RecipeService after mapping."""

    draft: dict[str, Any]


class ImportRecipeInput(BaseModel):
    text: str | None = None
    file_url: str | None = None
    source_hint: str | None = None


class ExpandRecipeInput(BaseModel):
    recipe_id: UUID
    instruction: str


class GetNutritionalProfileInput(BaseModel):
    recipe_id: UUID


class GetPlanExplanationInput(BaseModel):
    plan_id: UUID


class ProposeProfileUpdateInput(BaseModel):
    updates: dict[str, Any]


class UpdatePantryInput(BaseModel):
    action: Literal["add", "remove"]
    ingredient_id: UUID | None = None
    item_id: UUID | None = None


class GetShoppingListInput(BaseModel):
    plan_id: UUID


class GetUserProfileInput(BaseModel):
    """No fields — user_id injected by AgentToolExecutor."""

