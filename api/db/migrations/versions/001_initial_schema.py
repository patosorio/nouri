"""Initial schema from docs/3_ERD.md §3–§4.

Revision ID: 001
Revises:
Create Date: 2026-07-22

RLS policies are intentionally omitted — applied in Supabase SQL editor.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Local Docker stub for Supabase auth.users (production: managed by Supabase)
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid()
        )
        """
    )

    # Enums — docs/3_ERD.md §3
    op.execute(
        """
        CREATE TYPE diet_type_enum AS ENUM (
            'vegan', 'plant_based', 'wfpb', 'pescatarian',
            'flexitarian', 'omnivore', 'no_pork'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE cooking_type_enum AS ENUM (
            'raw_100', 'raw_80_cooked_20', 'raw_70_cooked_30',
            'raw_50_cooked_50', 'cooked_100'
        )
        """
    )
    op.execute("CREATE TYPE user_tier_enum AS ENUM ('free', 'pro')")
    op.execute("CREATE TYPE recipe_type_enum AS ENUM ('meal', 'juice', 'smoothie')")
    op.execute(
        """
        CREATE TYPE preparation_type_enum AS ENUM (
            'raw', 'juiced', 'blended', 'dehydrated', 'sprouted',
            'fermented', 'steamed', 'baked', 'fried', 'boiled', 'pressure_cooked'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE recipe_source_enum AS ENUM (
            'ai_generated', 'manual', 'imported_image', 'imported_text'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE primary_protein_enum AS ENUM (
            'legumes', 'tofu_soy', 'nuts_seeds', 'eggs', 'dairy',
            'fish', 'poultry', 'red_meat', 'none'
        )
        """
    )
    op.execute(
        "CREATE TYPE meal_role_enum AS ENUM ('breakfast', 'lunch', 'dinner', 'snack')"
    )
    op.execute(
        "CREATE TYPE juice_style_enum AS ENUM ('juice', 'smoothie', 'tonic', 'shot')"
    )
    op.execute(
        """
        CREATE TYPE juice_color_enum AS ENUM (
            'green', 'orange', 'red', 'purple', 'yellow', 'brown', 'white'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE juice_size_enum AS ENUM (
            'shot_ml125', 'oz8_ml250', 'oz16_ml500', 'oz24_ml750', 'oz32_ml1000'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE recipe_usage_policy_enum AS ENUM (
            'prefer_saved', 'balanced', 'prefer_new'
        )
        """
    )
    op.execute(
        "CREATE TYPE plan_status_enum AS ENUM ('draft', 'reviewing', 'approved')"
    )
    op.execute(
        """
        CREATE TYPE plan_slot_enum AS ENUM (
            'breakfast', 'lunch', 'dinner', 'snack', 'juice',
            'extra_morning', 'extra_afternoon', 'extra_evening'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE plan_item_source_enum AS ENUM (
            'ai_generated', 'saved_recipe', 'shared_corpus'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE juice_time_enum AS ENUM (
            'morning', 'pre_lunch', 'lunch', 'afternoon',
            'evening', 'dinner', 'after_dinner'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE job_status_enum AS ENUM (
            'pending', 'running', 'completed', 'failed', 'cancelled'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE signal_type_enum AS ENUM (
            'liked', 'disliked', 'skipped', 'swapped', 'cooked', 'saved'
        )
        """
    )
    op.execute(
        "CREATE TYPE notification_type_enum AS ENUM ('plan_ready', 'plan_failed', 'system')"
    )

    # --- Tables (order respects FKs; circular meal_plans ↔ conversations deferred) ---

    op.execute(
        """
        CREATE TABLE user_profiles (
            id                          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
            display_name                TEXT,
            diet_type                   diet_type_enum NOT NULL DEFAULT 'vegan',
            diet_subtypes               TEXT[] NOT NULL DEFAULT '{}',
            cuisine_prefs               TEXT[] NOT NULL DEFAULT '{}',
            cooking_type                cooking_type_enum NOT NULL DEFAULT 'raw_50_cooked_50',
            calorie_target              INTEGER,
            protein_g_target            INTEGER,
            carbs_g_target              INTEGER,
            fat_g_target                INTEGER,
            fiber_g_target              INTEGER,
            recipe_usage_policy         recipe_usage_policy_enum NOT NULL DEFAULT 'balanced',
            juicing_enabled             BOOLEAN NOT NULL DEFAULT FALSE,
            tier                        user_tier_enum NOT NULL DEFAULT 'free',
            generation_credits_remaining INTEGER NOT NULL DEFAULT 10,
            free_text_preferences       TEXT,
            timezone                    TEXT NOT NULL DEFAULT 'UTC',
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE ingredients (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                TEXT NOT NULL,
            name_normalised     TEXT NOT NULL UNIQUE,
            default_unit        TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ingredient_name UNIQUE (name)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE user_exclusions (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
            ingredient_id       UUID REFERENCES ingredients(id) ON DELETE SET NULL,
            ingredient_name_raw TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_user_exclusion UNIQUE (user_id, ingredient_name_raw)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE pantry_items (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                 UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
            ingredient_id           UUID REFERENCES ingredients(id) ON DELETE SET NULL,
            ingredient_name_raw     TEXT NOT NULL,
            quantity                NUMERIC,
            unit                    TEXT,
            notes                   TEXT,
            expires_at              DATE,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE recipes (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
            name                TEXT NOT NULL,
            description         TEXT,
            recipe_type         recipe_type_enum NOT NULL DEFAULT 'meal',
            prep_method         preparation_type_enum,
            cooking_type        cooking_type_enum NOT NULL DEFAULT 'cooked_100',
            color               VARCHAR(7) CHECK (color ~ '^#[0-9a-fA-F]{6}$'),
            source              recipe_source_enum NOT NULL,
            servings            INTEGER NOT NULL DEFAULT 1,
            prep_minutes        INTEGER,
            cook_minutes        INTEGER,
            steps               JSONB NOT NULL DEFAULT '[]',
            diet_subtypes       TEXT[] NOT NULL DEFAULT '{}',
            cuisine             TEXT[] NOT NULL DEFAULT '{}',
            tags                TEXT[] NOT NULL DEFAULT '{}',
            deleted_at          TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE recipe_import_log (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            recipe_id           UUID NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            import_method       recipe_source_enum NOT NULL,
            source_url          TEXT,
            source_notes        TEXT,
            raw_input_text      TEXT,
            image_storage_path  TEXT,
            raw_ai_response     JSONB,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE recipe_diet_compatibility (
            recipe_id   UUID NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            diet_type   diet_type_enum NOT NULL,
            PRIMARY KEY (recipe_id, diet_type)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE recipe_meal_details (
            recipe_id               UUID PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
            primary_protein_source  primary_protein_enum NOT NULL DEFAULT 'none',
            meal_roles              meal_role_enum[] NOT NULL DEFAULT '{}'
        )
        """
    )

    op.execute(
        """
        CREATE TABLE recipe_juice_details (
            recipe_id       UUID PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
            juice_style     juice_style_enum NOT NULL DEFAULT 'juice',
            color           juice_color_enum,
            default_size    juice_size_enum NOT NULL DEFAULT 'oz16_ml500'
        )
        """
    )

    op.execute(
        """
        CREATE TABLE recipe_ingredients (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            recipe_id       UUID NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            ingredient_id   UUID NOT NULL REFERENCES ingredients(id),
            amount          NUMERIC NOT NULL,
            unit            TEXT NOT NULL,
            notes           TEXT,
            is_optional     BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order      INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    op.execute(
        """
        CREATE TABLE recipe_nutrition (
            recipe_id               UUID PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
            calories_per_serving    NUMERIC NOT NULL,
            protein_g               NUMERIC NOT NULL,
            carbs_g                 NUMERIC NOT NULL,
            fat_g                   NUMERIC NOT NULL,
            fiber_g                 NUMERIC NOT NULL,
            sat_fat_g               NUMERIC,
            sugar_g                 NUMERIC,
            nutritional_highlights  JSONB NOT NULL DEFAULT '[]',
            estimated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE recipe_embeddings (
            recipe_id       UUID PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
            embedding       VECTOR(1024) NOT NULL,
            model_version   TEXT NOT NULL DEFAULT 'voyage-3-lite',
            content_hash    TEXT NOT NULL,
            embedded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # meal_plans without conversation_id FK first (circular with conversations)
    op.execute(
        """
        CREATE TABLE meal_plans (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                     UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
            conversation_id             UUID,
            cloned_from_plan_id         UUID REFERENCES meal_plans(id) ON DELETE SET NULL,
            title                       TEXT,
            diet_type_snapshot          diet_type_enum NOT NULL,
            diet_subtypes_snapshot      TEXT[] NOT NULL DEFAULT '{}',
            cooking_type_snapshot       cooking_type_enum NOT NULL,
            calorie_target_snapshot     INTEGER,
            protein_g_target_snapshot   INTEGER,
            carbs_g_target_snapshot     INTEGER,
            fat_g_target_snapshot       INTEGER,
            fiber_g_target_snapshot     INTEGER,
            recipe_usage_policy         recipe_usage_policy_enum NOT NULL DEFAULT 'balanced',
            generation_params           JSONB NOT NULL DEFAULT '{}',
            status                      plan_status_enum NOT NULL DEFAULT 'draft',
            num_days                    INTEGER NOT NULL DEFAULT 7,
            week_start_date             DATE NOT NULL,
            scheduled_date              DATE,
            notes                       TEXT,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE conversations (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                 UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
            plan_id                 UUID REFERENCES meal_plans(id) ON DELETE SET NULL,
            messages                JSONB NOT NULL DEFAULT '[]',
            tool_call_logs          JSONB NOT NULL DEFAULT '[]',
            total_input_tokens      INTEGER NOT NULL DEFAULT 0,
            total_output_tokens     INTEGER NOT NULL DEFAULT 0,
            model_version           TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        ALTER TABLE meal_plans
            ADD CONSTRAINT fk_meal_plans_conversation_id
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
        """
    )

    op.execute(
        """
        CREATE TABLE plan_days (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id     UUID NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
            day_number  INTEGER NOT NULL CHECK (day_number >= 1 AND day_number <= 31),
            date        DATE,
            calories_actual     NUMERIC,
            protein_g_actual    NUMERIC,
            carbs_g_actual      NUMERIC,
            fat_g_actual        NUMERIC,
            fiber_g_actual      NUMERIC,
            calories_target     NUMERIC,
            protein_g_target    NUMERIC,
            carbs_g_target      NUMERIC,
            fat_g_target        NUMERIC,
            fiber_g_target      NUMERIC,
            CONSTRAINT uq_plan_day UNIQUE (plan_id, day_number)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE plan_items (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_day_id         UUID NOT NULL REFERENCES plan_days(id) ON DELETE CASCADE,
            slot                plan_slot_enum NOT NULL,
            slot_order          INTEGER NOT NULL DEFAULT 0,
            recipe_id           UUID REFERENCES recipes(id) ON DELETE SET NULL,
            item_source         plan_item_source_enum NOT NULL,
            name                TEXT NOT NULL,
            description         TEXT,
            recipe_type         recipe_type_enum NOT NULL DEFAULT 'meal',
            color               VARCHAR(7) CHECK (color ~ '^#[0-9a-fA-F]{6}$'),
            prep_method         preparation_type_enum,
            prep_minutes        INTEGER,
            calories            NUMERIC,
            protein_g           NUMERIC,
            carbs_g             NUMERIC,
            fat_g               NUMERIC,
            fiber_g             NUMERIC,
            is_flexible_repeat  BOOLEAN NOT NULL DEFAULT FALSE,
            notes               TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE juicing_config (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id     UUID NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
            label       TEXT NOT NULL,
            time_of_day juice_time_enum NOT NULL,
            size        juice_size_enum NOT NULL DEFAULT 'oz16_ml500',
            slot_order  INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT uq_juicing_config_plan_time UNIQUE (plan_id, time_of_day)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE shopping_list_items (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id                 UUID NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
            ingredient_id           UUID REFERENCES ingredients(id) ON DELETE SET NULL,
            ingredient_name_display TEXT NOT NULL,
            quantity_total          NUMERIC NOT NULL,
            unit                    TEXT NOT NULL,
            category                TEXT,
            is_checked              BOOLEAN NOT NULL DEFAULT FALSE,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE job_queue (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_type        TEXT NOT NULL,
            user_id         UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
            plan_id         UUID REFERENCES meal_plans(id) ON DELETE CASCADE,
            status          job_status_enum NOT NULL DEFAULT 'pending',
            payload         JSONB NOT NULL DEFAULT '{}',
            result          JSONB,
            error_message   TEXT,
            attempts        INTEGER NOT NULL DEFAULT 0,
            max_attempts    INTEGER NOT NULL DEFAULT 3,
            scheduled_for   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            claimed_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE notifications (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
            type        notification_type_enum NOT NULL,
            title       TEXT NOT NULL,
            body        TEXT,
            data        JSONB NOT NULL DEFAULT '{}',
            is_read     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE behavior_signals (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
            plan_item_id    UUID NOT NULL REFERENCES plan_items(id) ON DELETE CASCADE,
            signal_type     signal_type_enum NOT NULL,
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_signal UNIQUE (user_id, plan_item_id, signal_type)
        )
        """
    )

    # Indexes — docs/3_ERD.md §4.6 + §5
    op.execute(
        """
        CREATE INDEX recipe_embeddings_ivfflat_idx
            ON recipe_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """
    )
    op.execute(
        """
        CREATE INDEX job_queue_poll_idx ON job_queue (status, scheduled_for)
            WHERE status = 'pending'
        """
    )
    op.execute(
        """
        CREATE INDEX job_queue_reaper_idx ON job_queue (claimed_at)
            WHERE status = 'running'
        """
    )
    op.execute(
        """
        CREATE INDEX notifications_unread_idx ON notifications (user_id, is_read)
            WHERE is_read = FALSE
        """
    )
    op.execute("CREATE INDEX recipes_user_id_idx ON recipes (user_id)")
    op.execute(
        """
        CREATE INDEX recipes_user_id_active_idx ON recipes (user_id, deleted_at)
            WHERE deleted_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX recipe_ingredients_recipe_id_idx ON recipe_ingredients (recipe_id)"
    )
    op.execute(
        "CREATE INDEX recipe_ingredients_ingredient_id_idx ON recipe_ingredients (ingredient_id)"
    )
    op.execute(
        "CREATE INDEX ingredients_name_normalised_idx ON ingredients (name_normalised)"
    )
    op.execute(
        "CREATE INDEX recipe_import_log_recipe_id_idx ON recipe_import_log (recipe_id)"
    )
    op.execute(
        "CREATE INDEX meal_plans_user_id_status_idx ON meal_plans (user_id, status)"
    )
    op.execute(
        "CREATE INDEX meal_plans_user_id_scheduled_date_idx ON meal_plans (user_id, scheduled_date)"
    )
    op.execute("CREATE INDEX plan_days_plan_id_idx ON plan_days (plan_id)")
    op.execute(
        "CREATE INDEX plan_items_plan_day_id_slot_idx ON plan_items (plan_day_id, slot)"
    )
    op.execute(
        """
        CREATE INDEX plan_items_recipe_id_idx ON plan_items (recipe_id)
            WHERE recipe_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX behavior_signals_user_plan_item_idx ON behavior_signals (user_id, plan_item_id)"
    )
    op.execute("CREATE INDEX conversations_user_id_idx ON conversations (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS behavior_signals CASCADE")
    op.execute("DROP TABLE IF EXISTS notifications CASCADE")
    op.execute("DROP TABLE IF EXISTS job_queue CASCADE")
    op.execute("DROP TABLE IF EXISTS shopping_list_items CASCADE")
    op.execute("DROP TABLE IF EXISTS juicing_config CASCADE")
    op.execute("DROP TABLE IF EXISTS plan_items CASCADE")
    op.execute("DROP TABLE IF EXISTS plan_days CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
    op.execute("DROP TABLE IF EXISTS meal_plans CASCADE")
    op.execute("DROP TABLE IF EXISTS recipe_embeddings CASCADE")
    op.execute("DROP TABLE IF EXISTS recipe_nutrition CASCADE")
    op.execute("DROP TABLE IF EXISTS recipe_ingredients CASCADE")
    op.execute("DROP TABLE IF EXISTS recipe_juice_details CASCADE")
    op.execute("DROP TABLE IF EXISTS recipe_meal_details CASCADE")
    op.execute("DROP TABLE IF EXISTS recipe_diet_compatibility CASCADE")
    op.execute("DROP TABLE IF EXISTS recipe_import_log CASCADE")
    op.execute("DROP TABLE IF EXISTS recipes CASCADE")
    op.execute("DROP TABLE IF EXISTS pantry_items CASCADE")
    op.execute("DROP TABLE IF EXISTS user_exclusions CASCADE")
    op.execute("DROP TABLE IF EXISTS ingredients CASCADE")
    op.execute("DROP TABLE IF EXISTS user_profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS auth.users CASCADE")

    op.execute("DROP TYPE IF EXISTS notification_type_enum")
    op.execute("DROP TYPE IF EXISTS signal_type_enum")
    op.execute("DROP TYPE IF EXISTS job_status_enum")
    op.execute("DROP TYPE IF EXISTS juice_time_enum")
    op.execute("DROP TYPE IF EXISTS plan_item_source_enum")
    op.execute("DROP TYPE IF EXISTS plan_slot_enum")
    op.execute("DROP TYPE IF EXISTS plan_status_enum")
    op.execute("DROP TYPE IF EXISTS recipe_usage_policy_enum")
    op.execute("DROP TYPE IF EXISTS juice_size_enum")
    op.execute("DROP TYPE IF EXISTS juice_color_enum")
    op.execute("DROP TYPE IF EXISTS juice_style_enum")
    op.execute("DROP TYPE IF EXISTS meal_role_enum")
    op.execute("DROP TYPE IF EXISTS primary_protein_enum")
    op.execute("DROP TYPE IF EXISTS recipe_source_enum")
    op.execute("DROP TYPE IF EXISTS preparation_type_enum")
    op.execute("DROP TYPE IF EXISTS recipe_type_enum")
    op.execute("DROP TYPE IF EXISTS user_tier_enum")
    op.execute("DROP TYPE IF EXISTS cooking_type_enum")
    op.execute("DROP TYPE IF EXISTS diet_type_enum")

    op.execute("DROP EXTENSION IF EXISTS vector")
