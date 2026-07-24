"""Background embedding helpers — docs/7_TECH_SPEC.md §9."""

from __future__ import annotations

from uuid import UUID

import structlog

from db.models import Recipe
from db.session import async_session_factory
from search.recipe_search_service import RecipeSearchService

logger = structlog.get_logger(__name__)


async def embed_recipe_by_id(recipe_id: UUID) -> None:
    async with async_session_factory() as session:
        try:
            recipe = await session.get(Recipe, recipe_id)
            if recipe is None or recipe.deleted_at is not None:
                return
            await RecipeSearchService().embed_recipe(recipe, session)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("recipe_embed_failed", recipe_id=str(recipe_id))
            raise


async def embed_recipes(recipe_ids: list[UUID]) -> None:
    for recipe_id in recipe_ids:
        try:
            await embed_recipe_by_id(recipe_id)
        except Exception:
            # Already logged; continue remaining recipes.
            continue
