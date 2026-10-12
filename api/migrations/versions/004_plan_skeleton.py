"""Plan skeleton columns: smoothie slot, juice size, unknown nutrition.

Revision ID: 004
Revises: 003
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New enum value is not used again in this migration. The juice-field
    # check compares slot::text so it does not touch the new label.
    op.execute("ALTER TYPE plan_slot_enum ADD VALUE IF NOT EXISTS 'smoothie'")
    op.execute(
        """
        ALTER TABLE plan_items
            ADD COLUMN juice_time juice_time_enum NULL,
            ADD COLUMN juice_size_ml INTEGER NULL
                CHECK (juice_size_ml > 0 AND juice_size_ml <= 1000),
            ADD COLUMN nutrition_unknown BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        ALTER TABLE plan_items
            ADD CONSTRAINT ck_plan_items_juice_fields CHECK (
                (juice_time IS NULL AND juice_size_ml IS NULL)
                OR slot::text IN ('juice', 'smoothie')
            )
        """
    )
    op.execute(
        """
        ALTER TABLE plan_days
            ADD COLUMN totals_incomplete BOOLEAN NOT NULL DEFAULT FALSE
        """
    )


def downgrade() -> None:
    # Postgres can't drop an enum value, and IF NOT EXISTS makes re-upgrade safe.
    # 'smoothie' stays in plan_slot_enum.
    op.execute(
        "ALTER TABLE plan_items DROP CONSTRAINT IF EXISTS ck_plan_items_juice_fields"
    )
    op.execute(
        "UPDATE plan_items SET slot = 'juice' WHERE slot::text = 'smoothie'"
    )
    op.execute("ALTER TABLE plan_items DROP COLUMN IF EXISTS nutrition_unknown")
    op.execute("ALTER TABLE plan_items DROP COLUMN IF EXISTS juice_size_ml")
    op.execute("ALTER TABLE plan_items DROP COLUMN IF EXISTS juice_time")
    op.execute("ALTER TABLE plan_days DROP COLUMN IF EXISTS totals_incomplete")
