"""Nutrition profile — docs/4_API_DESIGN.yaml GET /recipes/{recipe_id}/nutrition-profile."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RecipeNutrition
from dependencies import CurrentUser, get_current_user, get_db
from exceptions import NotFoundError
from routers.serializers import serialize_nutritional_profile
from services.recipe_service import RecipeService

router = APIRouter()


@router.get("/recipes/{recipe_id}/nutrition-profile")
async def get_recipe_nutrition_profile(
    recipe_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await RecipeService().get_recipe(recipe_id, current_user.id, db)
    nutrition = await db.get(RecipeNutrition, recipe_id)
    if nutrition is None:
        raise NotFoundError("Nutrition profile not found")
    include_pro = current_user.tier == "pro"
    return serialize_nutritional_profile(
        recipe_id, nutrition, include_pro_fields=include_pro
    )
