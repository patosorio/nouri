"""Job LLM checkpoint and per-call cost log.

Revision ID: 003
Revises: 002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE job_queue
            ADD COLUMN llm_output JSONB NULL,
            ADD COLUMN llm_output_saved_at TIMESTAMPTZ NULL
        """
    )
    op.execute(
        """
        CREATE TABLE llm_calls (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            user_id UUID NULL,
            job_id UUID NULL REFERENCES job_queue(id) ON DELETE SET NULL,
            task TEXT NOT NULL,
            model TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            outcome TEXT NOT NULL,
            http_status INTEGER NULL,
            latency_ms INTEGER NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_input_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd NUMERIC NULL,
            CONSTRAINT llm_calls_outcome_check CHECK (
                outcome IN (
                    'ok',
                    'http_error',
                    'timeout',
                    'parse_error',
                    'refused_budget'
                )
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX llm_calls_created_at_idx ON llm_calls (created_at)
        """
    )
    op.execute("ALTER TABLE llm_calls ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY llm_calls_service_role ON llm_calls "
        "USING (FALSE) WITH CHECK (FALSE)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS llm_calls_service_role ON llm_calls")
    op.execute("ALTER TABLE IF EXISTS llm_calls DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS llm_calls")
    op.execute("ALTER TABLE job_queue DROP COLUMN IF EXISTS llm_output_saved_at")
    op.execute("ALTER TABLE job_queue DROP COLUMN IF EXISTS llm_output")
