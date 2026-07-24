"""
Seed rich demo data so every main UI screen has something to render.

Patri runs this (not the agent). Requires migrated DB + a real Supabase auth user.

Preferred (inside Compose — same network as Cloud-adjacent local topology):

  docker compose exec api python -m scripts.seed_demo_data \\
    --email patosorio.88@gmail.com --force

Host-side (venv) also works: db/session.py rewrites @db → @localhost only when
hostname `db` does not resolve. Inside containers that rewrite is a no-op.

  cd api && python -m scripts.seed_demo_data --email patosorio.88@gmail.com --force

Creates / refreshes for that user:
  - profile (plant-based, raw-leaning, PRO so pantry-aware shopping works)
  - exclusions, pantry items
  - ~6 saved recipes with ingredients + nutrition
  - reviewing 7-day plan (meal planner)
  - approved + scheduled 7-day plan (calendar, chat today, shopping)
  - shopping list for the approved plan
  - sample encrypted chat conversation
  - a couple of notifications
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import (
    AuthUser,
    Conversation,
    CookingType,
    DietType,
    MealPlan,
    Notification,
    NotificationType,
    PantryItem,
    PlanDay,
    PlanItem,
    PlanItemSource,
    PlanSlot,
    PlanStatus,
    PreparationType,
    Recipe,
    RecipeSource,
    RecipeType,
    RecipeUsagePolicy,
    UserExclusion,
    UserProfile,
    UserTier,
)
from db.session import async_session_factory
from encryption.field_encryption import FieldEncryption
from services.shopping_list_service import ShoppingListService
from tests.factories import make_exclusion, make_ingredient, make_plan, make_recipe

DEFAULT_EMAIL = "patosorio.88@gmail.com"
DEMO_PLAN_REVIEWING_TITLE = "Demo · Week in review"
DEMO_PLAN_APPROVED_TITLE = "Demo · Live week"


async def resolve_user_id(*, email: str | None, user_id: UUID | None) -> UUID:
    if user_id is not None:
        return user_id
    if not email:
        raise SystemExit("Pass --email or --user-id")

    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_role_key
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{url}/auth/v1/admin/users",
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
            },
            params={"page": 1, "per_page": 200},
        )
        response.raise_for_status()
        payload = response.json()
        users = payload.get("users", payload if isinstance(payload, list) else [])

    needle = email.strip().lower()
    for user in users:
        if str(user.get("email", "")).lower() == needle:
            return UUID(str(user["id"]))

    raise SystemExit(
        f"No Supabase auth user with email {email!r}. "
        "Sign up in the app first, or pass --user-id from the Supabase dashboard."
    )


async def _ensure_auth_and_profile(db: AsyncSession, user_id: UUID) -> UserProfile:
    auth = await db.get(AuthUser, user_id)
    if auth is None:
        db.add(AuthUser(id=user_id))
        await db.flush()

    profile = await db.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(id=user_id)
        db.add(profile)
        await db.flush()

    profile.display_name = "Patri"
    profile.diet_type = DietType.PLANT_BASED
    profile.diet_subtypes = ["high_raw", "gluten_free"]
    profile.cuisine_prefs = ["mediterranean", "thai", "mexican", "japanese"]
    profile.cooking_type = CookingType.RAW_80_COOKED_20
    profile.calorie_target = 2050
    profile.protein_g_target = 76
    profile.carbs_g_target = 225
    profile.fat_g_target = 70
    profile.fiber_g_target = 35
    profile.recipe_usage_policy = RecipeUsagePolicy.PREFER_SAVED
    profile.juicing_enabled = True
    profile.tier = UserTier.PRO
    profile.generation_credits_remaining = 40
    profile.free_text_preferences = (
        "Love turmeric, citrus, and crunchy textures. Keep dinners under 35 minutes."
    )
    profile.timezone = "Asia/Bangkok"
    await db.flush()
    return profile


async def _clear_demo_rows(db: AsyncSession, user_id: UUID) -> None:
    """Remove prior demo seed so --force is idempotent."""
    plan_ids = (
        await db.execute(select(MealPlan.id).where(MealPlan.user_id == user_id))
    ).scalars().all()
    if plan_ids:
        await db.execute(delete(MealPlan).where(MealPlan.id.in_(plan_ids)))

    await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
    await db.execute(delete(Notification).where(Notification.user_id == user_id))
    await db.execute(delete(PantryItem).where(PantryItem.user_id == user_id))
    await db.execute(delete(UserExclusion).where(UserExclusion.user_id == user_id))
    await db.execute(delete(Recipe).where(Recipe.user_id == user_id))
    await db.flush()


async def _seed_exclusions(db: AsyncSession, user_id: UUID) -> None:
    for name in ("peanuts", "shellfish", "dairy"):
        ing = await make_ingredient(db, name=name)
        await make_exclusion(db, user_id, name=name, ingredient_id=ing.id)


async def _seed_pantry(db: AsyncSession, user_id: UUID) -> None:
    items = [
        ("oats", "2", "cup", date.today() + timedelta(days=90)),
        ("cashew milk", "1", "L", date.today() + timedelta(days=7)),
        ("turmeric", "1", "jar", date.today() + timedelta(days=180)),
        ("spinach", "200", "g", date.today() + timedelta(days=4)),
        ("almond butter", "1", "jar", date.today() + timedelta(days=60)),
        ("quinoa", "500", "g", date.today() + timedelta(days=120)),
        ("cucumber", "3", "each", date.today() + timedelta(days=5)),
        ("celery", "1", "bunch", date.today() + timedelta(days=6)),
    ]
    for name, qty, unit, expires in items:
        ing = await make_ingredient(db, name=name)
        db.add(
            PantryItem(
                user_id=user_id,
                ingredient_id=ing.id,
                ingredient_name_raw=name,
                quantity=Decimal(qty) if qty.replace(".", "", 1).isdigit() else None,
                unit=unit,
                expires_at=expires,
                notes="Demo pantry stock",
            )
        )
    await db.flush()


async def _seed_recipes(db: AsyncSession, user_id: UUID) -> dict[str, Recipe]:
    specs: list[dict[str, Any]] = [
        {
            "key": "oats",
            "name": "Golden Turmeric Overnight Oats",
            "description": (
                "Steel-cut oats soaked overnight in turmeric-cashew milk, chia, and mango."
            ),
            "prep_method": PreparationType.RAW,
            "cooking_type": CookingType.RAW_100,
            "calories": 320,
            "protein_g": 12,
            "carbs_g": 48,
            "fat_g": 10,
            "fiber_g": 8,
            "prep_minutes": 10,
            "ingredients": ["oats", "cashew milk", "turmeric", "chia", "mango"],
            "steps": [
                {"step_number": 1, "instruction": "Stir oats into turmeric-cashew milk."},
                {"step_number": 2, "instruction": "Add chia; refrigerate overnight."},
                {"step_number": 3, "instruction": "Top with mango before serving."},
            ],
        },
        {
            "key": "pad_thai",
            "name": "Zucchini Pad Thai with Almond Sauce",
            "description": (
                "Spiralized zucchini noodles tossed in a raw almond-tamari sauce."
            ),
            "prep_method": PreparationType.RAW,
            "cooking_type": CookingType.RAW_100,
            "calories": 410,
            "protein_g": 18,
            "carbs_g": 42,
            "fat_g": 22,
            "fiber_g": 10,
            "prep_minutes": 15,
            "ingredients": ["zucchini", "almond butter", "tamari", "lime", "scallion"],
            "steps": [
                {"step_number": 1, "instruction": "Spiralize zucchini into noodles."},
                {"step_number": 2, "instruction": "Whisk almond butter, tamari, and lime."},
                {"step_number": 3, "instruction": "Toss and finish with scallion."},
            ],
        },
        {
            "key": "cauliflower",
            "name": "Miso-Glazed Roasted Cauliflower Steaks",
            "description": (
                "Thick cauliflower steaks roasted with a sweet miso glaze, served over quinoa."
            ),
            "prep_method": PreparationType.BAKED,
            "cooking_type": CookingType.COOKED_100,
            "calories": 480,
            "protein_g": 20,
            "carbs_g": 58,
            "fat_g": 18,
            "fiber_g": 12,
            "prep_minutes": 30,
            "ingredients": ["cauliflower", "miso", "quinoa", "maple syrup", "sesame"],
            "steps": [
                {"step_number": 1, "instruction": "Slice cauliflower into thick steaks."},
                {"step_number": 2, "instruction": "Brush with miso-maple glaze; roast 25 min."},
                {"step_number": 3, "instruction": "Serve over quinoa with sesame."},
            ],
        },
        {
            "key": "salad",
            "name": "Citrus Herb Chickpea Salad",
            "description": "Bright chickpeas with orange, herbs, and olive oil.",
            "prep_method": PreparationType.RAW,
            "cooking_type": CookingType.RAW_100,
            "calories": 380,
            "protein_g": 16,
            "carbs_g": 44,
            "fat_g": 14,
            "fiber_g": 11,
            "prep_minutes": 12,
            "ingredients": ["chickpeas", "orange", "parsley", "olive oil", "red onion"],
        },
        {
            "key": "smoothie",
            "name": "Spinach Mango Smoothie Bowl",
            "description": "Thick smoothie bowl with spinach, mango, and hemp seeds.",
            "prep_method": PreparationType.BLENDED,
            "cooking_type": CookingType.RAW_100,
            "recipe_type": RecipeType.SMOOTHIE,
            "calories": 290,
            "protein_g": 14,
            "carbs_g": 40,
            "fat_g": 10,
            "fiber_g": 7,
            "prep_minutes": 8,
            "ingredients": ["spinach", "mango", "hemp seeds", "banana", "cashew milk"],
        },
        {
            "key": "juice",
            "name": "Afternoon Green Renewal",
            "description": "Cucumber, celery, green apple, and mint.",
            "prep_method": PreparationType.JUICED,
            "cooking_type": CookingType.RAW_100,
            "recipe_type": RecipeType.JUICE,
            "calories": 90,
            "protein_g": 2,
            "carbs_g": 20,
            "fat_g": 0,
            "fiber_g": 3,
            "prep_minutes": 5,
            "ingredients": ["cucumber", "celery", "green apple", "mint"],
            "color": "#6FCF7B",
        },
    ]

    out: dict[str, Recipe] = {}
    for spec in specs:
        recipe = await make_recipe(
            db,
            user_id,
            name=spec["name"],
            recipe_type=spec.get("recipe_type", RecipeType.MEAL),
            cooking_type=spec["cooking_type"],
            prep_method=spec["prep_method"],
            calories=spec["calories"],
            protein_g=spec["protein_g"],
            carbs_g=spec["carbs_g"],
            fat_g=spec["fat_g"],
            fiber_g=spec["fiber_g"],
            ingredient_names=spec["ingredients"],
        )
        recipe.description = spec["description"]
        recipe.prep_minutes = spec["prep_minutes"]
        recipe.source = RecipeSource.MANUAL
        recipe.steps = spec.get(
            "steps",
            [{"step_number": 1, "instruction": "Combine and serve."}],
        )
        if "color" in spec:
            recipe.color = spec["color"]
        recipe.tags = ["demo"]
        out[spec["key"]] = recipe
    await db.flush()
    return out


def _monday_on_or_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def _link_recipes_across_plan(
    db: AsyncSession,
    plan: MealPlan,
    recipes: dict[str, Recipe],
) -> None:
    """Ensure B/L/D/juice items point at real recipes (shopping list needs recipe_id)."""
    days = (
        await db.execute(
            select(PlanDay)
            .where(PlanDay.plan_id == plan.id)
            .order_by(PlanDay.day_number.asc())
        )
    ).scalars().all()

    slot_recipe = {
        PlanSlot.BREAKFAST: recipes["oats"],
        PlanSlot.LUNCH: recipes["pad_thai"],
        PlanSlot.DINNER: recipes["cauliflower"],
        PlanSlot.JUICE: recipes["juice"],
    }
    slot_meta = {
        PlanSlot.BREAKFAST: (
            recipes["oats"].name,
            recipes["oats"].description,
            PlanItemSource.SAVED_RECIPE,
            PreparationType.RAW,
            10,
            320,
        ),
        PlanSlot.LUNCH: (
            recipes["pad_thai"].name,
            recipes["pad_thai"].description,
            PlanItemSource.SAVED_RECIPE,
            PreparationType.RAW,
            15,
            410,
        ),
        PlanSlot.DINNER: (
            recipes["cauliflower"].name,
            recipes["cauliflower"].description,
            PlanItemSource.SAVED_RECIPE,
            PreparationType.BAKED,
            30,
            480,
        ),
        PlanSlot.JUICE: (
            recipes["juice"].name,
            recipes["juice"].description,
            PlanItemSource.SAVED_RECIPE,
            PreparationType.JUICED,
            5,
            90,
        ),
    }

    for day in days:
        items = (
            await db.execute(select(PlanItem).where(PlanItem.plan_day_id == day.id))
        ).scalars().all()
        by_slot = {i.slot: i for i in items}
        for order, slot in enumerate(
            (PlanSlot.BREAKFAST, PlanSlot.LUNCH, PlanSlot.DINNER, PlanSlot.JUICE)
        ):
            recipe = slot_recipe[slot]
            name, desc, source, prep, mins, cal = slot_meta[slot]
            item = by_slot.get(slot)
            if item is None:
                item = PlanItem(
                    plan_day_id=day.id,
                    slot=slot,
                    slot_order=order,
                )
                db.add(item)
            item.recipe_id = recipe.id
            item.name = name
            item.description = desc
            item.recipe_type = recipe.recipe_type
            item.item_source = source
            item.prep_method = prep
            item.prep_minutes = mins
            item.calories = Decimal(str(cal))
            item.protein_g = Decimal("14" if slot != PlanSlot.JUICE else "2")
            item.carbs_g = Decimal("52" if slot != PlanSlot.JUICE else "20")
            item.fat_g = Decimal("16" if slot != PlanSlot.JUICE else "0")
            item.fiber_g = Decimal("8" if slot != PlanSlot.JUICE else "3")
            item.color = recipe.color
    await db.flush()


async def _seed_conversation(
    db: AsyncSession, user_id: UUID, plan_id: UUID
) -> Conversation:
    messages = [
        {
            "role": "user",
            "content": "<user_content>What's the plan look like for today?</user_content>",
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Today leans raw: turmeric oats, zucchini pad thai, and a green "
                        "juice in the afternoon. Dinner is the miso cauliflower if you "
                        "want something warm."
                    ),
                }
            ],
        },
        {
            "role": "user",
            "content": (
                "<user_content>Can you riff on my Zucchini Pad Thai with more "
                "protein?</user_content>"
            ),
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Easy lift: fold in hemp seeds and extra almond butter, or add "
                        "marinated tofu cubes. I can save a higher-protein variation "
                        "to your recipes when you're ready."
                    ),
                }
            ],
        },
    ]
    token = FieldEncryption().encrypt_json(json.dumps(messages))
    conversation = Conversation(
        user_id=user_id,
        plan_id=plan_id,
        messages=[{"_encrypted": True, "ciphertext": token}],
        tool_call_logs=[],
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def _seed_notifications(
    db: AsyncSession, user_id: UUID, plan_id: UUID
) -> None:
    db.add(
        Notification(
            user_id=user_id,
            type=NotificationType.PLAN_READY,
            title="Your demo plan is ready",
            body="Open the meal planner to review this week's meals.",
            data={"plan_id": str(plan_id)},
            is_read=False,
        )
    )
    db.add(
        Notification(
            user_id=user_id,
            type=NotificationType.SYSTEM,
            title="Welcome to Nouri",
            body="Demo data is loaded — explore plans, recipes, pantry, and chat.",
            data={},
            is_read=True,
        )
    )
    await db.flush()


async def seed(*, user_id: UUID, force: bool) -> dict[str, str]:
    async with async_session_factory() as db:
        await _ensure_auth_and_profile(db, user_id)

        existing_plans = (
            await db.execute(select(MealPlan).where(MealPlan.user_id == user_id))
        ).scalars().all()
        has_filled = False
        for plan in existing_plans:
            day = await db.execute(
                select(PlanDay.id).where(PlanDay.plan_id == plan.id).limit(1)
            )
            if day.scalar_one_or_none() is not None:
                has_filled = True
                break

        if has_filled and not force:
            await db.commit()
            approved = next(
                (p for p in existing_plans if p.status == PlanStatus.APPROVED),
                existing_plans[0],
            )
            return {
                "user_id": str(user_id),
                "approved_plan_id": str(approved.id),
                "reviewing_plan_id": str(existing_plans[0].id),
                "note": "Existing data kept. Re-run with --force to rebuild.",
            }

        if force or has_filled:
            await _clear_demo_rows(db, user_id)
            await _ensure_auth_and_profile(db, user_id)

        await _seed_exclusions(db, user_id)
        await _seed_pantry(db, user_id)
        recipes = await _seed_recipes(db, user_id)

        week_start = _monday_on_or_before(date.today())
        reviewing = await make_plan(
            db,
            user_id,
            num_days=7,
            status=PlanStatus.REVIEWING,
            week_start=week_start,
            recipe=recipes["oats"],
        )
        reviewing.title = DEMO_PLAN_REVIEWING_TITLE
        reviewing.scheduled_date = None
        reviewing.notes = "Demo reviewing plan for the meal planner UI."
        await _link_recipes_across_plan(db, reviewing, recipes)

        approved = await make_plan(
            db,
            user_id,
            num_days=7,
            status=PlanStatus.APPROVED,
            week_start=week_start,
            recipe=recipes["oats"],
        )
        approved.title = DEMO_PLAN_APPROVED_TITLE
        approved.scheduled_date = week_start
        approved.notes = "Demo approved plan for calendar, shopping, and chat today."
        await _link_recipes_across_plan(db, approved, recipes)

        await ShoppingListService().generate(approved.id, user_id, db)
        await _seed_conversation(db, user_id, approved.id)
        await _seed_notifications(db, user_id, reviewing.id)

        await db.commit()
        return {
            "user_id": str(user_id),
            "reviewing_plan_id": str(reviewing.id),
            "approved_plan_id": str(approved.id),
            "recipes": str(len(recipes)),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed full-UI demo data for one user")
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help=f"Supabase auth email (default: {DEFAULT_EMAIL})",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Supabase auth user UUID (skips email lookup)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Wipe this user's app data and reseed",
    )
    args = parser.parse_args()
    uid = asyncio.run(
        resolve_user_id(
            email=None if args.user_id else args.email,
            user_id=UUID(args.user_id) if args.user_id else None,
        )
    )
    result = asyncio.run(seed(user_id=uid, force=args.force))
    print("Seed complete:")
    for key, value in result.items():
        print(f"  {key}={value}")
    print(f"  meal planner → http://localhost:3000/plans/{result['reviewing_plan_id']}")
    print(f"  calendar/shopping → plan {result['approved_plan_id']}")


if __name__ == "__main__":
    main()
