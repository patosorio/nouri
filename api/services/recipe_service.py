from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from db.models import (
    Ingredient,
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
from exceptions import NotFoundError, PlanGenerationFailedError
from schemas.common import PaginatedResult
from schemas.recipes import (
    PinnedRecipeSnapshot,
    RecipeDraft,
    RecipeFilters,
    RecipeIngredientSnapshot,
    RecipePlanSnapshot,
    RecipeUpdate,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services._helpers import (
    get_owned_recipe,
    get_profile_or_404,
    resolve_or_create_ingredient,
)
from services.recipe_dedup import should_reuse_existing

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class SaveGeneratedBatchResult:
    recipes: list[Recipe]
    id_remap: dict[UUID, UUID] = field(default_factory=dict)
    inserted: list[Recipe] = field(default_factory=list)


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
        self,
        user_id: UUID,
        drafts: list[RecipeDraft],
        db: AsyncSession,
        *,
        placed_ids: set[UUID] | None = None,
    ) -> SaveGeneratedBatchResult:
        await get_profile_or_404(user_id, db)
        library = await self._load_library_for_dedup(user_id, db)
        recipes: list[Recipe] = []
        inserted: list[Recipe] = []
        id_remap: dict[UUID, UUID] = {}
        for draft in drafts:
            if (
                placed_ids is not None
                and draft.id is not None
                and draft.id not in placed_ids
            ):
                continue
            existing = self._match_existing(draft, library)
            if existing is not None:
                if draft.id is not None and draft.id != existing.id:
                    id_remap[draft.id] = existing.id
                logger.info(
                    "generated_recipe_reused",
                    requested_id=str(draft.id) if draft.id else None,
                    existing_id=str(existing.id),
                    name=existing.name,
                )
                recipes.append(existing)
                continue
            recipe = await self._persist_draft(user_id, draft, db)
            recipes.append(recipe)
            inserted.append(recipe)
            library.append(
                (
                    recipe,
                    {ing.ingredient_name for ing in draft.ingredients},
                )
            )
        return SaveGeneratedBatchResult(
            recipes=recipes, id_remap=id_remap, inserted=inserted
        )

    async def _load_library_for_dedup(
        self, user_id: UUID, db: AsyncSession
    ) -> list[tuple[Recipe, set[str]]]:
        result = await db.execute(
            select(Recipe)
            .where(Recipe.user_id == user_id, Recipe.deleted_at.is_(None))
            .order_by(Recipe.created_at.asc())
        )
        recipes = list(result.scalars().all())
        library: list[tuple[Recipe, set[str]]] = []
        for recipe in recipes:
            ing_result = await db.execute(
                select(Ingredient.name)
                .join(
                    RecipeIngredient,
                    RecipeIngredient.ingredient_id == Ingredient.id,
                )
                .where(RecipeIngredient.recipe_id == recipe.id)
            )
            names = {n for n in ing_result.scalars().all() if n}
            library.append((recipe, names))
        return library

    @staticmethod
    def _match_existing(
        draft: RecipeDraft, library: list[tuple[Recipe, set[str]]]
    ) -> Recipe | None:
        draft_names = {ing.ingredient_name for ing in draft.ingredients}
        for recipe, names in library:
            if should_reuse_existing(
                draft_name=draft.name,
                draft_ingredients=draft_names,
                existing_name=recipe.name,
                existing_ingredients=names,
            ):
                return recipe
        return None

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

    async def load_plan_snapshots(
        self,
        user_id: UUID,
        recipe_ids: list[UUID],
        db: AsyncSession,
    ) -> dict[UUID, RecipePlanSnapshot]:
        """Load recipes that have nutrition — ineligible (no row) are omitted."""
        if not recipe_ids:
            return {}
        unique_ids = list(dict.fromkeys(recipe_ids))
        recipes_result = await db.execute(
            select(Recipe).where(
                Recipe.id.in_(unique_ids),
                Recipe.user_id == user_id,
                Recipe.deleted_at.is_(None),
            )
        )
        recipes = list(recipes_result.scalars().all())
        snapshots: dict[UUID, RecipePlanSnapshot] = {}
        for recipe in recipes:
            nutrition = await db.get(RecipeNutrition, recipe.id)
            if nutrition is None:
                continue
            meal = await db.get(RecipeMealDetails, recipe.id)
            primary = None
            slot_hint = None
            if meal is not None:
                primary = meal.primary_protein_source.value
                if meal.meal_roles:
                    slot_hint = meal.meal_roles[0].value
            ing_result = await db.execute(
                select(RecipeIngredient, Ingredient)
                .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
                .where(RecipeIngredient.recipe_id == recipe.id)
                .order_by(RecipeIngredient.sort_order.asc())
            )
            ingredients = [
                RecipeIngredientSnapshot(name=ing.name, ingredient_id=ing.id)
                for _row, ing in ing_result.all()
            ]
            snapshots[recipe.id] = RecipePlanSnapshot(
                recipe_id=recipe.id,
                title=recipe.name,
                calories=float(nutrition.calories_per_serving),
                protein_g=float(nutrition.protein_g),
                carbs_g=float(nutrition.carbs_g),
                fat_g=float(nutrition.fat_g),
                fiber_g=float(nutrition.fiber_g),
                prep_method=recipe.prep_method,
                primary_protein=primary,
                slot_hint=slot_hint,
                ingredients=ingredients,
            )
        return snapshots

    async def load_pinned_recipes(
        self,
        user_id: UUID,
        ids: list[UUID],
        db: AsyncSession,
        *,
        names: Mapping[UUID, str] | None = None,
    ) -> dict[UUID, PinnedRecipeSnapshot]:
        """Owned, non-deleted pins. Nutrition may be missing.

        A missing or foreign id raises. ``names`` supplies the label for that
        error when the row is not visible to this user.
        """
        if not ids:
            return {}
        unique_ids = list(dict.fromkeys(ids))
        recipes_result = await db.execute(
            select(Recipe).where(
                Recipe.id.in_(unique_ids),
                Recipe.user_id == user_id,
                Recipe.deleted_at.is_(None),
            )
        )
        recipes = {recipe.id: recipe for recipe in recipes_result.scalars().all()}
        labels = names or {}
        missing = [rid for rid in unique_ids if rid not in recipes]
        if missing:
            label = labels.get(missing[0], str(missing[0]))
            raise PlanGenerationFailedError(f"Pinned recipe not found: {label}")

        snapshots: dict[UUID, PinnedRecipeSnapshot] = {}
        for recipe_id in unique_ids:
            recipe = recipes[recipe_id]
            nutrition = await db.get(RecipeNutrition, recipe.id)
            meal = await db.get(RecipeMealDetails, recipe.id)
            primary = None
            slot_hint = None
            if meal is not None:
                primary = meal.primary_protein_source.value
                if meal.meal_roles:
                    slot_hint = meal.meal_roles[0].value
            ing_result = await db.execute(
                select(RecipeIngredient, Ingredient)
                .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
                .where(RecipeIngredient.recipe_id == recipe.id)
                .order_by(RecipeIngredient.sort_order.asc())
            )
            ingredients = [
                RecipeIngredientSnapshot(name=ing.name, ingredient_id=ing.id)
                for _row, ing in ing_result.all()
            ]
            calories = protein_g = carbs_g = fat_g = fiber_g = None
            if nutrition is not None:
                calories = float(nutrition.calories_per_serving)
                protein_g = float(nutrition.protein_g)
                carbs_g = float(nutrition.carbs_g)
                fat_g = float(nutrition.fat_g)
                fiber_g = float(nutrition.fiber_g)
            snapshots[recipe.id] = PinnedRecipeSnapshot(
                recipe_id=recipe.id,
                title=recipe.name,
                recipe_type=recipe.recipe_type,
                ingredients=ingredients,
                calories=calories,
                protein_g=protein_g,
                carbs_g=carbs_g,
                fat_g=fat_g,
                fiber_g=fiber_g,
                prep_method=recipe.prep_method,
                primary_protein=primary,
                slot_hint=slot_hint,
            )
        return snapshots

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
