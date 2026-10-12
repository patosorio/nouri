"""RecipeSearchService — Voyage AI embeddings + pgvector kNN (docs/7_TECH_SPEC.md §9)."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
import voyageai
from config import settings
from db.models import (
    DietType,
    Ingredient,
    MealPlan,
    MealRole,
    PlanDay,
    PlanItem,
    PrimaryProtein,
    Recipe,
    RecipeDietCompatibility,
    RecipeEmbedding,
    RecipeIngredient,
    RecipeMealDetails,
    RecipeNutrition,
    RecipeType,
    UserExclusion,
)
from schemas.common import PaginatedResult
from schemas.recipes import RecipeFilters
from sqlalchemy import exists, false, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from validation.exclusion_checker import ExclusionChecker
from validation.types import ExclusionView, RecipeIngredientView, RecipeView

logger = structlog.get_logger(__name__)

_EXACT_SEARCH_ROW_THRESHOLD = 1000
_PLANNING_CANDIDATE_CAP = 60
_PLANNING_POOL_LIMIT = _PLANNING_CANDIDATE_CAP * 5
_PLANNING_ROLE_ORDER = (
    "breakfast",
    "lunch",
    "dinner",
    "snack",
    "juice",
    "smoothie",
)
_PLANNING_PROTEIN_ORDER = tuple(protein.value for protein in PrimaryProtein)


def build_knn_select_sql(
    *,
    query_vec: str,
    user_id: str,
    diet_type: str | None,
    cooking_type: str | None,
    recipe_type: str | None,
    prep_method: str | None,
    limit_n: int,
    offset_n: int,
) -> tuple[str, dict[str, str | int]]:
    """kNN SQL with optional filters.

    Bind names must never sit next to Postgres `::` casts — SQLAlchemy leaves
    `:diet_type::text` unbound and asyncpg raises PostgresSyntaxError.
    """
    filters = [
        "r.user_id = CAST(:user_id AS uuid)",
        "r.deleted_at IS NULL",
    ]
    params: dict[str, str | int] = {
        "query_vec": query_vec,
        "user_id": user_id,
        "limit_n": limit_n,
        "offset_n": offset_n,
    }
    if diet_type is not None:
        filters.append(
            "EXISTS ("
            " SELECT 1 FROM recipe_diet_compatibility rdc"
            " WHERE rdc.recipe_id = r.id"
            " AND CAST(rdc.diet_type AS text) = :diet_type)"
        )
        params["diet_type"] = diet_type
    if cooking_type is not None:
        filters.append("CAST(r.cooking_type AS text) = :cooking_type")
        params["cooking_type"] = cooking_type
    if recipe_type is not None:
        filters.append("CAST(r.recipe_type AS text) = :recipe_type")
        params["recipe_type"] = recipe_type
    if prep_method is not None:
        filters.append("CAST(r.prep_method AS text) = :prep_method")
        params["prep_method"] = prep_method

    where_sql = " AND ".join(filters)
    sql = f"""
            SELECT
                r.id,
                (re.embedding <=> CAST(:query_vec AS vector)) AS distance
            FROM recipe_embeddings re
            JOIN recipes r ON r.id = re.recipe_id
            WHERE {where_sql}
            ORDER BY distance ASC
            LIMIT :limit_n OFFSET :offset_n
        """
    return sql, params


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
    meal_roles: list[str] = field(default_factory=list)
    recipe_type: str | None = None


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

        model = self._resolve_model()
        dim = settings.voyage_embedding_dim

        def _call() -> list[list[float]]:
            kwargs: dict[str, Any] = {
                "texts": texts,
                "model": model,
                "input_type": input_type,
            }
            # voyage-3.5* / voyage-4* accept output_dimension; voyage-3 ignores or
            # only supports its native size — pass only when not the classic voyage-3.
            if model not in ("voyage-3", "voyage-3-lite"):
                kwargs["output_dimension"] = dim
            result = self._client().embed(**kwargs)
            return list(result.embeddings)

        vectors = await asyncio.to_thread(_call)
        for vector in vectors:
            if len(vector) != dim:
                raise ValueError(
                    f"Voyage model {model!r} returned {len(vector)}-dim embeddings; "
                    f"database expects {dim}. Set VOYAGE_MODEL=voyage-3 "
                    f"(or another 1024-dim model)."
                )
        return vectors

    @staticmethod
    def _resolve_model() -> str:
        """voyage-3-lite is 512-dim; ERD/pgvector column is VECTOR(1024)."""
        model = settings.voyage_model
        if model == "voyage-3-lite" and settings.voyage_embedding_dim == 1024:
            logger.warning(
                "voyage_model_override",
                configured=model,
                using="voyage-3",
                reason="voyage-3-lite returns 512 dims; schema requires 1024",
            )
            return "voyage-3"
        return model

    async def embed_recipe(self, recipe: Recipe, db: AsyncSession) -> list[float]:
        embedding_text = await self._build_embedding_text(recipe, db)
        content_hash = hashlib.md5(embedding_text.encode("utf-8")).hexdigest()
        model = self._resolve_model()

        existing = await db.get(RecipeEmbedding, recipe.id)
        if (
            existing is not None
            and existing.content_hash == content_hash
            and existing.model_version == model
        ):
            return list(existing.embedding)

        vectors = await self.embed_texts([embedding_text], input_type="document")
        vector = vectors[0]

        if existing is None:
            db.add(
                RecipeEmbedding(
                    recipe_id=recipe.id,
                    embedding=vector,
                    model_version=model,
                    content_hash=content_hash,
                )
            )
        else:
            existing.embedding = vector
            existing.model_version = model
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
        """Planning retrieval. Makes no embedding calls."""
        del days
        return await self.planning_candidates(
            user_id,
            diet_type,
            ("breakfast", "lunch", "dinner"),
            (),
            db,
        )

    async def planning_candidates(
        self,
        user_id: UUID,
        diet_type: str,
        roles: list[str] | tuple[str, ...],
        excluded_ingredient_ids: list[UUID] | tuple[UUID, ...],
        db: AsyncSession,
        cap: int = _PLANNING_CANDIDATE_CAP,
        *,
        juicing_enabled: bool = False,
    ) -> list[RecipeCandidate]:
        """SQL-filtered, deterministic saved recipes for plan generation.

        Least recently used first, then round-robin by role and protein.
        Voyage is not called. ExclusionChecker is a second guard after SQL.
        """
        diet_enum = self._diet_enum(diet_type)
        if diet_enum is None:
            return []

        rows = await self._planning_rows(
            user_id,
            diet_enum,
            roles,
            excluded_ingredient_ids,
            db,
            juicing_enabled=juicing_enabled,
        )
        if not rows:
            return []

        ingredients = await self._ingredients_by_recipe(
            [row.recipe_id for row in rows], db
        )
        exclusion_views = await self._load_exclusions(user_id, db)
        views = [
            RecipeView(id=row.recipe_id, ingredients=ingredients.get(row.recipe_id, ()))
            for row in rows
        ]
        # SQL already excluded ingredient ids and capped the pool. This check
        # is a second guard; if it removes rows, the result may be under 60.
        kept_ids = {
            view.id
            for view in self._exclusions.filter_candidates(views, exclusion_views)
        }
        eligible = [row for row in rows if row.recipe_id in kept_ids]
        picked = _round_robin(eligible, cap)
        return [
            RecipeCandidate(
                recipe_id=row.recipe_id,
                title=row.title,
                diet_type=row.diet_type,
                cooking_type=row.cooking_type,
                macro_summary=row.macros,
                similarity=0.0,
                meal_roles=list(row.meal_roles),
                recipe_type=row.recipe_type,
            )
            for row in picked
        ]

    async def _planning_rows(
        self,
        user_id: UUID,
        diet_type: DietType,
        roles: list[str] | tuple[str, ...],
        excluded_ingredient_ids: list[UUID] | tuple[UUID, ...],
        db: AsyncSession,
        *,
        juicing_enabled: bool,
    ) -> list[_PlanningRow]:
        meal_roles = _coerce_meal_roles(roles)
        last_used = (
            select(
                PlanItem.recipe_id.label("recipe_id"),
                func.max(PlanDay.date).label("last_used"),
            )
            .join(PlanDay, PlanDay.id == PlanItem.plan_day_id)
            .join(MealPlan, MealPlan.id == PlanDay.plan_id)
            .where(MealPlan.user_id == user_id, PlanItem.recipe_id.is_not(None))
            .group_by(PlanItem.recipe_id)
            .subquery()
        )
        diet_label = (
            select(RecipeDietCompatibility.diet_type)
            .where(RecipeDietCompatibility.recipe_id == Recipe.id)
            .limit(1)
            .scalar_subquery()
        )
        meal_match = (
            RecipeMealDetails.meal_roles.overlap(meal_roles) if meal_roles else false()
        )
        if juicing_enabled:
            kind_match = meal_match | Recipe.recipe_type.in_(
                (RecipeType.JUICE, RecipeType.SMOOTHIE)
            )
        else:
            kind_match = meal_match
        stmt = (
            select(
                Recipe,
                RecipeNutrition,
                RecipeMealDetails.meal_roles,
                RecipeMealDetails.primary_protein_source,
                diet_label,
            )
            .join(RecipeNutrition, RecipeNutrition.recipe_id == Recipe.id)
            .outerjoin(RecipeMealDetails, RecipeMealDetails.recipe_id == Recipe.id)
            .outerjoin(last_used, last_used.c.recipe_id == Recipe.id)
            .where(
                Recipe.user_id == user_id,
                Recipe.deleted_at.is_(None),
                Recipe.id.in_(
                    select(RecipeDietCompatibility.recipe_id).where(
                        RecipeDietCompatibility.diet_type == diet_type
                    )
                ),
                kind_match,
            )
            .order_by(
                last_used.c.last_used.asc().nulls_first(),
                Recipe.created_at.asc(),
                Recipe.id.asc(),
            )
        )
        if excluded_ingredient_ids:
            blocked = exists(
                select(RecipeIngredient.id).where(
                    RecipeIngredient.recipe_id == Recipe.id,
                    RecipeIngredient.ingredient_id.in_(list(excluded_ingredient_ids)),
                )
            )
            stmt = stmt.where(~blocked)
        stmt = stmt.limit(_PLANNING_POOL_LIMIT)
        result = await db.execute(stmt)
        rows: list[_PlanningRow] = []
        for recipe, nutrition, meal_role_values, protein, diet in result.all():
            role_values = _role_values(meal_role_values)
            protein_value = protein.value if hasattr(protein, "value") else (protein or "none")
            if not protein_value:
                protein_value = "none"
            diet_value = diet.value if hasattr(diet, "value") else diet
            rows.append(
                _PlanningRow(
                    recipe_id=recipe.id,
                    title=recipe.name,
                    recipe_type=recipe.recipe_type.value,
                    cooking_type=recipe.cooking_type.value,
                    diet_type=str(diet_value) if diet_value is not None else None,
                    role=_planning_role(recipe.recipe_type.value, role_values),
                    protein=str(protein_value),
                    macros=self._macro_summary(nutrition),
                    meal_roles=tuple(role_values),
                )
            )
        return rows

    async def _ingredients_by_recipe(
        self, recipe_ids: list[UUID], db: AsyncSession
    ) -> dict[UUID, tuple[RecipeIngredientView, ...]]:
        if not recipe_ids:
            return {}
        result = await db.execute(
            select(RecipeIngredient.recipe_id, Ingredient)
            .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
            .where(RecipeIngredient.recipe_id.in_(recipe_ids))
            .order_by(RecipeIngredient.sort_order.asc())
        )
        grouped: dict[UUID, list[RecipeIngredientView]] = {}
        for recipe_id, ingredient in result.all():
            grouped.setdefault(recipe_id, []).append(
                RecipeIngredientView(name=ingredient.name, ingredient_id=ingredient.id)
            )
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    def _diet_enum(diet_type: str) -> DietType | None:
        try:
            return DietType(diet_type)
        except ValueError:
            return None

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
        sql, params = build_knn_select_sql(
            query_vec=vector_literal,
            user_id=str(user_id),
            diet_type=diet_type,
            cooking_type=cooking_type,
            recipe_type=recipe_type,
            prep_method=prep_method,
            limit_n=limit,
            offset_n=offset,
        )
        result = await db.execute(text(sql), params)
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


@dataclass(frozen=True, slots=True)
class _PlanningRow:
    recipe_id: UUID
    title: str
    recipe_type: str
    cooking_type: str
    diet_type: str | None
    role: str
    protein: str
    macros: MacroSummary
    meal_roles: tuple[str, ...] = ()


def _coerce_meal_roles(
    roles: list[str] | tuple[str, ...],
) -> list[MealRole]:
    parsed: list[MealRole] = []
    for role in roles:
        try:
            parsed.append(MealRole(role))
        except ValueError:
            continue
    return parsed


def _role_values(meal_roles: object) -> list[str]:
    if not meal_roles:
        return []
    values: list[str] = []
    for role in meal_roles:  # type: ignore[union-attr]
        values.append(role.value if hasattr(role, "value") else str(role))
    return values


def _planning_role(recipe_type: str, meal_roles: list[str]) -> str:
    if recipe_type in (RecipeType.JUICE.value, RecipeType.SMOOTHIE.value):
        return recipe_type
    if meal_roles:
        return meal_roles[0]
    return recipe_type


def _round_robin(rows: list[_PlanningRow], cap: int) -> list[_PlanningRow]:
    buckets: dict[tuple[str, str], list[_PlanningRow]] = {}
    for row in rows:
        buckets.setdefault((row.role, row.protein), []).append(row)
    if not buckets or cap <= 0:
        return []
    present_roles = {role for role, _protein in buckets}
    roles = [role for role in _PLANNING_ROLE_ORDER if role in present_roles]
    roles.extend(sorted(present_roles - set(roles)))
    present_proteins = {protein for _role, protein in buckets}
    proteins = [
        protein for protein in _PLANNING_PROTEIN_ORDER if protein in present_proteins
    ]
    proteins.extend(sorted(present_proteins - set(proteins)))
    picked: list[_PlanningRow] = []
    while len(picked) < cap:
        took = False
        for role in roles:
            for protein in proteins:
                bucket = buckets.get((role, protein))
                if not bucket:
                    continue
                picked.append(bucket.pop(0))
                took = True
                if len(picked) >= cap:
                    return picked
        if not took:
            break
    return picked
