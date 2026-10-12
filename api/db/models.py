"""SQLAlchemy ORM models mirroring docs/3_ERD.md §3–§4."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums — exact values from docs/3_ERD.md §3
# ---------------------------------------------------------------------------


class DietType(str, enum.Enum):
    VEGAN = "vegan"
    PLANT_BASED = "plant_based"
    WFPB = "wfpb"
    PESCATARIAN = "pescatarian"
    FLEXITARIAN = "flexitarian"
    OMNIVORE = "omnivore"
    NO_PORK = "no_pork"


class CookingType(str, enum.Enum):
    RAW_100 = "raw_100"
    RAW_80_COOKED_20 = "raw_80_cooked_20"
    RAW_70_COOKED_30 = "raw_70_cooked_30"
    RAW_50_COOKED_50 = "raw_50_cooked_50"
    COOKED_100 = "cooked_100"


class UserTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"


class RecipeType(str, enum.Enum):
    MEAL = "meal"
    JUICE = "juice"
    SMOOTHIE = "smoothie"


class PreparationType(str, enum.Enum):
    RAW = "raw"
    JUICED = "juiced"
    BLENDED = "blended"
    DEHYDRATED = "dehydrated"
    SPROUTED = "sprouted"
    FERMENTED = "fermented"
    STEAMED = "steamed"
    BAKED = "baked"
    FRIED = "fried"
    BOILED = "boiled"
    PRESSURE_COOKED = "pressure_cooked"


class RecipeSource(str, enum.Enum):
    AI_GENERATED = "ai_generated"
    MANUAL = "manual"
    IMPORTED_IMAGE = "imported_image"
    IMPORTED_TEXT = "imported_text"


class PrimaryProtein(str, enum.Enum):
    LEGUMES = "legumes"
    TOFU_SOY = "tofu_soy"
    NUTS_SEEDS = "nuts_seeds"
    EGGS = "eggs"
    DAIRY = "dairy"
    FISH = "fish"
    POULTRY = "poultry"
    RED_MEAT = "red_meat"
    NONE = "none"


class MealRole(str, enum.Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class JuiceStyle(str, enum.Enum):
    JUICE = "juice"
    SMOOTHIE = "smoothie"
    TONIC = "tonic"
    SHOT = "shot"


class JuiceColor(str, enum.Enum):
    GREEN = "green"
    ORANGE = "orange"
    RED = "red"
    PURPLE = "purple"
    YELLOW = "yellow"
    BROWN = "brown"
    WHITE = "white"


class JuiceSize(str, enum.Enum):
    SHOT_ML125 = "shot_ml125"
    OZ8_ML250 = "oz8_ml250"
    OZ16_ML500 = "oz16_ml500"
    OZ24_ML750 = "oz24_ml750"
    OZ32_ML1000 = "oz32_ml1000"


class RecipeUsagePolicy(str, enum.Enum):
    PREFER_SAVED = "prefer_saved"
    BALANCED = "balanced"
    PREFER_NEW = "prefer_new"


class PlanStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    APPROVED = "approved"


class PlanSlot(str, enum.Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    JUICE = "juice"
    SMOOTHIE = "smoothie"
    EXTRA_MORNING = "extra_morning"
    EXTRA_AFTERNOON = "extra_afternoon"
    EXTRA_EVENING = "extra_evening"


class PlanItemSource(str, enum.Enum):
    AI_GENERATED = "ai_generated"
    SAVED_RECIPE = "saved_recipe"
    SHARED_CORPUS = "shared_corpus"


class JuiceTime(str, enum.Enum):
    MORNING = "morning"
    PRE_LUNCH = "pre_lunch"
    LUNCH = "lunch"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    DINNER = "dinner"
    AFTER_DINNER = "after_dinner"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SignalType(str, enum.Enum):
    LIKED = "liked"
    DISLIKED = "disliked"
    SKIPPED = "skipped"
    SWAPPED = "swapped"
    COOKED = "cooked"
    SAVED = "saved"


class NotificationType(str, enum.Enum):
    PLAN_READY = "plan_ready"
    PLAN_FAILED = "plan_failed"
    SYSTEM = "system"


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda x: [e.value for e in x],
    )


# ---------------------------------------------------------------------------
# Auth schema — minimal mapping to Supabase auth.users
# ---------------------------------------------------------------------------


class AuthUser(Base):
    """Maps to Supabase auth.users. Local Docker creates a stub table for FKs."""

    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )


# ---------------------------------------------------------------------------
# User domain
# ---------------------------------------------------------------------------


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[UUID] = mapped_column(
        ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str | None] = mapped_column(Text)
    diet_type: Mapped[DietType] = mapped_column(
        _pg_enum(DietType, "diet_type_enum"),
        nullable=False,
        server_default=text("'vegan'"),
    )
    diet_subtypes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    cuisine_prefs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    cooking_type: Mapped[CookingType] = mapped_column(
        _pg_enum(CookingType, "cooking_type_enum"),
        nullable=False,
        server_default=text("'raw_50_cooked_50'"),
    )
    calorie_target: Mapped[int | None] = mapped_column(Integer)
    protein_g_target: Mapped[int | None] = mapped_column(Integer)
    carbs_g_target: Mapped[int | None] = mapped_column(Integer)
    fat_g_target: Mapped[int | None] = mapped_column(Integer)
    fiber_g_target: Mapped[int | None] = mapped_column(Integer)
    recipe_usage_policy: Mapped[RecipeUsagePolicy] = mapped_column(
        _pg_enum(RecipeUsagePolicy, "recipe_usage_policy_enum"),
        nullable=False,
        server_default=text("'balanced'"),
    )
    juicing_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    tier: Mapped[UserTier] = mapped_column(
        _pg_enum(UserTier, "user_tier_enum"),
        nullable=False,
        server_default=text("'free'"),
    )
    # Watermark for Stripe subscription events (migration 005). Not in the ERD.
    stripe_subscription_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    generation_credits_remaining: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10")
    )
    free_text_preferences: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'UTC'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class Ingredient(Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        UniqueConstraint("name", name="uq_ingredient_name"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalised: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    default_unit: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class UserExclusion(Base):
    __tablename__ = "user_exclusions"
    __table_args__ = (
        UniqueConstraint("user_id", "ingredient_name_raw", name="uq_user_exclusion"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="SET NULL")
    )
    ingredient_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class PantryItem(Base):
    __tablename__ = "pantry_items"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="SET NULL")
    )
    ingredient_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


# ---------------------------------------------------------------------------
# Recipe domain
# ---------------------------------------------------------------------------


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'",
            name="ck_recipes_color_hex",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    recipe_type: Mapped[RecipeType] = mapped_column(
        _pg_enum(RecipeType, "recipe_type_enum"),
        nullable=False,
        server_default=text("'meal'"),
    )
    prep_method: Mapped[PreparationType | None] = mapped_column(
        _pg_enum(PreparationType, "preparation_type_enum")
    )
    cooking_type: Mapped[CookingType] = mapped_column(
        _pg_enum(CookingType, "cooking_type_enum"),
        nullable=False,
        server_default=text("'cooked_100'"),
    )
    color: Mapped[str | None] = mapped_column(String(7))
    source: Mapped[RecipeSource] = mapped_column(
        _pg_enum(RecipeSource, "recipe_source_enum"), nullable=False
    )
    servings: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    prep_minutes: Mapped[int | None] = mapped_column(Integer)
    cook_minutes: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    diet_subtypes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    cuisine: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class RecipeImportLog(Base):
    __tablename__ = "recipe_import_log"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    recipe_id: Mapped[UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    import_method: Mapped[RecipeSource] = mapped_column(
        _pg_enum(RecipeSource, "recipe_source_enum"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    source_notes: Mapped[str | None] = mapped_column(Text)
    raw_input_text: Mapped[str | None] = mapped_column(Text)
    image_storage_path: Mapped[str | None] = mapped_column(Text)
    raw_ai_response: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RecipeDietCompatibility(Base):
    __tablename__ = "recipe_diet_compatibility"
    __table_args__ = (
        PrimaryKeyConstraint("recipe_id", "diet_type"),
    )

    recipe_id: Mapped[UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    diet_type: Mapped[DietType] = mapped_column(
        _pg_enum(DietType, "diet_type_enum"), nullable=False
    )


class RecipeMealDetails(Base):
    __tablename__ = "recipe_meal_details"

    recipe_id: Mapped[UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    primary_protein_source: Mapped[PrimaryProtein] = mapped_column(
        _pg_enum(PrimaryProtein, "primary_protein_enum"),
        nullable=False,
        server_default=text("'none'"),
    )
    meal_roles: Mapped[list[MealRole]] = mapped_column(
        ARRAY(_pg_enum(MealRole, "meal_role_enum")),
        nullable=False,
        server_default=text("'{}'"),
    )


class RecipeJuiceDetails(Base):
    __tablename__ = "recipe_juice_details"

    recipe_id: Mapped[UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    juice_style: Mapped[JuiceStyle] = mapped_column(
        _pg_enum(JuiceStyle, "juice_style_enum"),
        nullable=False,
        server_default=text("'juice'"),
    )
    color: Mapped[JuiceColor | None] = mapped_column(
        _pg_enum(JuiceColor, "juice_color_enum")
    )
    default_size: Mapped[JuiceSize] = mapped_column(
        _pg_enum(JuiceSize, "juice_size_enum"),
        nullable=False,
        server_default=text("'oz16_ml500'"),
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    recipe_id: Mapped[UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingredients.id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_optional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class RecipeNutrition(Base):
    __tablename__ = "recipe_nutrition"

    recipe_id: Mapped[UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    calories_per_serving: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    carbs_g: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    fiber_g: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    sat_fat_g: Mapped[Decimal | None] = mapped_column(Numeric)
    sugar_g: Mapped[Decimal | None] = mapped_column(Numeric)
    nutritional_highlights: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    estimated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RecipeEmbedding(Base):
    __tablename__ = "recipe_embeddings"

    recipe_id: Mapped[UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    model_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'voyage-3-lite'")
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


# ---------------------------------------------------------------------------
# Planning domain
# ---------------------------------------------------------------------------


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    # Circular FK with conversations — constraint added in migration after both tables exist
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL", use_alter=True, name="fk_meal_plans_conversation_id")
    )
    cloned_from_plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("meal_plans.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(Text)
    diet_type_snapshot: Mapped[DietType] = mapped_column(
        _pg_enum(DietType, "diet_type_enum"), nullable=False
    )
    diet_subtypes_snapshot: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    cooking_type_snapshot: Mapped[CookingType] = mapped_column(
        _pg_enum(CookingType, "cooking_type_enum"), nullable=False
    )
    calorie_target_snapshot: Mapped[int | None] = mapped_column(Integer)
    protein_g_target_snapshot: Mapped[int | None] = mapped_column(Integer)
    carbs_g_target_snapshot: Mapped[int | None] = mapped_column(Integer)
    fat_g_target_snapshot: Mapped[int | None] = mapped_column(Integer)
    fiber_g_target_snapshot: Mapped[int | None] = mapped_column(Integer)
    recipe_usage_policy: Mapped[RecipeUsagePolicy] = mapped_column(
        _pg_enum(RecipeUsagePolicy, "recipe_usage_policy_enum"),
        nullable=False,
        server_default=text("'balanced'"),
    )
    generation_params: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[PlanStatus] = mapped_column(
        _pg_enum(PlanStatus, "plan_status_enum"),
        nullable=False,
        server_default=text("'draft'"),
    )
    num_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("7")
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class PlanDay(Base):
    __tablename__ = "plan_days"
    __table_args__ = (
        UniqueConstraint("plan_id", "day_number", name="uq_plan_day"),
        CheckConstraint(
            "day_number >= 1 AND day_number <= 31", name="ck_plan_days_day_number"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date | None] = mapped_column(Date)
    calories_actual: Mapped[Decimal | None] = mapped_column(Numeric)
    protein_g_actual: Mapped[Decimal | None] = mapped_column(Numeric)
    carbs_g_actual: Mapped[Decimal | None] = mapped_column(Numeric)
    fat_g_actual: Mapped[Decimal | None] = mapped_column(Numeric)
    fiber_g_actual: Mapped[Decimal | None] = mapped_column(Numeric)
    calories_target: Mapped[Decimal | None] = mapped_column(Numeric)
    protein_g_target: Mapped[Decimal | None] = mapped_column(Numeric)
    carbs_g_target: Mapped[Decimal | None] = mapped_column(Numeric)
    fat_g_target: Mapped[Decimal | None] = mapped_column(Numeric)
    fiber_g_target: Mapped[Decimal | None] = mapped_column(Numeric)
    totals_incomplete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'",
            name="ck_plan_items_color_hex",
        ),
        CheckConstraint(
            "(juice_time IS NULL AND juice_size_ml IS NULL) "
            "OR slot::text IN ('juice', 'smoothie')",
            name="ck_plan_items_juice_fields",
        ),
        CheckConstraint(
            "juice_size_ml > 0 AND juice_size_ml <= 1000",
            name="plan_items_juice_size_ml_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    plan_day_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_days.id", ondelete="CASCADE"), nullable=False
    )
    slot: Mapped[PlanSlot] = mapped_column(
        _pg_enum(PlanSlot, "plan_slot_enum"), nullable=False
    )
    slot_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    recipe_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL")
    )
    item_source: Mapped[PlanItemSource] = mapped_column(
        _pg_enum(PlanItemSource, "plan_item_source_enum"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    recipe_type: Mapped[RecipeType] = mapped_column(
        _pg_enum(RecipeType, "recipe_type_enum"),
        nullable=False,
        server_default=text("'meal'"),
    )
    color: Mapped[str | None] = mapped_column(String(7))
    prep_method: Mapped[PreparationType | None] = mapped_column(
        _pg_enum(PreparationType, "preparation_type_enum")
    )
    prep_minutes: Mapped[int | None] = mapped_column(Integer)
    calories: Mapped[Decimal | None] = mapped_column(Numeric)
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric)
    carbs_g: Mapped[Decimal | None] = mapped_column(Numeric)
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric)
    fiber_g: Mapped[Decimal | None] = mapped_column(Numeric)
    is_flexible_repeat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    juice_time: Mapped[JuiceTime | None] = mapped_column(
        _pg_enum(JuiceTime, "juice_time_enum")
    )
    juice_size_ml: Mapped[int | None] = mapped_column(Integer)
    nutrition_unknown: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class JuicingConfig(Base):
    __tablename__ = "juicing_config"
    __table_args__ = (
        UniqueConstraint("plan_id", "time_of_day", name="uq_juicing_config_plan_time"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    time_of_day: Mapped[JuiceTime] = mapped_column(
        _pg_enum(JuiceTime, "juice_time_enum"), nullable=False
    )
    size: Mapped[JuiceSize] = mapped_column(
        _pg_enum(JuiceSize, "juice_size_enum"),
        nullable=False,
        server_default=text("'oz16_ml500'"),
    )
    slot_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


# ---------------------------------------------------------------------------
# Shopping / conversations / jobs / notifications / signals
# ---------------------------------------------------------------------------


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="SET NULL")
    )
    ingredient_name_display: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_total: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    is_checked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("meal_plans.id", ondelete="SET NULL", use_alter=True, name="fk_conversations_plan_id")
    )
    messages: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    tool_call_logs: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    total_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    total_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    model_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'claude-sonnet-4-6'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class JobQueue(Base):
    __tablename__ = "job_queue"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("meal_plans.id", ondelete="CASCADE")
    )
    status: Mapped[JobStatus] = mapped_column(
        _pg_enum(JobStatus, "job_status_enum"),
        nullable=False,
        server_default=text("'pending'"),
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    # Parsed output_plan tool input, committed before any plan writes so a
    # later attempt can rebuild the plan without another model call.
    llm_output: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    llm_output_saved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3")
    )
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(
        _pg_enum(NotificationType, "notification_type_enum"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class BehaviorSignal(Base):
    __tablename__ = "behavior_signals"
    __table_args__ = (
        UniqueConstraint("user_id", "plan_item_id", "signal_type", name="uq_signal"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    plan_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_items.id", ondelete="CASCADE"), nullable=False
    )
    signal_type: Mapped[SignalType] = mapped_column(
        _pg_enum(SignalType, "signal_type_enum"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ("
            "'ok', 'http_error', 'timeout', 'parse_error', 'refused_budget'"
            ")",
            name="llm_calls_outcome_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_queue.id", ondelete="SET NULL")
    )
    task: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cache_creation_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cache_read_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric)


class ProcessedStripeEvent(Base):
    """Stripe event ids already accepted. Service role only; RLS with no policies."""

    __tablename__ = "processed_stripe_events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
