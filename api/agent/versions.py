"""Versions stamped on every plan job. No migration: existing JSONB columns."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from config import AgentTask, route_model

_CODE_HASH_SKIP = frozenset({".venv", "tests", "__pycache__"})


def _compute_code_version() -> str:
    """Git short sha, plus -dirty when the tree is dirty.

    GIT_SHA is the fallback when git is not reachable. Otherwise "unknown".
    Computed once at import.
    """
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        rev = None
        status = None
    if rev is not None and rev.returncode == 0 and rev.stdout.strip():
        sha = rev.stdout.strip()
        dirty = (
            status is not None
            and status.returncode == 0
            and bool(status.stdout.strip())
        )
        return f"{sha}-dirty" if dirty else sha
    configured = os.environ.get("GIT_SHA", "").strip()
    return configured or "unknown"


def _compute_code_hash(root: Path | None = None) -> str:
    """First 12 hex chars of sha256 over sorted api/**/*.py path and contents.

    Skips .venv, tests, and __pycache__. Computed once at import.
    """
    base = (
        root if root is not None else Path(__file__).resolve().parent.parent
    ).resolve()
    rows: list[tuple[str, bytes]] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(
            name for name in dirnames if name not in _CODE_HASH_SKIP
        )
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = Path(dirpath) / filename
            rel = path.relative_to(base).as_posix()
            rows.append((rel, path.read_bytes()))
    rows.sort()
    digest = hashlib.sha256()
    for rel, contents in rows:
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(contents)
        digest.update(b"\0")
    return digest.hexdigest()[:12]


CODE_VERSION = _compute_code_version()
CODE_HASH = _compute_code_hash()

_SCHEMA_VERSION: str | None = None


def prompt_version(system_prompt: str) -> str:
    """First 12 hex chars of the plan system prompt."""
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:12]


def schema_version() -> str:
    """First 12 hex chars of the output_plan schema JSON (sort_keys)."""
    global _SCHEMA_VERSION
    if _SCHEMA_VERSION is None:
        from agent.plan_generator import _plan_output_schema

        encoded = json.dumps(_plan_output_schema(), sort_keys=True, separators=(",", ":"))
        _SCHEMA_VERSION = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]
    return _SCHEMA_VERSION


def plan_versions(system_prompt: str) -> dict[str, str]:
    return {
        "code_version": CODE_VERSION,
        "code_hash": CODE_HASH,
        "prompt_version": prompt_version(system_prompt),
        "schema_version": schema_version(),
        "model": route_model(AgentTask.PLAN_GENERATION),
    }
