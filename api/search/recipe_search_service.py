"""RecipeSearchService — Voyage AI embeddings + pgvector kNN (docs/7_TECH_SPEC.md §9)."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import voyageai
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import (
    Ingredient,
    Recipe,
    RecipeDietCompatibility,
    RecipeEmbedding,
    RecipeIngredient,
    RecipeNutrition,
    UserExclusion,
)
from schemas.common import PaginatedResult
from schemas.recipes import RecipeFilters
from validation.exclusion_checker import ExclusionChecker
from validation.types import ExclusionView, RecipeIngredientView, RecipeView

_EXACT_SEARCH_ROW_THRESHOLD = 1000
_CANDIDATE_LIMIT = 30


@dataclass(frozen=True, slots=True)
class MacroSummary:
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None


@dataclass(frozen=True, slots=True)
class RecipeCandidate:
    recipe_id: UUID
    title: str
    diet_type: str | None
    cooking_type: str
    macro_summary: MacroSummary
    similarity: float


class RecipeSearchService:
    def __init__(
        self,
        *,
        voyage_client: Any | None = None,
        exclusion_checker: ExclusionChecker | None = None,
    ) -> None:
        self._voyage = voyage_client
        self._exclusions = exclusion_checker or ExclusionChecker()

    def _client(self) -> Any:
        if self._voyage is None:
            self._voyage = voyageai.Client(api_key=settings.voyage_api_key)
        return self._voyage

    async def embed_texts(
        self, texts: list[str], *, input_type: str = "document"
    ) -> list[list[float]]:
        if not texts:
            return []

        def _call() -> list[list[float]]:
            result = self._client().embed(
                texts,
                model=settings.voyage_model,
                input_type=input_type,
            )
            return list(result.embeddings)

        return await asyncio.to_thread(_call)

    async def embed_recipe(self, recipe: Recipe, db: AsyncSession) -> list[float]:
        embedding_text = await self._build_embedding_text(recipe, db)
        content_hash = hashlib.md5(embedding_text.encode("utf-8")).hexdigest()
        vectors = await self.embed_texts([embedding_text], input_type="document")
        vector = vectors[0]

        existing = await db.get(RecipeEmbedding, recipe.id)
        if existing is None:
            db.add(
                RecipeEmbedding(
                    recipe_id=recipe.id,
                    embedding=vector,
                    model_version=settings.voyage_model,
                    content_hash=content_hash,
                )
            )
        else:
            existing.embedding = vector
            existing.model_version = settings.voyage_model
            existing.content_hash = content_hash
            existing.embedded_at = datetime.now(timezone.utc)

        await db.flush()
        return vector

    async def find_candidates(
        self,
        user_id: UUID,
        diet_type: str,
        days: int,
        db: AsyncSession,
    ) -> list[RecipeCandidate]:
        query_text = f"{diet_type} recipe for {days}-day plan"
        query_vectors = await self.embed_texts([query_text], input_type="query")
        query_vec = query_vectors[0]

        embed_count = await self._user_embedding_count(user_id, db)
        rows = await self._knn_rows(
            user_id=user_id,
            query_vec=query_vec,
            db=db,
            diet_type=diet_type,
            cooking_type=None,
            recipe_type=None,
            prep_method=None,
            limit=_CANDIDATE_LIMIT * 3,
            offset=0,
            exact=embed_count < _EXACT_SEARCH_ROW_THRESHOLD,
        )

        threshold = settings.recipe_similarity_threshold
        candidates: list[RecipeCandidate] = []
        recipe_views: list[tuple[RecipeCandidate, RecipeView]] = []

        for recipe, distance, diet_label, nutrition in rows:
            similarity = 1.0 - float(distance)
            if similarity < threshold:
                continue
            candidate = RecipeCandidate(
                recipe_id=recipe.id,
                title=recipe.name,
                diet_type=diet_label,
                cooking_type=recipe.cooking_type.value,
                macro_summary=self._macro_summary(nutrition),
                similarity=similarity,
            )
            view = await self._recipe_view(recipe.id, db)
            recipe_views.append((candidate, view))

        exclusion_views = await self._load_exclusions(user_id, db)
        kept_ids = {
            r.id
            for r in self._exclusions.filter_candidates(
                [v for _, v in recipe_views], exclusion_views
            )
        }
        for candidate, view in recipe_views:
            if view.id in kept_ids:
                candidates.append(candidate)
            if len(candidates) >= _CANDIDATE_LIMIT:
                break
        return candidates

    async def search(
        self,
        user_id: UUID,
        query: str,
        filters: RecipeFilters,
        db: AsyncSession,
    ) -> PaginatedResult[Recipe]:
        q = (query or filters.q or "").strip()
        if not q:
            # Structured filters only — no embedding call
            return await self._filtered_list(user_id, filters, db)

        query_vectors = await self.embed_texts([q], input_type="query")
        query_vec = query_vectors[0]
        embed_count = await self._user_embedding_count(user_id, db)

        fetch_limit = filters.offset + filters.limit
        rows = await self._knn_rows(
            user_id=user_id,
            query_vec=query_vec,
            db=db,
            diet_type=filters.diet_type.value if filters.diet_type else None,
            cooking_type=filters.cooking_type.value
            if filters.cooking_type
            else None,
            recipe_type=filters.recipe_type.value if filters.recipe_type else None,
            prep_method=filters.prep_method.value if filters.prep_method else None,
            limit=fetch_limit,
            offset=0,
            exact=embed_count < _EXACT_SEARCH_ROW_THRESHOLD,
        )

        recipes = [r for r, _, _, _ in rows]
        page = recipes[filters.offset : filters.offset + filters.limit]
        return PaginatedResult(
            data=page,
            total=len(recipes),
            offset=filters.offset,
            limit=filters.limit,
        )

    async def _build_embedding_text(
        self, recipe: Recipe, db: AsyncSession
    ) -> str:
        ing_result = await db.execute(
            select(Ingredient.name)
            .join(
                RecipeIngredient,
                RecipeIngredient.ingredient_id == Ingredient.id,
            )
            .where(RecipeIngredient.recipe_id == recipe.id)
            .order_by(RecipeIngredient.sort_order.asc())
        )
        ingredient_names = [n for n in ing_result.scalars().all() if n]
        ingredients_joined = ", ".join(ingredient_names) if ingredient_names else ""

        diet_result = await db.execute(
            select(RecipeDietCompatibility.diet_type).where(
                RecipeDietCompatibility.recipe_id == recipe.id
            )
        )
        diet_types = [d.value for d in diet_result.scalars().all()]
        diet_label = diet_types[0] if diet_types else "unspecified"

        prep = (
            recipe.prep_method.value
            if recipe.prep_method is not None
            else recipe.cooking_type.value
        )
        title = recipe.name
        description = recipe.description or ""
        return (
            f"{title}. {description}. Ingredients: {ingredients_joined}. "
            f"Diet: {diet_label}. Prep: {prep}."
        )

    async def _user_embedding_count(
        self, user_id: UUID, db: AsyncSession
    ) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(RecipeEmbedding)
            .join(Recipe, Recipe.id == RecipeEmbedding.recipe_id)
            .where(
                Recipe.user_id == user_id,
                Recipe.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def _knn_rows(
        self,
        *,
        user_id: UUID,
        query_vec: list[float],
        db: AsyncSession,
        diet_type: str | None,
        cooking_type: str | None,
        recipe_type: str | None,
        prep_method: str | None,
        limit: int,
        offset: int,
        exact: bool,
    ) -> list[tuple[Recipe, float, str | None, RecipeNutrition | None]]:
        if exact:
            await db.execute(text("SET LOCAL enable_indexscan = off"))

        vector_literal = "[" + ",".join(str(float(x)) for x in query_vec) + "]"

        sql = """
            SELECT
                r.id,
                (re.embedding <=> CAST(:query_vec AS vector)) AS distance
            FROM recipe_embeddings re
            JOIN recipes r ON r.id = re.recipe_id
            WHERE r.user_id = CAST(:user_id AS uuid)
              AND r.deleted_at IS NULL
              AND (
                    :diet_type::text IS NULL
                    OR EXISTS (
                        SELECT 1 FROM recipe_diet_compatibility rdc
                        WHERE rdc.recipe_id = r.id
                          AND rdc.diet_type::text = :diet_type
                    )
                  )
              AND (:cooking_type::text IS NULL OR r.cooking_type::text = :cooking_type)
              AND (:recipe_type::text IS NULL OR r.recipe_type::text = :recipe_type)
              AND (:prep_method::text IS NULL OR r.prep_method::text = :prep_method)
            ORDER BY distance ASC
            LIMIT :limit_n OFFSET :offset_n
        """
        result = await db.execute(
            text(sql),
            {
                "query_vec": vector_literal,
                "user_id": str(user_id),
                "diet_type": diet_type,
                "cooking_type": cooking_type,
                "recipe_type": recipe_type,
                "prep_method": prep_method,
                "limit_n": limit,
                "offset_n": offset,
            },
        )
        id_distances = [(row[0], float(row[1])) for row in result.all()]
        if not id_distances:
            return []

        recipe_ids = [rid for rid, _ in id_distances]
        recipes_result = await db.execute(
            select(Recipe).where(Recipe.id.in_(recipe_ids))
        )
        recipes_by_id = {r.id: r for r in recipes_result.scalars().all()}

        out: list[tuple[Recipe, float, str | None, RecipeNutrition | None]] = []
        for rid, distance in id_distances:
            recipe = recipes_by_id.get(rid)
            if recipe is None:
                continue
            diet_label = await self._primary_diet(rid, db)
            nutrition = await db.get(RecipeNutrition, rid)
            out.append((recipe, distance, diet_label, nutrition))
        return out

    async def _filtered_list(
        self, user_id: UUID, filters: RecipeFilters, db: AsyncSession
    ) -> PaginatedResult[Recipe]:
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
        if filters.diet_type is not None:
            base = base.where(
                Recipe.id.in_(
                    select(RecipeDietCompatibility.recipe_id).where(
                        RecipeDietCompatibility.diet_type == filters.diet_type
                    )
                )
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
        return PaginatedResult(
            data=list(result.scalars().all()),
            total=total,
            offset=filters.offset,
            limit=filters.limit,
        )

    async def _primary_diet(
        self, recipe_id: UUID, db: AsyncSession
    ) -> str | None:
        result = await db.execute(
            select(RecipeDietCompatibility.diet_type)
            .where(RecipeDietCompatibility.recipe_id == recipe_id)
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row.value if row is not None else None

    async def _recipe_view(
        self, recipe_id: UUID, db: AsyncSession
    ) -> RecipeView:
        result = await db.execute(
            select(RecipeIngredient, Ingredient)
            .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
            .where(RecipeIngredient.recipe_id == recipe_id)
        )
        ingredients: list[RecipeIngredientView] = []
        for ri, ing in result.all():
            ingredients.append(
                RecipeIngredientView(
                    name=ing.name,
                    ingredient_id=ing.id,
                )
            )
        return RecipeView(id=recipe_id, ingredients=tuple(ingredients))

    async def _load_exclusions(
        self, user_id: UUID, db: AsyncSession
    ) -> list[ExclusionView]:
        result = await db.execute(
            select(UserExclusion).where(UserExclusion.user_id == user_id)
        )
        return [
            ExclusionView(
                raw_name=e.ingredient_name_raw or "",
                ingredient_id=e.ingredient_id,
            )
            for e in result.scalars().all()
        ]

    @staticmethod
    def _macro_summary(nutrition: RecipeNutrition | None) -> MacroSummary:
        if nutrition is None:
            return MacroSummary(None, None, None, None, None)

        def _f(v: Decimal | float | None) -> float | None:
            return float(v) if v is not None else None

        return MacroSummary(
            calories=_f(nutrition.calories_per_serving),
            protein_g=_f(nutrition.protein_g),
            carbs_g=_f(nutrition.carbs_g),
            fat_g=_f(nutrition.fat_g),
            fiber_g=_f(nutrition.fiber_g),
        )
