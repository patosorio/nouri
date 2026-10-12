from __future__ import annotations

from uuid import UUID

from db.models import AuthUser, Ingredient, UserExclusion, UserProfile, UserTier
from exceptions import NotFoundError, OwnershipError
from schemas.profile import ProfileCreate, ProfileUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services._helpers import get_profile_or_404


class ProfileService:
    async def get_profile(self, user_id: UUID, db: AsyncSession) -> UserProfile:
        return await get_profile_or_404(user_id, db)

    async def ensure_profile(self, user_id: UUID, db: AsyncSession) -> UserProfile:
        """Create auth.users + user_profiles stubs so FKs can succeed.

        Hosted Supabase Auth issues a JWT before this database has a matching
        user_profiles row. conversations / meal_plans / job_queue all FK to
        user_profiles. Onboarding later updates the stub.
        """
        profile = await db.get(UserProfile, user_id)
        if profile is not None:
            return profile
        auth_user = await db.get(AuthUser, user_id)
        if auth_user is None:
            db.add(AuthUser(id=user_id))
            await db.flush()
        profile = UserProfile(id=user_id)
        db.add(profile)
        await db.flush()
        await db.refresh(profile)
        return profile

    async def set_tier(
        self, user_id: UUID, tier: UserTier, db: AsyncSession
    ) -> UserProfile:
        profile = await self.ensure_profile(user_id, db)
        profile.tier = tier
        await db.flush()
        await db.refresh(profile)
        return profile

    async def create_profile(
        self, user_id: UUID, data: ProfileCreate, db: AsyncSession
    ) -> UserProfile:
        existing = await db.get(UserProfile, user_id)
        if existing is not None:
            raise OwnershipError("User profile already exists")

        auth_user = await db.get(AuthUser, user_id)
        if auth_user is None:
            db.add(AuthUser(id=user_id))
            await db.flush()

        profile = UserProfile(
            id=user_id,
            display_name=data.display_name,
            diet_type=data.diet_type,
            diet_subtypes=list(data.diet_subtypes),
            cuisine_prefs=list(data.cuisine_prefs),
            cooking_type=data.cooking_type,
            calorie_target=data.calorie_target,
            protein_g_target=data.protein_g_target,
            carbs_g_target=data.carbs_g_target,
            fat_g_target=data.fat_g_target,
            fiber_g_target=data.fiber_g_target,
            recipe_usage_policy=data.recipe_usage_policy,
            juicing_enabled=data.juicing_enabled,
            free_text_preferences=data.free_text_preferences,
            timezone=data.timezone,
        )
        db.add(profile)
        await db.flush()
        await db.refresh(profile)
        return profile

    async def update_profile(
        self, user_id: UUID, data: ProfileUpdate, db: AsyncSession
    ) -> UserProfile:
        profile = await get_profile_or_404(user_id, db)
        updates = data.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(profile, key, value)
        await db.flush()
        await db.refresh(profile)
        return profile

    async def get_exclusions(
        self, user_id: UUID, db: AsyncSession
    ) -> list[UserExclusion]:
        await get_profile_or_404(user_id, db)
        result = await db.execute(
            select(UserExclusion)
            .where(UserExclusion.user_id == user_id)
            .order_by(UserExclusion.created_at.asc())
        )
        return list(result.scalars().all())

    async def add_exclusion(
        self, user_id: UUID, ingredient_id: UUID, db: AsyncSession
    ) -> UserExclusion:
        await get_profile_or_404(user_id, db)
        ingredient = await db.get(Ingredient, ingredient_id)
        if ingredient is None:
            raise NotFoundError("Ingredient not found")

        existing = await db.execute(
            select(UserExclusion).where(
                UserExclusion.user_id == user_id,
                UserExclusion.ingredient_name_raw == ingredient.name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise OwnershipError("Exclusion already exists for this ingredient")

        exclusion = UserExclusion(
            user_id=user_id,
            ingredient_id=ingredient.id,
            ingredient_name_raw=ingredient.name,
        )
        db.add(exclusion)
        await db.flush()
        await db.refresh(exclusion)
        return exclusion

    async def add_exclusion_by_name(
        self, user_id: UUID, ingredient_name_raw: str, db: AsyncSession
    ) -> UserExclusion:
        from preprocessing.exclusion_service import ExclusionService

        await get_profile_or_404(user_id, db)
        name = ingredient_name_raw.strip()
        if not name:
            raise NotFoundError("ingredient_name_raw is required")

        ingredient_id = await ExclusionService().resolve_name(name, db)
        existing = await db.execute(
            select(UserExclusion).where(
                UserExclusion.user_id == user_id,
                UserExclusion.ingredient_name_raw == name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise OwnershipError("Exclusion already exists for this ingredient")

        exclusion = UserExclusion(
            user_id=user_id,
            ingredient_id=ingredient_id,
            ingredient_name_raw=name,
        )
        db.add(exclusion)
        await db.flush()
        await db.refresh(exclusion)
        return exclusion

    async def remove_exclusion(
        self, user_id: UUID, exclusion_id: UUID, db: AsyncSession
    ) -> None:
        result = await db.execute(
            select(UserExclusion).where(UserExclusion.id == exclusion_id)
        )
        exclusion = result.scalar_one_or_none()
        if exclusion is None:
            raise NotFoundError("Exclusion not found")
        if exclusion.user_id != user_id:
            raise OwnershipError("Exclusion not found")
        await db.delete(exclusion)
        await db.flush()
