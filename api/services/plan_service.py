from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from db.models import (
    JobQueue,
    JobStatus,
    MealPlan,
    PlanDay,
    PlanItem,
    PlanItemSource,
    PlanStatus,
    Recipe,
    RecipeType,
)
from exceptions import NotFoundError, OwnershipError, PlanGenerationFailedError
from schemas.plans import (
    GeneratedPlanData,
    PlanGenerationParams,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services._helpers import get_owned_recipe, get_profile_or_404


class PlanService:
    async def get_plan(
        self, plan_id: UUID, user_id: UUID, db: AsyncSession
    ) -> MealPlan:
        return await self._get_owned_plan(plan_id, user_id, db)

    async def list_plans(
        self,
        user_id: UUID,
        db: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 30,
        status: PlanStatus | None = None,
    ) -> tuple[list[MealPlan], int]:
        await get_profile_or_404(user_id, db)
        base = select(MealPlan).where(MealPlan.user_id == user_id)
        if status is not None:
            base = base.where(MealPlan.status == status)

        from sqlalchemy import func

        count_result = await db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())
        result = await db.execute(
            base.order_by(MealPlan.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def create_plan_stub(
        self, user_id: UUID, params: PlanGenerationParams, db: AsyncSession
    ) -> tuple[MealPlan, JobQueue]:
        profile = await get_profile_or_404(user_id, db)

        if params.cloned_from_plan_id is not None:
            await self._get_owned_plan(params.cloned_from_plan_id, user_id, db)

        cooking = params.cooking_type or profile.cooking_type
        calories = (
            params.calorie_target
            if params.calorie_target is not None
            else profile.calorie_target
        )
        week_start = params.week_start_date or datetime.now(timezone.utc).date()

        plan = MealPlan(
            user_id=user_id,
            conversation_id=params.conversation_id,
            cloned_from_plan_id=params.cloned_from_plan_id,
            title=None,
            diet_type_snapshot=params.diet_type,
            diet_subtypes_snapshot=list(profile.diet_subtypes),
            cooking_type_snapshot=cooking,
            calorie_target_snapshot=calories,
            protein_g_target_snapshot=profile.protein_g_target,
            carbs_g_target_snapshot=profile.carbs_g_target,
            fat_g_target_snapshot=profile.fat_g_target,
            fiber_g_target_snapshot=profile.fiber_g_target,
            recipe_usage_policy=params.sourcing_policy,
            generation_params=params.model_dump(mode="json"),
            status=PlanStatus.DRAFT,
            num_days=params.duration_days,
            week_start_date=week_start,
            notes=params.notes,
        )
        db.add(plan)
        await db.flush()

        job = JobQueue(
            job_type="generate_plan",
            user_id=user_id,
            plan_id=plan.id,
            status=JobStatus.PENDING,
            payload={
                "plan_id": str(plan.id),
                "params": params.model_dump(mode="json"),
            },
        )
        db.add(job)
        await db.flush()
        await db.refresh(plan)
        await db.refresh(job)
        return plan, job

    async def get_plan_days(
        self, plan_id: UUID, user_id: UUID, db: AsyncSession
    ) -> list[tuple[PlanDay, list[PlanItem]]]:
        await self._get_owned_plan(plan_id, user_id, db)
        days_result = await db.execute(
            select(PlanDay)
            .where(PlanDay.plan_id == plan_id)
            .order_by(PlanDay.day_number.asc())
        )
        days = list(days_result.scalars().all())
        day_ids = [d.id for d in days]
        items_by_day: dict[UUID, list[PlanItem]] = {d.id: [] for d in days}
        if day_ids:
            items_result = await db.execute(
                select(PlanItem).where(PlanItem.plan_day_id.in_(day_ids))
            )
            for item in items_result.scalars().all():
                items_by_day.setdefault(item.plan_day_id, []).append(item)
        return [(day, items_by_day.get(day.id, [])) for day in days]

    async def delete_plan(
        self, plan_id: UUID, user_id: UUID, db: AsyncSession
    ) -> None:
        plan = await self._get_owned_plan(plan_id, user_id, db)
        await db.delete(plan)
        await db.flush()

    async def update_plan_status(
        self,
        plan_id: UUID,
        user_id: UUID,
        status: PlanStatus,
        db: AsyncSession,
    ) -> MealPlan:
        plan = await self._get_owned_plan(plan_id, user_id, db)
        plan.status = status
        await db.flush()
        await db.refresh(plan)
        return plan

    async def write_generated_plan(
        self,
        plan_id: UUID,
        generated: GeneratedPlanData,
        db: AsyncSession,
        *,
        on_day_written: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> MealPlan:
        plan = await db.get(MealPlan, plan_id)
        if plan is None:
            raise NotFoundError("Meal plan not found")

        recipe_types = await self._owned_recipe_types(plan.user_id, generated, db)

        # Clear existing days/items if regenerating
        existing_days = await db.execute(
            select(PlanDay).where(PlanDay.plan_id == plan_id)
        )
        for day in existing_days.scalars().all():
            await db.delete(day)
        await db.flush()

        if generated.title is not None:
            plan.title = generated.title
        if generated.review_notes:
            existing = (plan.notes or "").strip()
            plan.notes = (
                f"{existing}\n\n{generated.review_notes}".strip()
                if existing
                else generated.review_notes
            )

        for day_data in generated.days:
            day_date = day_data.date
            if day_date is None:
                day_date = plan.week_start_date + timedelta(days=day_data.day_number - 1)

            day = PlanDay(
                plan_id=plan.id,
                day_number=day_data.day_number,
                date=day_date,
                totals_incomplete=any(
                    item.nutrition_unknown for item in day_data.items
                )
                or day_data.totals_incomplete,
            )
            db.add(day)
            await db.flush()

            day_calories = day_protein = day_carbs = day_fat = day_fiber = 0.0
            known_items = [
                item for item in day_data.items if not item.nutrition_unknown
            ]
            for item_data in day_data.items:
                item = PlanItem(
                    plan_day_id=day.id,
                    slot=item_data.slot_type,
                    slot_order=item_data.slot_order,
                    recipe_id=item_data.recipe_id,
                    item_source=item_data.item_source,
                    name=item_data.recipe_title,
                    description=item_data.description,
                    recipe_type=(
                        recipe_types.get(item_data.recipe_id, item_data.recipe_type)
                        if item_data.recipe_id is not None
                        else item_data.recipe_type
                    ),
                    color=item_data.color,
                    prep_method=item_data.prep_method,
                    prep_minutes=item_data.prep_minutes,
                    calories=item_data.calories,
                    protein_g=item_data.protein_g,
                    carbs_g=item_data.carbs_g,
                    fat_g=item_data.fat_g,
                    fiber_g=item_data.fiber_g,
                    juice_time=item_data.juice_time,
                    juice_size_ml=item_data.juice_size_ml,
                    nutrition_unknown=item_data.nutrition_unknown,
                )
                db.add(item)
            for item_data in known_items:
                day_calories += float(item_data.calories or 0)
                day_protein += float(item_data.protein_g or 0)
                day_carbs += float(item_data.carbs_g or 0)
                day_fat += float(item_data.fat_g or 0)
                day_fiber += float(item_data.fiber_g or 0)

            day.calories_actual = day_calories
            day.protein_g_actual = day_protein
            day.carbs_g_actual = day_carbs
            day.fat_g_actual = day_fat
            day.fiber_g_actual = day_fiber
            day.calories_target = plan.calorie_target_snapshot
            day.protein_g_target = plan.protein_g_target_snapshot
            day.carbs_g_target = plan.carbs_g_target_snapshot
            day.fat_g_target = plan.fat_g_target_snapshot
            day.fiber_g_target = plan.fiber_g_target_snapshot
            await db.flush()
            if on_day_written is not None:
                await on_day_written(day_data.day_number, len(generated.days))

        plan.status = PlanStatus.REVIEWING
        await db.flush()
        await db.refresh(plan)
        return plan

    async def _assert_recipes_owned(
        self,
        user_id: UUID,
        generated: GeneratedPlanData,
        db: AsyncSession,
    ) -> None:
        """Reject foreign or missing recipe ids before any day is written."""
        await self._owned_recipe_types(user_id, generated, db)

    async def _owned_recipe_types(
        self,
        user_id: UUID,
        generated: GeneratedPlanData,
        db: AsyncSession,
    ) -> dict[UUID, RecipeType]:
        """Owned recipe ids mapped to the recipe's own recipe_type."""
        ids = list(
            dict.fromkeys(
                item.recipe_id
                for day in generated.days
                for item in day.items
                if item.recipe_id is not None
            )
        )
        if not ids:
            return {}
        result = await db.execute(
            select(Recipe.id, Recipe.recipe_type).where(
                Recipe.id.in_(ids),
                Recipe.user_id == user_id,
                Recipe.deleted_at.is_(None),
            )
        )
        owned_ids: set[UUID] = set()
        types: dict[UUID, RecipeType] = {}
        for row in result.all():
            if isinstance(row, UUID):
                owned_ids.add(row)
                continue
            recipe_id, recipe_type = row[0], row[1]
            owned_ids.add(recipe_id)
            if isinstance(recipe_type, RecipeType):
                types[recipe_id] = recipe_type
        for recipe_id in ids:
            if recipe_id not in owned_ids:
                raise PlanGenerationFailedError(
                    f"Recipe {recipe_id} not owned by user"
                )
        return types

    async def swap_plan_item(
        self,
        plan_id: UUID,
        item_id: UUID,
        user_id: UUID,
        new_recipe_id: UUID,
        db: AsyncSession,
    ) -> PlanItem:
        await self._get_owned_plan(plan_id, user_id, db)
        recipe = await get_owned_recipe(new_recipe_id, user_id, db)

        item = await db.get(PlanItem, item_id)
        if item is None:
            raise NotFoundError("Plan item not found")

        day = await db.get(PlanDay, item.plan_day_id)
        if day is None or day.plan_id != plan_id:
            raise OwnershipError("Plan item not found")

        nutrition = None
        from db.models import RecipeNutrition

        nutrition = await db.get(RecipeNutrition, recipe.id)

        item.recipe_id = recipe.id
        item.name = recipe.name
        item.description = recipe.description
        item.recipe_type = recipe.recipe_type
        item.color = recipe.color
        item.prep_method = recipe.prep_method
        item.prep_minutes = recipe.prep_minutes
        item.item_source = PlanItemSource.SAVED_RECIPE
        if nutrition is not None:
            item.calories = nutrition.calories_per_serving
            item.protein_g = nutrition.protein_g
            item.carbs_g = nutrition.carbs_g
            item.fat_g = nutrition.fat_g
            item.fiber_g = nutrition.fiber_g

        await db.flush()
        await db.refresh(item)
        return item

    async def apply_recipe_nutrition_to_items(
        self,
        recipe_id: UUID,
        nutrition: Any,
        db: AsyncSession,
    ) -> None:
        """Copy recipe_nutrition onto plan_items that still have null snapshots."""
        items_result = await db.execute(
            select(PlanItem).where(PlanItem.recipe_id == recipe_id)
        )
        items = list(items_result.scalars().all())
        if not items:
            return

        touched_days: set[UUID] = set()
        for item in items:
            if item.calories is not None:
                continue
            item.calories = nutrition.calories_per_serving
            item.protein_g = nutrition.protein_g
            item.carbs_g = nutrition.carbs_g
            item.fat_g = nutrition.fat_g
            item.fiber_g = nutrition.fiber_g
            item.nutrition_unknown = False
            touched_days.add(item.plan_day_id)

        for day_id in touched_days:
            day = await db.get(PlanDay, day_id)
            if day is None:
                continue
            day_items_result = await db.execute(
                select(PlanItem).where(PlanItem.plan_day_id == day_id)
            )
            day_items = list(day_items_result.scalars().all())
            known = [item for item in day_items if not item.nutrition_unknown]
            day.totals_incomplete = any(item.nutrition_unknown for item in day_items)
            day.calories_actual = sum(float(item.calories or 0) for item in known)
            day.protein_g_actual = sum(float(item.protein_g or 0) for item in known)
            day.carbs_g_actual = sum(float(item.carbs_g or 0) for item in known)
            day.fat_g_actual = sum(float(item.fat_g or 0) for item in known)
            day.fiber_g_actual = sum(float(item.fiber_g or 0) for item in known)

        await db.flush()

    async def approve_plan(
        self, plan_id: UUID, user_id: UUID, db: AsyncSession
    ) -> MealPlan:
        plan = await self._get_owned_plan(plan_id, user_id, db)
        plan.status = PlanStatus.APPROVED
        await db.flush()
        await db.refresh(plan)
        return plan

    async def _get_owned_plan(
        self, plan_id: UUID, user_id: UUID, db: AsyncSession
    ) -> MealPlan:
        plan = await db.get(MealPlan, plan_id)
        if plan is None:
            raise NotFoundError("Meal plan not found")
        if plan.user_id != user_id:
            raise OwnershipError("Meal plan not found")
        return plan
