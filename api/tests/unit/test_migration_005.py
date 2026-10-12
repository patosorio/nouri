"""Upgrade, re-upgrade, downgrade, and upgrade migration 005.

Skipped unless TEST_DATABASE_URL is set. It never points Alembic at the
application DATABASE_URL from settings. Start from revision 004 on a copy.
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
        pytest.skip("Set TEST_DATABASE_URL to a copy already at revision 004")
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


async def _llm_calls_rls(url: str) -> tuple[bool, bool]:
    import asyncpg

    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    connection = await asyncpg.connect(dsn)
    try:
        enabled = await connection.fetchval(
            """
            SELECT c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'llm_calls'
            """
        )
        policy = await connection.fetchval(
            """
            SELECT 1
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'llm_calls'
              AND policyname = 'llm_calls_select_own'
            """
        )
        return bool(enabled), policy is not None
    finally:
        await connection.close()


def test_migration_005_upgrade_downgrade_upgrade() -> None:
    url = _database_url()
    current = asyncio.run(_revision(url))
    if current != "004":
        pytest.fail(
            f"TEST_DATABASE_URL is at revision {current!r}; start from 004 "
            "on a database copy before this cycle"
        )

    _alembic(url, "upgrade", "005")
    assert asyncio.run(_revision(url)) == "005"
    assert asyncio.run(_llm_calls_rls(url)) == (True, True)

    # Run the upgrade body a second time against the objects it just created.
    _alembic(url, "stamp", "004")
    _alembic(url, "upgrade", "005")
    assert asyncio.run(_revision(url)) == "005"
    assert asyncio.run(_llm_calls_rls(url)) == (True, True)

    _alembic(url, "downgrade", "004")
    assert asyncio.run(_revision(url)) == "004"
    assert asyncio.run(_llm_calls_rls(url)) == (False, False)

    _alembic(url, "upgrade", "005")
    assert asyncio.run(_revision(url)) == "005"
    assert asyncio.run(_llm_calls_rls(url)) == (True, True)
