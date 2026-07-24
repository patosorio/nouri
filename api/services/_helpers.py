"""Shared service helpers — ownership lookups and ingredient resolution."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Ingredient, Recipe, UserProfile
from exceptions import NotFoundError, OwnershipError


def normalise_ingredient_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


async def get_profile_or_404(user_id: UUID, db: AsyncSession) -> UserProfile:
    profile = await db.get(UserProfile, user_id)
    if profile is None:
        raise NotFoundError("User profile not found")
    return profile


async def get_owned_recipe(
    recipe_id: UUID, user_id: UUID, db: AsyncSession, *, include_deleted: bool = False
) -> Recipe:
    recipe = await db.get(Recipe, recipe_id)
    if recipe is None or (recipe.deleted_at is not None and not include_deleted):
        raise NotFoundError("Recipe not found")
    if recipe.user_id != user_id:
        raise OwnershipError("Recipe not found")
    return recipe


async def resolve_or_create_ingredient(
    name: str,
    db: AsyncSession,
    *,
    ingredient_id: UUID | None = None,
    default_unit: str | None = None,
) -> Ingredient:
    if ingredient_id is not None:
        existing = await db.get(Ingredient, ingredient_id)
        if existing is not None:
            return existing

    normalised = normalise_ingredient_name(name)
    result = await db.execute(
        select(Ingredient).where(Ingredient.name_normalised == normalised)
    )
    found = result.scalar_one_or_none()
    if found is not None:
        return found

    ingredient = Ingredient(
        name=name.strip(),
        name_normalised=normalised,
        default_unit=default_unit,
    )
    db.add(ingredient)
    await db.flush()
    return ingredient
