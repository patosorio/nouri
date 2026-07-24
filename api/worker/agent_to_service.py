"""Map AI agent plan/recipe shapes → service/ERD DTOs (Phase 7 translation boundary)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from db.models import (
    CookingType,
    MealRole,
    PlanItemSource,
    PlanSlot,
    PreparationType,
    RecipeSource,
    RecipeType,
)
from schemas import agent as agent_schemas
from schemas.plans import GeneratedPlanData, GeneratedPlanDay, GeneratedPlanItem
from schemas.recipes import RecipeDraft, RecipeIngredientDraft, RecipeStepDraft


def map_generated_plan(
    agent_plan: agent_schemas.GeneratedPlanData,
) -> GeneratedPlanData:
    generated_ids = {
        r.assigned_id for r in agent_plan.generated_recipes if r.assigned_id is not None
    }
    recipe_drafts = [
        map_generated_recipe(r) for r in agent_plan.generated_recipes
    ]

    days: list[GeneratedPlanDay] = []
    for day in agent_plan.days:
        items: list[GeneratedPlanItem] = []
        for index, item in enumerate(day.items):
            recipe_id = _coerce_recipe_id(item.recipe_id)
            items.append(
                GeneratedPlanItem(
                    slot_type=PlanSlot(item.slot_type),
                    recipe_title=item.recipe_title,
                    recipe_id=recipe_id,
                    servings=item.servings,
                    recipe_type=_recipe_type_for_slot(item.slot_type),
                    prep_method=None,
                    item_source=(
                        PlanItemSource.AI_GENERATED
                        if recipe_id is not None and recipe_id in generated_ids
                        else PlanItemSource.SAVED_RECIPE
                    ),
                    slot_order=index,
                )
            )
        days.append(GeneratedPlanDay(day_number=day.day_number, items=items))

    return GeneratedPlanData(days=days, generated_recipes=recipe_drafts)


def map_generated_recipe(
    recipe: agent_schemas.GeneratedRecipeAI,
) -> RecipeDraft:
    recipe_type = _recipe_type_for_slot(recipe.slot_type)
    prep = recipe.prep_type
    cooking = (
        CookingType.RAW_100 if prep in _RAWISH_PREP else CookingType.COOKED_100
    )
    meal_roles: list[MealRole] = []
    try:
        meal_roles = [MealRole(recipe.slot_type)]
    except ValueError:
        meal_roles = []

    return RecipeDraft(
        id=recipe.assigned_id,
        name=recipe.title,
        recipe_type=recipe_type,
        source=RecipeSource.AI_GENERATED,
        servings=recipe.servings,
        ingredients=[
            RecipeIngredientDraft(
                ingredient_name=ing.ingredient_name,
                amount=ing.quantity,
                unit=ing.unit,
                ingredient_id=ing.ingredient_id,
                notes=ing.notes,
                sort_order=i,
            )
            for i, ing in enumerate(recipe.ingredients)
        ],
        steps=[
            RecipeStepDraft(
                step_number=step.step_number,
                instruction=step.instruction,
                duration_minutes=step.duration_minutes,
                tips=step.tips,
            )
            for step in recipe.steps
        ],
        prep_method=prep,
        cooking_type=cooking,
        diet_types=[recipe.diet_type],
        meal_roles=meal_roles,
    )


def _coerce_recipe_id(value: UUID | str) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if value == "generate_new":
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _recipe_type_for_slot(slot_type: str) -> RecipeType:
    if slot_type == "juice":
        return RecipeType.JUICE
    if slot_type == "smoothie":
        return RecipeType.SMOOTHIE
    return RecipeType.MEAL


def decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
