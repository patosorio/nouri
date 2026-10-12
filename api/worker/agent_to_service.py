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
    PrimaryProtein,
    RecipeSource,
    RecipeType,
)
from exceptions import PlanGenerationFailedError
from schemas import agent as agent_schemas
from schemas.plans import GeneratedPlanData, GeneratedPlanDay, GeneratedPlanItem
from schemas.recipes import (
    RecipeDraft,
    RecipeIngredientDraft,
    RecipeNutritionDraft,
    RecipeStepDraft,
)

_RAWISH_PREP = frozenset(
    {
        PreparationType.RAW,
        PreparationType.JUICED,
        PreparationType.BLENDED,
        PreparationType.DEHYDRATED,
        PreparationType.SPROUTED,
        PreparationType.FERMENTED,
    }
)


def map_generated_plan(
    agent_plan: agent_schemas.GeneratedPlanData,
    *,
    saved_ids: set[UUID],
) -> GeneratedPlanData:
    generated_by_id = {
        r.assigned_id: r
        for r in agent_plan.generated_recipes
        if r.assigned_id is not None
    }
    generated_ids = set(generated_by_id)
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
                    recipe_type=_recipe_type_for_item(item, generated_by_id),
                    prep_method=item.prep_method,
                    item_source=_item_source(recipe_id, generated_ids, saved_ids),
                    slot_order=index,
                    calories=decimal_or_none(item.calories),
                    protein_g=decimal_or_none(item.protein_g),
                    carbs_g=decimal_or_none(item.carbs_g),
                    fat_g=decimal_or_none(item.fat_g),
                    fiber_g=decimal_or_none(item.fiber_g),
                    juice_time=item.juice_time,
                    juice_size_ml=item.juice_size_ml,
                    nutrition_unknown=item.nutrition_unknown,
                )
            )
        days.append(
            GeneratedPlanDay(
                day_number=day.day_number,
                items=items,
                totals_incomplete=any(item.nutrition_unknown for item in items),
            )
        )

    return GeneratedPlanData(
        days=days,
        generated_recipes=recipe_drafts,
        review_notes=agent_plan.review_notes,
    )


def placed_recipe_ids(plan: GeneratedPlanData) -> set[UUID]:
    ids: set[UUID] = set()
    for day in plan.days:
        for item in day.items:
            if item.recipe_id is not None:
                ids.add(item.recipe_id)
    return ids


def filter_unplaced_generated(plan: GeneratedPlanData) -> GeneratedPlanData:
    placed = placed_recipe_ids(plan)
    return plan.model_copy(
        update={
            "generated_recipes": [
                draft
                for draft in plan.generated_recipes
                if draft.id is not None and draft.id in placed
            ]
        }
    )


def remap_reused_recipe_ids(
    plan: GeneratedPlanData, id_remap: dict[UUID, UUID]
) -> GeneratedPlanData:
    if not id_remap:
        return plan
    days: list[GeneratedPlanDay] = []
    for day in plan.days:
        items: list[GeneratedPlanItem] = []
        for item in day.items:
            if item.recipe_id is not None and item.recipe_id in id_remap:
                items.append(
                    item.model_copy(
                        update={
                            "recipe_id": id_remap[item.recipe_id],
                            "item_source": PlanItemSource.SAVED_RECIPE,
                        }
                    )
                )
            else:
                items.append(item)
        days.append(day.model_copy(update={"items": items}))
    reused = set(id_remap)
    return plan.model_copy(
        update={
            "days": days,
            "generated_recipes": [
                draft
                for draft in plan.generated_recipes
                if draft.id is None or draft.id not in reused
            ],
        }
    )


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

    nutrition = None
    if recipe.nutrition_per_serving is not None:
        n = recipe.nutrition_per_serving
        nutrition = RecipeNutritionDraft(
            calories_per_serving=Decimal(str(n.calories_kcal)),
            protein_g=Decimal(str(n.protein_g)),
            carbs_g=Decimal(str(n.carbohydrates_g)),
            fat_g=Decimal(str(n.fat_g)),
            fiber_g=Decimal(str(n.fiber_g)),
            sugar_g=Decimal(str(n.sugar_g)) if n.sugar_g is not None else None,
        )

    primary = recipe.primary_protein or PrimaryProtein.NONE

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
        nutrition=nutrition,
        primary_protein_source=primary,
    )


def _item_source(
    recipe_id: UUID | None,
    generated_ids: set[UUID],
    saved_ids: set[UUID],
) -> PlanItemSource:
    if recipe_id is None or recipe_id in generated_ids:
        return PlanItemSource.AI_GENERATED
    if recipe_id in saved_ids:
        return PlanItemSource.SAVED_RECIPE
    raise PlanGenerationFailedError(
        f"Recipe {recipe_id} is not a saved or generated recipe"
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


def _recipe_type_for_item(
    item: agent_schemas.GeneratedPlanItemAI,
    generated_by_id: dict[UUID, agent_schemas.GeneratedRecipeAI],
) -> RecipeType:
    """Generated dishes keep the recipe's type. Saved dishes fall back to the slot."""
    recipe_id = item.recipe_id if isinstance(item.recipe_id, UUID) else None
    if recipe_id is not None and recipe_id in generated_by_id:
        return _recipe_type_for_slot(generated_by_id[recipe_id].slot_type)
    return _recipe_type_for_slot(item.slot_type)


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
