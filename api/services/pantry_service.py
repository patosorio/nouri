from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PantryItem, UserTier
from exceptions import NotFoundError, OwnershipError, TierGateError
from services._helpers import get_profile_or_404, resolve_or_create_ingredient


class PantryService:
    async def list_pantry(
        self,
        user_id: UUID,
        db: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[PantryItem], int]:
        await self._require_pro(user_id, db)
        base = select(PantryItem).where(PantryItem.user_id == user_id)
        count_result = await db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())
        result = await db.execute(
            base.order_by(PantryItem.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def add_item(
        self, user_id: UUID, ingredient_id: UUID, db: AsyncSession
    ) -> PantryItem:
        await self._require_pro(user_id, db)
        from db.models import Ingredient

        ingredient = await db.get(Ingredient, ingredient_id)
        if ingredient is None:
            raise NotFoundError("Ingredient not found")

        item = PantryItem(
            user_id=user_id,
            ingredient_id=ingredient.id,
            ingredient_name_raw=ingredient.name,
            quantity=None,
            unit=ingredient.default_unit,
        )
        db.add(item)
        await db.flush()
        await db.refresh(item)
        return item

    async def add_item_from_payload(
        self,
        user_id: UUID,
        *,
        ingredient_name_raw: str,
        quantity: Decimal | None,
        unit: str | None,
        notes: str | None,
        expires_at: date | None,
        db: AsyncSession,
    ) -> PantryItem:
        await self._require_pro(user_id, db)
        ingredient = await resolve_or_create_ingredient(
            ingredient_name_raw, db, default_unit=unit
        )
        item = PantryItem(
            user_id=user_id,
            ingredient_id=ingredient.id,
            ingredient_name_raw=ingredient_name_raw.strip(),
            quantity=quantity,
            unit=unit or ingredient.default_unit,
            notes=notes,
            expires_at=expires_at,
        )
        db.add(item)
        await db.flush()
        await db.refresh(item)
        return item

    async def update_item(
        self,
        item_id: UUID,
        user_id: UUID,
        db: AsyncSession,
        *,
        quantity: Decimal | None = None,
        unit: str | None = None,
        notes: str | None = None,
        expires_at: date | None = None,
        ingredient_name_raw: str | None = None,
    ) -> PantryItem:
        await self._require_pro(user_id, db)
        item = await self._get_owned_item(item_id, user_id, db)
        if quantity is not None:
            item.quantity = quantity
        if unit is not None:
            item.unit = unit
        if notes is not None:
            item.notes = notes
        if expires_at is not None:
            item.expires_at = expires_at
        if ingredient_name_raw is not None:
            item.ingredient_name_raw = ingredient_name_raw
        await db.flush()
        await db.refresh(item)
        return item

    async def remove_item(
        self, item_id: UUID, user_id: UUID, db: AsyncSession
    ) -> None:
        await self._require_pro(user_id, db)
        item = await self._get_owned_item(item_id, user_id, db)
        await db.delete(item)
        await db.flush()

    async def _require_pro(self, user_id: UUID, db: AsyncSession) -> None:
        profile = await get_profile_or_404(user_id, db)
        if profile.tier != UserTier.PRO:
            raise TierGateError("Pantry requires a pro plan")

    async def _get_owned_item(
        self, item_id: UUID, user_id: UUID, db: AsyncSession
    ) -> PantryItem:
        item = await db.get(PantryItem, item_id)
        if item is None:
            raise NotFoundError("Pantry item not found")
        if item.user_id != user_id:
            raise OwnershipError("Pantry item not found")
        return item
