"""002 must not replace or drop Supabase's auth.uid()."""

from __future__ import annotations

from pathlib import Path

_SOURCE = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "002_rls_policies.py"
)


def test_migration_002_does_not_replace_or_drop_auth_uid() -> None:
    source = _SOURCE.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION auth.uid" not in source
    for line in source.splitlines():
        if "DROP FUNCTION" in line:
            assert "auth.uid" not in line
