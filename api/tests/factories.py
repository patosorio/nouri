"""Factory helpers for integration tests — docs/8_TEST_PLAN.md Phase 11."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AuthUser,
    CookingType,
    DietType,
    Ingredient,
    MealPlan,
    PlanDay,
    PlanItem,
    PlanItemSource,
    PlanSlot,
    PlanStatus,
    PreparationType,
    Recipe,
    RecipeDietCompatibility,
    RecipeIngredient,
    RecipeNutrition,
    RecipeSource,
    RecipeType,
    RecipeUsagePolicy,
    UserExclusion,
    UserProfile,
    UserTier,
)
from services._helpers import normalise_ingredient_name


async def make_auth_user(db: AsyncSession, *, user_id: UUID | None = None) -> AuthUser:
    uid = user_id or uuid4()
    user = AuthUser(id=uid)
    db.add(user)
    await db.flush()
    return user


async def make_user(
    db: AsyncSession,
    *,
    user_id: UUID | None = None,
    email: str = "test@nouri.app",
    tier: UserTier = UserTier.FREE,
    diet_type: DietType = DietType.PLANT_BASED,
    cooking_type: CookingType = CookingType.RAW_80_COOKED_20,
    display_name: str = "Test User",
) -> UserProfile:
    auth = await make_auth_user(db, user_id=user_id)
    profile = UserProfile(
        id=auth.id,
        display_name=display_name,
        diet_type=diet_type,
        cooking_type=cooking_type,
        tier=tier,
        juicing_enabled=True,
        calorie_target=2050,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    setattr(profile, "_test_email", email)
    return profile


async def make_ingredient(
    db: AsyncSession,
    *,
    name: str = "spinach",
    ingredient_id: UUID | None = None,
) -> Ingredient:
    normalised = normalise_ingredient_name(name)
    result = await db.execute(
        select(Ingredient).where(Ingredient.name_normalised == normalised)
    )
    found = result.scalar_one_or_none()
    if found is not None:
        return found

    ing = Ingredient(
        id=ingredient_id or uuid4(),
        name=name.strip(),
        name_normalised=normalised,
        default_unit="g",
    )
    db.add(ing)
    await db.flush()
    return ing


async def make_exclusion(
    db: AsyncSession,
    user_id: UUID,
    *,
    name: str = "peanuts",
    ingredient_id: UUID | None = None,
) -> UserExclusion:
    row = UserExclusion(
        user_id=user_id,
        ingredient_id=ingredient_id,
        ingredient_name_raw=name,
    )
    db.add(row)
    await db.flush()
    return row


async def make_recipe(
    db: AsyncSession,
    user_id: UUID,
    *,
    name: str = "Golden Turmeric Overnight Oats",
    recipe_type: RecipeType = RecipeType.MEAL,
    cooking_type: CookingType = CookingType.RAW_100,
    prep_method: PreparationType = PreparationType.RAW,
    diet_type: DietType = DietType.PLANT_BASED,
    calories: float = 320,
    protein_g: float = 12,
    carbs_g: float = 48,
    fat_g: float = 10,
    fiber_g: float = 8,
    ingredient_names: list[str] | None = None,
) -> Recipe:
    recipe = Recipe(
        user_id=user_id,
        name=name,
        description=(
            "Steel-cut oats soaked overnight in turmeric-cashew milk, chia, and mango."
            if name == "Golden Turmeric Overnight Oats"
            else f"Test recipe: {name}"
        ),
        recipe_type=recipe_type,
        prep_method=prep_method,
        cooking_type=cooking_type,
        source=RecipeSource.AI_GENERATED,
        servings=1,
        prep_minutes=10,
        steps=[{"step_number": 1, "instruction": "Prepare ingredients."}],
    )
    db.add(recipe)
    await db.flush()

    db.add(RecipeDietCompatibility(recipe_id=recipe.id, diet_type=diet_type))
    db.add(
        RecipeNutrition(
            recipe_id=recipe.id,
            calories_per_serving=Decimal(str(calories)),
            protein_g=Decimal(str(protein_g)),
            carbs_g=Decimal(str(carbs_g)),
            fat_g=Decimal(str(fat_g)),
            fiber_g=Decimal(str(fiber_g)),
        )
    )

    names = ingredient_names or ["oats", "cashew milk", "turmeric"]
    for i, ing_name in enumerate(names):
        ing = await make_ingredient(db, name=ing_name)
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ing.id,
                amount=Decimal("1"),
                unit="cup",
                sort_order=i,
            )
        )

    await db.flush()
    await db.refresh(recipe)
    return recipe


async def make_plan(
    db: AsyncSession,
    user_id: UUID,
    *,
    num_days: int = 7,
    status: PlanStatus = PlanStatus.REVIEWING,
    week_start: date | None = None,
    with_meals: bool = True,
    recipe: Recipe | None = None,
) -> MealPlan:
    start = week_start or date.today()
    plan = MealPlan(
        user_id=user_id,
        title=f"Week of {start.isoformat()}",
        diet_type_snapshot=DietType.PLANT_BASED,
        cooking_type_snapshot=CookingType.RAW_80_COOKED_20,
        calorie_target_snapshot=2050,
        recipe_usage_policy=RecipeUsagePolicy.PREFER_SAVED,
        status=status,
        num_days=num_days,
        week_start_date=start,
    )
    db.add(plan)
    await db.flush()

    meal_recipe = recipe
    if with_meals and meal_recipe is None:
        meal_recipe = await make_recipe(db, user_id)

    for day_n in range(1, num_days + 1):
        day = PlanDay(
            plan_id=plan.id,
            day_number=day_n,
            date=start + timedelta(days=day_n - 1),
            calories_actual=Decimal("2040"),
            protein_g_actual=Decimal("72"),
            carbs_g_actual=Decimal("238"),
            fat_g_actual=Decimal("64"),
            calories_target=Decimal("2050"),
            protein_g_target=Decimal("76"),
            carbs_g_target=Decimal("225"),
            fat_g_target=Decimal("70"),
        )
        db.add(day)
        await db.flush()

        if not with_meals or meal_recipe is None:
            continue

        # Screen-09 style day: saved breakfast, AI lunch, baked dinner + juice.
        slot_specs: list[
            tuple[PlanSlot, int, str, str, PlanItemSource, PreparationType]
        ] = [
            (
                PlanSlot.BREAKFAST,
                320,
                meal_recipe.name,
                meal_recipe.description
                or "Steel-cut oats soaked overnight in turmeric-cashew milk, chia, and mango.",
                PlanItemSource.SAVED_RECIPE,
                PreparationType.RAW,
            ),
            (
                PlanSlot.LUNCH,
                410,
                "Zucchini Pad Thai with Almond Sauce",
                "Spiralized zucchini noodles tossed in a raw almond-tamari sauce.",
                PlanItemSource.AI_GENERATED,
                PreparationType.RAW,
            ),
            (
                PlanSlot.DINNER,
                480,
                "Miso-Glazed Roasted Cauliflower Steaks",
                "Thick cauliflower steaks roasted with a sweet miso glaze, served over quinoa.",
                PlanItemSource.AI_GENERATED,
                PreparationType.BAKED,
            ),
        ]

        for order, (slot, cal, label, desc, source, prep) in enumerate(slot_specs):
            db.add(
                PlanItem(
                    plan_day_id=day.id,
                    slot=slot,
                    recipe_id=(
                        meal_recipe.id
                        if source == PlanItemSource.SAVED_RECIPE
                        else None
                    ),
                    name=label,
                    description=desc,
                    recipe_type=RecipeType.MEAL,
                    item_source=source,
                    prep_method=prep,
                    prep_minutes=(
                        10
                        if slot == PlanSlot.BREAKFAST
                        else (15 if slot == PlanSlot.LUNCH else 30)
                    ),
                    slot_order=order,
                    calories=Decimal(str(cal)),
                    protein_g=Decimal("14"),
                    carbs_g=Decimal("52"),
                    fat_g=Decimal("16"),
                    fiber_g=Decimal("8"),
                )
            )
        db.add(
            PlanItem(
                plan_day_id=day.id,
                slot=PlanSlot.JUICE,
                recipe_id=None,
                name="Afternoon Green Renewal",
                description="Cucumber · celery · green apple · mint",
                recipe_type=RecipeType.JUICE,
                item_source=PlanItemSource.AI_GENERATED,
                prep_method=PreparationType.JUICED,
                color="#6FCF7B",
                prep_minutes=5,
                slot_order=3,
                calories=Decimal("90"),
                protein_g=Decimal("2"),
                carbs_g=Decimal("20"),
                fat_g=Decimal("0"),
                fiber_g=Decimal("3"),
            )
        )

    await db.flush()
    await db.refresh(plan)
    return plan
