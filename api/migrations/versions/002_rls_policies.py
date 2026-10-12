# Edited after apply on 2026-10-12 (HF3): only changes behaviour on fresh
# databases; already-migrated DBs are unaffected. Do not use as a precedent.
"""RLS policies from docs/3_ERD.md §4.6 / §6.

Local Compose uses table-owner `nouri`, which bypasses RLS. Policies apply
when the same schema is used by Supabase `authenticated` / `anon` roles.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    # Local stub only. Supabase already provides auth.uid(); replacing it
    # would change JWT behaviour on a hosted project.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_proc
            JOIN pg_namespace ON pg_namespace.oid = pg_proc.pronamespace
            WHERE pg_namespace.nspname = 'auth'
              AND pg_proc.proname = 'uid'
          ) THEN
            CREATE FUNCTION auth.uid()
            RETURNS uuid
            LANGUAGE sql
            STABLE
            AS $fn$
              SELECT NULLIF(
                current_setting('request.jwt.claim.sub', true), ''
              )::uuid;
            $fn$;
          END IF;
        END $$;
        """
    )

    owner = "user_id = auth.uid()"
    recipe_owned = (
        "EXISTS (SELECT 1 FROM recipes r "
        "WHERE r.id = recipe_id AND r.user_id = auth.uid())"
    )
    plan_owned = (
        "EXISTS (SELECT 1 FROM meal_plans mp "
        "WHERE mp.id = plan_id AND mp.user_id = auth.uid())"
    )
    plan_item_owned = (
        "EXISTS (SELECT 1 FROM plan_days pd "
        "JOIN meal_plans mp ON mp.id = pd.plan_id "
        "WHERE pd.id = plan_day_id AND mp.user_id = auth.uid())"
    )
    plan_day_owned = (
        "EXISTS (SELECT 1 FROM meal_plans mp "
        "WHERE mp.id = plan_id AND mp.user_id = auth.uid())"
    )

    _enable("user_profiles", "user_profiles_self", "id = auth.uid()")
    _enable("user_exclusions", "user_exclusions_owner", owner)
    _enable("pantry_items", "pantry_items_owner", owner)
    _enable("recipes", "recipes_owner", owner)
    _enable("recipe_import_log", "recipe_import_log_via_recipe", recipe_owned)
    _enable(
        "recipe_diet_compatibility",
        "recipe_diet_compatibility_via_recipe",
        recipe_owned,
    )
    _enable("recipe_meal_details", "recipe_meal_details_via_recipe", recipe_owned)
    _enable("recipe_juice_details", "recipe_juice_details_via_recipe", recipe_owned)
    _enable("recipe_ingredients", "recipe_ingredients_via_recipe", recipe_owned)
    _enable("recipe_nutrition", "recipe_nutrition_via_recipe", recipe_owned)
    _enable("recipe_embeddings", "recipe_embeddings_via_recipe", recipe_owned)
    _enable("meal_plans", "meal_plans_owner", owner)
    _enable("plan_days", "plan_days_via_plan", plan_day_owned)
    _enable("plan_items", "plan_items_via_plan", plan_item_owned)
    _enable("juicing_config", "juicing_config_via_plan", plan_owned)
    _enable("shopping_list_items", "shopping_list_items_via_plan", plan_owned)
    _enable("conversations", "conversations_owner", owner)
    _enable("notifications", "notifications_owner", owner)
    _enable("behavior_signals", "signals_owner", owner)

    op.execute("ALTER TABLE ingredients ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ingredients_read ON ingredients FOR SELECT USING (TRUE)"
    )

    op.execute("ALTER TABLE job_queue ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY job_queue_service_role ON job_queue "
        "USING (FALSE) WITH CHECK (FALSE)"
    )


def _enable(table: str, policy: str, using: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {policy} ON {table} USING ({using}) WITH CHECK ({using})"
    )


def downgrade() -> None:
    policies = (
        ("user_profiles", "user_profiles_self"),
        ("user_exclusions", "user_exclusions_owner"),
        ("pantry_items", "pantry_items_owner"),
        ("recipes", "recipes_owner"),
        ("recipe_import_log", "recipe_import_log_via_recipe"),
        ("recipe_diet_compatibility", "recipe_diet_compatibility_via_recipe"),
        ("recipe_meal_details", "recipe_meal_details_via_recipe"),
        ("recipe_juice_details", "recipe_juice_details_via_recipe"),
        ("recipe_ingredients", "recipe_ingredients_via_recipe"),
        ("recipe_nutrition", "recipe_nutrition_via_recipe"),
        ("recipe_embeddings", "recipe_embeddings_via_recipe"),
        ("meal_plans", "meal_plans_owner"),
        ("plan_days", "plan_days_via_plan"),
        ("plan_items", "plan_items_via_plan"),
        ("juicing_config", "juicing_config_via_plan"),
        ("shopping_list_items", "shopping_list_items_via_plan"),
        ("conversations", "conversations_owner"),
        ("notifications", "notifications_owner"),
        ("behavior_signals", "signals_owner"),
        ("ingredients", "ingredients_read"),
        ("job_queue", "job_queue_service_role"),
    )
    for table, policy in policies:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
