"""RLS for llm_calls, and Stripe webhook idempotency.

Revision ID: 005
Revises: 004

llm_calls was created without a working policy: 003 enabled RLS and added
llm_calls_service_role, then that migration was edited after it had been
applied, so the live table has relrowsecurity = false and no policy.
This migration does not edit 003.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_calls ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'llm_calls'
              AND policyname = 'llm_calls_select_own'
          ) THEN
            CREATE POLICY llm_calls_select_own ON llm_calls
              FOR SELECT
              USING (user_id = auth.uid());
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_stripe_events (
            event_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "ALTER TABLE processed_stripe_events ENABLE ROW LEVEL SECURITY"
    )
    # No existing column stores the subscription ordering watermark.
    op.execute(
        """
        ALTER TABLE user_profiles
            ADD COLUMN IF NOT EXISTS stripe_subscription_event_at TIMESTAMPTZ NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_profiles DROP COLUMN IF EXISTS stripe_subscription_event_at"
    )
    op.execute("DROP TABLE IF EXISTS processed_stripe_events")
    op.execute("DROP POLICY IF EXISTS llm_calls_select_own ON llm_calls")
    op.execute("ALTER TABLE llm_calls DISABLE ROW LEVEL SECURITY")
