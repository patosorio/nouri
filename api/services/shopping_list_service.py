from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Ingredient,
    MealPlan,
    PantryItem,
    PlanDay,
    PlanItem,
    RecipeIngredient,
    ShoppingListItem,
    UserTier,
)
from exceptions import NotFoundError, OwnershipError
from services._helpers import get_profile_or_404


class ShoppingListService:
    async def generate(
        self, plan_id: UUID, user_id: UUID, db: AsyncSession
    ) -> list[ShoppingListItem]:
        profile = await get_profile_or_404(user_id, db)
        plan = await db.get(MealPlan, plan_id)
        if plan is None:
            raise NotFoundError("Meal plan not found")
        if plan.user_id != user_id:
            raise OwnershipError("Meal plan not found")

        # Clear previous list for this plan
        await db.execute(
            delete(ShoppingListItem).where(ShoppingListItem.plan_id == plan_id)
        )
        await db.flush()

        days = await db.execute(select(PlanDay).where(PlanDay.plan_id == plan_id))
        day_ids = [d.id for d in days.scalars().all()]
        if not day_ids:
            return []

        items_result = await db.execute(
            select(PlanItem).where(PlanItem.plan_day_id.in_(day_ids))
        )
        plan_items = list(items_result.scalars().all())
        recipe_ids = [i.recipe_id for i in plan_items if i.recipe_id is not None]
        if not recipe_ids:
            return []

        ri_result = await db.execute(
            select(RecipeIngredient).where(RecipeIngredient.recipe_id.in_(recipe_ids))
        )
        recipe_ingredients = list(ri_result.scalars().all())

        # Aggregate by (ingredient_id, unit) — unit conversion deferred (see missing.txt)
        totals: dict[tuple[UUID, str], Decimal] = defaultdict(lambda: Decimal("0"))
        for ri in recipe_ingredients:
            key = (ri.ingredient_id, ri.unit)
            totals[key] += Decimal(str(ri.amount))

        pantry_by_ingredient: dict[UUID, list[PantryItem]] = defaultdict(list)
        if profile.tier == UserTier.PRO:
            pantry_result = await db.execute(
                select(PantryItem).where(PantryItem.user_id == user_id)
            )
            for p in pantry_result.scalars().all():
                if p.ingredient_id is not None:
                    pantry_by_ingredient[p.ingredient_id].append(p)

        created: list[ShoppingListItem] = []
        for (ingredient_id, unit), quantity in sorted(
            totals.items(), key=lambda x: (str(x[0][0]), x[0][1])
        ):
            remaining = quantity
            pantry_rows = pantry_by_ingredient.get(ingredient_id, [])
            for pantry in pantry_rows:
                if pantry.unit != unit or pantry.quantity is None:
                    continue
                deduct = min(remaining, Decimal(str(pantry.quantity)))
                remaining -= deduct
                if remaining <= 0:
                    break

            if remaining <= 0:
                continue

            ingredient = await db.get(Ingredient, ingredient_id)
            name = ingredient.name if ingredient is not None else "Unknown"
            row = ShoppingListItem(
                plan_id=plan_id,
                ingredient_id=ingredient_id,
                ingredient_name_display=name,
                quantity_total=remaining,
                unit=unit,
                category=None,
                is_checked=False,
            )
            db.add(row)
            created.append(row)

        await db.flush()
        for row in created:
            await db.refresh(row)

        return sorted(
            created,
            key=lambda r: ((r.category or "zzz"), r.ingredient_name_display.lower()),
        )

    async def check_item(
        self, item_id: UUID, user_id: UUID, db: AsyncSession
    ) -> ShoppingListItem:
        return await self._set_checked(item_id, user_id, True, db)

    async def uncheck_item(
        self, item_id: UUID, user_id: UUID, db: AsyncSession
    ) -> ShoppingListItem:
        return await self._set_checked(item_id, user_id, False, db)

    async def _set_checked(
        self,
        item_id: UUID,
        user_id: UUID,
        checked: bool,
        db: AsyncSession,
    ) -> ShoppingListItem:
        item = await db.get(ShoppingListItem, item_id)
        if item is None:
            raise NotFoundError("Shopping list item not found")

        plan = await db.get(MealPlan, item.plan_id)
        if plan is None or plan.user_id != user_id:
            raise OwnershipError("Shopping list item not found")

        item.is_checked = checked
        await db.flush()
        await db.refresh(item)
        return item
