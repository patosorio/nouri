"""ExclusionService — ingredient name → canonical ID (RISK-05 / Phase 10)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Ingredient
from services._helpers import normalise_ingredient_name


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
