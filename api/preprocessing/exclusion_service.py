"""ExclusionService — ingredient name → canonical ID (RISK-05 / Phase 10)."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from db.models import Ingredient, Recipe, RecipeIngredient
from services._helpers import normalise_ingredient_name
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from validation.text_match import contains


class ExclusionService:
    async def resolve_name(
        self, ingredient_name: str, db: AsyncSession
    ) -> UUID | None:
        """Look up ingredient by canonical name (case-insensitive).

        ERD `ingredients` has `name` / `name_normalised` only — no `aliases[]`
        column (docs/6_DATA_INTEGRITY.md RISK-05 mentions aliases; deferred until
        ERD is amended). Returns None when unresolved; callers store null
        ingredient_id and flag for review.
        """
        normalised = normalise_ingredient_name(ingredient_name)
        if not normalised:
            return None

        result = await db.execute(
            select(Ingredient.id).where(Ingredient.name_normalised == normalised)
        )
        found = result.scalar_one_or_none()
        return found

    async def matching_ingredient_ids(
        self,
        exclusions: Sequence[object],
        db: AsyncSession,
    ) -> list[UUID]:
        """Ingredient ids used by her recipes whose names contain an exclusion.

        ``resolve_name`` stays an exact lookup. This is the token-containment
        scan the planner uses to keep those rows out of SQL retrieval.
        """
        labels = [self._exclusion_label(row) for row in exclusions]
        labels = [label for label in labels if label]
        if not labels:
            return []

        user_id = self._exclusion_user_id(exclusions)
        if user_id is None:
            return []

        result = await db.execute(
            select(Ingredient.id, Ingredient.name)
            .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
            .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
            .where(Recipe.user_id == user_id, Recipe.deleted_at.is_(None))
            .distinct()
        )
        matched: list[UUID] = []
        for ingredient_id, name in result.all():
            if any(contains(name, label) for label in labels):
                matched.append(ingredient_id)
        matched.sort(key=lambda value: str(value))
        return matched

    @staticmethod
    def _exclusion_label(row: object) -> str:
        raw = getattr(row, "ingredient_name_raw", None)
        if isinstance(raw, str) and raw.strip():
            return raw
        name = getattr(row, "raw_name", None)
        if isinstance(name, str):
            return name
        return ""

    @staticmethod
    def _exclusion_user_id(exclusions: Sequence[object]) -> UUID | None:
        for row in exclusions:
            user_id = getattr(row, "user_id", None)
            if isinstance(user_id, UUID):
                return user_id
        return None
