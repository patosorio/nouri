from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Recipe,
    RecipeDietCompatibility,
    RecipeImportLog,
    RecipeIngredient,
    RecipeJuiceDetails,
    RecipeMealDetails,
    RecipeNutrition,
    RecipeSource,
    RecipeType,
)
from exceptions import NotFoundError
from schemas.common import PaginatedResult
from schemas.recipes import RecipeDraft, RecipeFilters, RecipeUpdate
from services._helpers import (
    get_owned_recipe,
    get_profile_or_404,
    resolve_or_create_ingredient,
)


class RecipeService:
    async def get_recipe(
        self, recipe_id: UUID, user_id: UUID, db: AsyncSession
    ) -> Recipe:
        return await get_owned_recipe(recipe_id, user_id, db)

    async def list_recipes(
        self, user_id: UUID, filters: RecipeFilters, db: AsyncSession
    ) -> PaginatedResult[Recipe]:
        await get_profile_or_404(user_id, db)
        base = select(Recipe).where(
            Recipe.user_id == user_id,
            Recipe.deleted_at.is_(None),
        )
        if filters.recipe_type is not None:
            base = base.where(Recipe.recipe_type == filters.recipe_type)
        if filters.prep_method is not None:
            base = base.where(Recipe.prep_method == filters.prep_method)
        if filters.cooking_type is not None:
            base = base.where(Recipe.cooking_type == filters.cooking_type)
        if filters.q:
            pattern = f"%{filters.q.strip()}%"
            base = base.where(
                or_(Recipe.name.ilike(pattern), Recipe.description.ilike(pattern))
            )

        count_result = await db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())

        result = await db.execute(
            base.order_by(Recipe.created_at.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        )
        rows = list(result.scalars().all())
        return PaginatedResult(
            data=rows,
            total=total,
            offset=filters.offset,
            limit=filters.limit,
        )

    async def save_recipe(
        self, user_id: UUID, draft: RecipeDraft, db: AsyncSession
    ) -> Recipe:
        await get_profile_or_404(user_id, db)
        return await self._persist_draft(user_id, draft, db)

    async def save_generated_batch(
        self, user_id: UUID, drafts: list[RecipeDraft], db: AsyncSession
    ) -> list[Recipe]:
        await get_profile_or_404(user_id, db)
        saved: list[Recipe] = []
        for draft in drafts:
            saved.append(await self._persist_draft(user_id, draft, db))
        return saved

    async def update_recipe(
        self,
        recipe_id: UUID,
        user_id: UUID,
        data: RecipeUpdate,
        db: AsyncSession,
    ) -> Recipe:
        recipe = await get_owned_recipe(recipe_id, user_id, db)
        updates = data.model_dump(
            exclude_unset=True,
            exclude={"ingredients", "steps", "nutrition", "primary_protein_source", "meal_roles"},
        )
        for key, value in updates.items():
            setattr(recipe, key, value)

        if data.steps is not None:
            recipe.steps = [s.model_dump() for s in data.steps]

        if data.ingredients is not None:
            await self._replace_ingredients(recipe.id, data.ingredients, db)

        if data.nutrition is not None:
            await self._upsert_nutrition(recipe.id, data.nutrition, db)

        if data.primary_protein_source is not None or data.meal_roles is not None:
            await self._upsert_meal_details(
                recipe.id,
                primary_protein=data.primary_protein_source,
                meal_roles=data.meal_roles,
                db=db,
            )

        await db.flush()
        await db.refresh(recipe)
        return recipe

    async def upsert_nutrition(
        self, recipe_id: UUID, nutrition: Any, db: AsyncSession
    ) -> None:
        await self._upsert_nutrition(recipe_id, nutrition, db)
        await db.flush()

    async def delete_recipe(
        self, recipe_id: UUID, user_id: UUID, db: AsyncSession
    ) -> None:
        recipe = await get_owned_recipe(recipe_id, user_id, db)
        recipe.deleted_at = datetime.now(timezone.utc)
        await db.flush()

    async def log_import(
        self,
        user_id: UUID,
        source_hint: str,
        raw_input: str,
        parsed_output: dict[str, Any],
        db: AsyncSession,
    ) -> RecipeImportLog:
        await get_profile_or_404(user_id, db)
        raw_recipe_id = parsed_output.get("recipe_id")
        if raw_recipe_id is None:
            raise NotFoundError("parsed_output.recipe_id is required for import log")
        recipe_id = UUID(str(raw_recipe_id))
        await get_owned_recipe(recipe_id, user_id, db)

        method = RecipeSource.IMPORTED_TEXT
        if "image" in source_hint.lower() or "photo" in source_hint.lower():
            method = RecipeSource.IMPORTED_IMAGE

        log = RecipeImportLog(
            recipe_id=recipe_id,
            import_method=method,
            source_notes=source_hint,
            raw_input_text=raw_input,
            raw_ai_response=parsed_output,
        )
        db.add(log)
        await db.flush()
        await db.refresh(log)
        return log

    async def _persist_draft(
        self, user_id: UUID, draft: RecipeDraft, db: AsyncSession
    ) -> Recipe:
        fields: dict[str, Any] = {
            "user_id": user_id,
            "name": draft.name,
            "description": draft.description,
            "recipe_type": draft.recipe_type,
            "prep_method": draft.prep_method,
            "cooking_type": draft.cooking_type,
            "color": draft.color,
            "source": draft.source,
            "servings": draft.servings,
            "prep_minutes": draft.prep_minutes,
            "cook_minutes": draft.cook_minutes,
            "steps": [s.model_dump() for s in draft.steps],
            "diet_subtypes": list(draft.diet_subtypes),
            "cuisine": list(draft.cuisine),
            "tags": list(draft.tags),
        }
        if draft.id is not None:
            fields["id"] = draft.id
        recipe = Recipe(**fields)
        db.add(recipe)
        await db.flush()

        for diet in draft.diet_types:
            db.add(RecipeDietCompatibility(recipe_id=recipe.id, diet_type=diet))

        if draft.recipe_type == RecipeType.MEAL:
            db.add(
                RecipeMealDetails(
                    recipe_id=recipe.id,
                    primary_protein_source=draft.primary_protein_source,
                    meal_roles=list(draft.meal_roles),
                )
            )
        elif draft.recipe_type in (RecipeType.JUICE, RecipeType.SMOOTHIE):
            db.add(
                RecipeJuiceDetails(
                    recipe_id=recipe.id,
                    juice_style=draft.juice_style,
                    color=draft.juice_color,
                    default_size=draft.juice_default_size,
                )
            )

        await self._replace_ingredients(recipe.id, draft.ingredients, db)

        if draft.nutrition is not None:
            await self._upsert_nutrition(recipe.id, draft.nutrition, db)

        await db.flush()
        await db.refresh(recipe)
        return recipe

    async def _replace_ingredients(
        self,
        recipe_id: UUID,
        ingredients: list[Any],
        db: AsyncSession,
    ) -> None:
        existing = await db.execute(
            select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)
        )
        for row in existing.scalars().all():
            await db.delete(row)
        await db.flush()

        for draft_ing in ingredients:
            ingredient = await resolve_or_create_ingredient(
                draft_ing.ingredient_name,
                db,
                ingredient_id=draft_ing.ingredient_id,
                default_unit=draft_ing.unit,
            )
            db.add(
                RecipeIngredient(
                    recipe_id=recipe_id,
                    ingredient_id=ingredient.id,
                    amount=draft_ing.amount,
                    unit=draft_ing.unit,
                    notes=draft_ing.notes,
                    is_optional=draft_ing.is_optional,
                    sort_order=draft_ing.sort_order,
                )
            )

    async def _upsert_nutrition(
        self, recipe_id: UUID, nutrition: Any, db: AsyncSession
    ) -> None:
        row = await db.get(RecipeNutrition, recipe_id)
        if row is None:
            row = RecipeNutrition(recipe_id=recipe_id)
            db.add(row)
        row.calories_per_serving = nutrition.calories_per_serving
        row.protein_g = nutrition.protein_g
        row.carbs_g = nutrition.carbs_g
        row.fat_g = nutrition.fat_g
        row.fiber_g = nutrition.fiber_g
        row.sat_fat_g = nutrition.sat_fat_g
        row.sugar_g = nutrition.sugar_g
        row.nutritional_highlights = list(nutrition.nutritional_highlights)

    async def _upsert_meal_details(
        self,
        recipe_id: UUID,
        *,
        primary_protein: Any,
        meal_roles: Any,
        db: AsyncSession,
    ) -> None:
        row = await db.get(RecipeMealDetails, recipe_id)
        if row is None:
            from db.models import PrimaryProtein

            row = RecipeMealDetails(
                recipe_id=recipe_id,
                primary_protein_source=primary_protein or PrimaryProtein.NONE,
                meal_roles=list(meal_roles or []),
            )
            db.add(row)
            return
        if primary_protein is not None:
            row.primary_protein_source = primary_protein
        if meal_roles is not None:
            row.meal_roles = list(meal_roles)
