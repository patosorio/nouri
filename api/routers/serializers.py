"""Response serializers — ORM/domain → OpenAPI shapes (docs/4_API_DESIGN.yaml)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from db.models import (
    Conversation,
    JobQueue,
    MealPlan,
    Notification,
    PantryItem,
    PlanDay,
    PlanItem,
    Recipe,
    RecipeNutrition,
    ShoppingListItem,
    UserExclusion,
    UserProfile,
)


def _enum(value: Any) -> Any:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else value


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _num(value: Decimal | float | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def pagination_meta(total: int, offset: int, limit: int) -> dict[str, Any]:
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }


def serialize_profile(profile: UserProfile, *, email: str) -> dict[str, Any]:
    return {
        "id": str(profile.id),
        "email": email,
        "display_name": profile.display_name,
        "tier": _enum(profile.tier),
        "diet_type": _enum(profile.diet_type),
        "diet_subtypes": list(profile.diet_subtypes or []),
        "cooking_type": _enum(profile.cooking_type),
        "cuisine_prefs": list(profile.cuisine_prefs or []),
        "calorie_target": profile.calorie_target,
        "protein_g_target": profile.protein_g_target,
        "carbs_g_target": profile.carbs_g_target,
        "fat_g_target": profile.fat_g_target,
        "fiber_g_target": profile.fiber_g_target,
        "recipe_usage_policy": _enum(profile.recipe_usage_policy),
        "juicing_enabled": profile.juicing_enabled,
        "generation_credits_remaining": profile.generation_credits_remaining,
        "free_text_preferences": profile.free_text_preferences,
        "timezone": profile.timezone,
        "created_at": _dt(profile.created_at),
        "updated_at": _dt(profile.updated_at),
    }


def serialize_exclusion(row: UserExclusion) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "ingredient_id": str(row.ingredient_id) if row.ingredient_id else None,
        "ingredient_name_raw": row.ingredient_name_raw,
        "created_at": _dt(row.created_at),
    }


def serialize_generation(job: JobQueue | None) -> dict[str, Any] | None:
    if job is None:
        return None
    result = job.result if isinstance(job.result, dict) else {}
    progress = result.get("progress_pct")
    days_completed = result.get("days_completed")
    days_total = result.get("days_total")
    if job.status.value == "completed":
        progress = 100
    return {
        "job_id": str(job.id),
        "status": _enum(job.status),
        "progress_pct": int(progress) if isinstance(progress, (int, float)) else 0,
        "stage": result.get("stage") if isinstance(result.get("stage"), str) else None,
        "days_completed": (
            int(days_completed) if isinstance(days_completed, (int, float)) else 0
        ),
        "days_total": int(days_total) if isinstance(days_total, (int, float)) else 0,
        "error_message": job.error_message,
        "attempts": job.attempts,
    }


def serialize_plan_summary(
    plan: MealPlan, *, generation: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "title": plan.title,
        "status": _enum(plan.status),
        "num_days": plan.num_days,
        "week_start_date": _date(plan.week_start_date),
        "scheduled_date": _date(plan.scheduled_date),
        "created_at": _dt(plan.created_at),
        "generation": generation,
    }


def serialize_plan_item(item: PlanItem, *, day_number: int, plan_id: UUID) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "plan_id": str(plan_id),
        "day_number": day_number,
        "slot": _enum(item.slot),
        "recipe_id": str(item.recipe_id) if item.recipe_id else None,
        "name": item.name,
        "description": item.description,
        "recipe_type": _enum(item.recipe_type),
        "item_source": _enum(item.item_source),
        "prep_method": _enum(item.prep_method),
        "color": item.color,
        "prep_minutes": item.prep_minutes,
        "slot_order": item.slot_order,
        "juice_time": _enum(item.juice_time),
        "juice_size_ml": item.juice_size_ml,
        "nutrition_unknown": bool(item.nutrition_unknown),
        "calories": _num(item.calories),
        "protein_g": _num(item.protein_g),
        "carbs_g": _num(item.carbs_g),
        "fat_g": _num(item.fat_g),
        "fiber_g": _num(item.fiber_g),
    }


def serialize_plan_day(day: PlanDay, items: list[PlanItem], *, plan_id: UUID) -> dict[str, Any]:
    return {
        "id": str(day.id),
        "day_number": day.day_number,
        "date": _date(day.date),
        "calories_actual": _num(day.calories_actual),
        "protein_g_actual": _num(day.protein_g_actual),
        "carbs_g_actual": _num(day.carbs_g_actual),
        "fat_g_actual": _num(day.fat_g_actual),
        "fiber_g_actual": _num(day.fiber_g_actual),
        "calories_target": _num(day.calories_target),
        "protein_g_target": _num(day.protein_g_target),
        "carbs_g_target": _num(day.carbs_g_target),
        "fat_g_target": _num(day.fat_g_target),
        "fiber_g_target": _num(day.fiber_g_target),
        "totals_incomplete": bool(day.totals_incomplete),
        "items": [
            serialize_plan_item(i, day_number=day.day_number, plan_id=plan_id)
            for i in items
        ],
    }


def serialize_meal_plan(
    plan: MealPlan,
    days: list[tuple[PlanDay, list[PlanItem]]],
    *,
    generation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "user_id": str(plan.user_id),
        "title": plan.title,
        "status": _enum(plan.status),
        "num_days": plan.num_days,
        "week_start_date": _date(plan.week_start_date),
        "scheduled_date": _date(plan.scheduled_date),
        "recipe_usage_policy": _enum(plan.recipe_usage_policy),
        "generation_params": plan.generation_params or None,
        "nutrition_summary": None,
        "days": [
            serialize_plan_day(day, items, plan_id=plan.id) for day, items in days
        ],
        "cloned_from_plan_id": str(plan.cloned_from_plan_id)
        if plan.cloned_from_plan_id
        else None,
        "notes": plan.notes,
        "created_at": _dt(plan.created_at),
        "updated_at": _dt(plan.updated_at),
        "generation": generation,
    }


def serialize_job(job: JobQueue) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": _enum(job.status),
        "plan_id": str(job.plan_id) if job.plan_id else None,
        "payload": job.payload or {},
        "result": job.result,
        "error_message": job.error_message,
        "attempts": job.attempts,
        "claimed_at": _dt(job.claimed_at),
        "completed_at": _dt(job.completed_at),
        "created_at": _dt(job.created_at),
        "updated_at": _dt(job.updated_at),
    }


def serialize_recipe_list_item(recipe: Recipe) -> dict[str, Any]:
    return {
        "id": str(recipe.id),
        "name": recipe.name,
        "description": recipe.description,
        "recipe_type": _enum(recipe.recipe_type),
        "cooking_type": _enum(recipe.cooking_type),
        "prep_method": _enum(recipe.prep_method),
        "color": recipe.color,
        "servings": recipe.servings,
        "prep_minutes": recipe.prep_minutes,
        "source": _enum(recipe.source),
        "cuisine": list(recipe.cuisine or []),
        "tags": list(recipe.tags or []),
        "created_at": _dt(recipe.created_at),
    }


def serialize_recipe(
    recipe: Recipe,
    *,
    ingredients: list[dict[str, Any]] | None = None,
    nutrition: dict[str, Any] | None = None,
    diet_types: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(recipe.id),
        "user_id": str(recipe.user_id) if recipe.user_id else None,
        "name": recipe.name,
        "description": recipe.description,
        "servings": recipe.servings,
        "prep_minutes": recipe.prep_minutes,
        "cook_minutes": recipe.cook_minutes,
        "recipe_type": _enum(recipe.recipe_type),
        "diet_types": diet_types or [],
        "diet_subtypes": list(recipe.diet_subtypes or []),
        "cooking_type": _enum(recipe.cooking_type),
        "cuisine": list(recipe.cuisine or []),
        "tags": list(recipe.tags or []),
        "prep_method": _enum(recipe.prep_method),
        "color": recipe.color,
        "source": _enum(recipe.source),
        "steps": recipe.steps or [],
        "ingredients": ingredients or [],
        "nutrition": nutrition,
        "created_at": _dt(recipe.created_at),
        "updated_at": _dt(recipe.updated_at),
    }


def serialize_nutrition(
    nutrition: RecipeNutrition, *, include_pro_fields: bool
) -> dict[str, Any]:
    highlights = list(nutrition.nutritional_highlights or []) if include_pro_fields else []
    return {
        "calories_per_serving": _num(nutrition.calories_per_serving),
        "protein_g": _num(nutrition.protein_g),
        "carbs_g": _num(nutrition.carbs_g),
        "fat_g": _num(nutrition.fat_g),
        "fiber_g": _num(nutrition.fiber_g),
        "sat_fat_g": _num(nutrition.sat_fat_g),
        "sugar_g": _num(nutrition.sugar_g),
        "nutritional_highlights": highlights,
        "food_advisor_notes": None,
    }


def serialize_nutritional_profile(
    recipe_id: UUID,
    nutrition: RecipeNutrition,
    *,
    include_pro_fields: bool,
) -> dict[str, Any]:
    return {
        "recipe_id": str(recipe_id),
        "per_serving": serialize_nutrition(
            nutrition, include_pro_fields=include_pro_fields
        ),
        "estimated_at": _dt(nutrition.estimated_at),
        "disclaimer": (
            "Nutritional values are AI-estimated from ingredient knowledge and are "
            "provided as general guidance only — not a substitute for clinical "
            "nutrition advice."
        ),
    }


def serialize_shopping_item(item: ShoppingListItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "ingredient_id": str(item.ingredient_id) if item.ingredient_id else None,
        "ingredient_name_display": item.ingredient_name_display,
        "quantity_total": _num(item.quantity_total),
        "unit": item.unit,
        "category": item.category,
        "is_checked": item.is_checked,
    }


def serialize_pantry_item(item: PantryItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "user_id": str(item.user_id),
        "ingredient_id": str(item.ingredient_id) if item.ingredient_id else None,
        "ingredient_name_raw": item.ingredient_name_raw,
        "quantity": _num(item.quantity),
        "unit": item.unit,
        "notes": item.notes,
        "expires_at": _date(item.expires_at),
        "created_at": _dt(item.created_at),
        "updated_at": _dt(item.updated_at),
    }


def serialize_notification(row: Notification) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "type": _enum(row.type),
        "title": row.title,
        "body": row.body,
        "data": row.data or {},
        "is_read": row.is_read,
        "created_at": _dt(row.created_at),
    }


def serialize_conversation_summary(
    conversation: Conversation, *, message_count: int
) -> dict[str, Any]:
    return {
        "id": str(conversation.id),
        "plan_id": str(conversation.plan_id) if conversation.plan_id else None,
        "message_count": message_count,
        "model_version": conversation.model_version,
        "created_at": _dt(conversation.created_at),
        "updated_at": _dt(conversation.updated_at),
    }


def serialize_conversation(
    conversation: Conversation, messages: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "id": str(conversation.id),
        "plan_id": str(conversation.plan_id) if conversation.plan_id else None,
        "messages": messages,
        "model_version": conversation.model_version,
        "created_at": _dt(conversation.created_at),
        "updated_at": _dt(conversation.updated_at),
    }
