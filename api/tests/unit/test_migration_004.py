"""Upgrade, downgrade, and re-upgrade migration 004 on TEST_DATABASE_URL only.

Patricia runs this. It is skipped unless TEST_DATABASE_URL is set, and it never
points Alembic at the application DATABASE_URL from settings.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = API_ROOT / "db" / "migrations" / "alembic.ini"


def _database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a copy already at revision 003")
    if not url.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must be a Postgres URL")
    return url


def _alembic(url: str, *args: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed\n{completed.stdout}\n{completed.stderr}"
        )


async def _revision(url: str) -> str | None:
    import asyncpg

    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    connection = await asyncpg.connect(dsn)
    try:
        return await connection.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await connection.close()


async def _columns(url: str) -> set[tuple[str, str]]:
    import asyncpg

    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    connection = await asyncpg.connect(dsn)
    try:
        rows = await connection.fetch(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_name IN ('plan_items', 'plan_days')
              AND column_name IN (
                  'juice_time', 'juice_size_ml', 'nutrition_unknown', 'totals_incomplete'
              )
            """
        )
        return {(row["table_name"], row["column_name"]) for row in rows}
    finally:
        await connection.close()


def test_migration_004_upgrade_downgrade_upgrade() -> None:
    url = _database_url()
    current = asyncio.run(_revision(url))
    if current != "003":
        pytest.fail(
            f"TEST_DATABASE_URL is at revision {current!r}; start from 003 "
            "on a database copy before this cycle"
        )

    _alembic(url, "upgrade", "004")
    assert asyncio.run(_revision(url)) == "004"
    upgraded = asyncio.run(_columns(url))
    assert upgraded == {
        ("plan_items", "juice_time"),
        ("plan_items", "juice_size_ml"),
        ("plan_items", "nutrition_unknown"),
        ("plan_days", "totals_incomplete"),
    }

    _alembic(url, "downgrade", "003")
    assert asyncio.run(_revision(url)) == "003"
    assert asyncio.run(_columns(url)) == set()

    _alembic(url, "upgrade", "004")
    assert asyncio.run(_revision(url)) == "004"
    assert asyncio.run(_columns(url)) == upgraded
