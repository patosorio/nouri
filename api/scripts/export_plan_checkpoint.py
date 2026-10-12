"""Export a plan-generation checkpoint for replay tests. Read-only.

No model calls. Commit nothing.

    cd api && python -m scripts.export_plan_checkpoint \
        --job-prefix bfb0ddf0 --out tests/fixtures/plan_replay/bfb0ddf0.json
    cd api && python -m scripts.export_plan_checkpoint \
        --latest --out tests/fixtures/plan_replay/latest.json

Jobs:
  bfb0ddf0 — today's 3-day pescatarian plan, juicing on
             (morning 500 ml, pre_lunch 250 ml).
  --latest — newest meal_plans row.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from db.models import JobQueue, JuicingConfig, MealPlan, Recipe, RecipeMealDetails
from db.session import async_session_factory
from planning.skeleton import JUICE_SIZE_ML
from preprocessing.notes_preprocessor import NotesPreprocessor, RecipeTitleRef
from services.recipe_service import RecipeService
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DROP_KEYS = frozenset({"user_id", "email"})
_PREFIX = re.compile(r"^[0-9a-fA-F]{8}$")


def scrub(value: Any) -> Any:
    """Drop user ids and email addresses. Everything else is kept."""
    if isinstance(value, dict):
        return {
            key: scrub(item)
            for key, item in value.items()
            if key not in _DROP_KEYS
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return _EMAIL.sub("[redacted]", value)
    return value


async def export_checkpoint(
    db: AsyncSession,
    *,
    job_prefix: str | None,
    latest: bool,
) -> dict[str, Any]:
    job = await _find_job(db, job_prefix=job_prefix, latest=latest)
    if job.plan_id is None:
        raise SystemExit(f"Job {job.id} has no plan_id")
    plan = await db.get(MealPlan, job.plan_id)
    if plan is None:
        raise SystemExit(f"Plan {job.plan_id} was not found")

    payload = dict(job.payload or {})
    raw_params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    params = dict(raw_params)
    llm_output = _llm_output(job.llm_output)
    await _fill_layout_maps(db, llm_output)
    juicing = await _juicing_rows(db, plan.id)
    pins = await _pins(db, plan, params)
    snapshots = await _snapshots(db, plan.user_id, llm_output)
    include_juicing = bool(params.get("include_juicing"))
    duration_days = int(params.get("duration_days") or plan.num_days)

    return scrub(
        {
            "job_id": str(job.id),
            "llm_output": llm_output,
            "plan_params": {
                "duration_days": duration_days,
                "diet_type": params.get("diet_type") or _enum(plan.diet_type_snapshot),
                "cooking_type": params.get("cooking_type")
                or _enum(plan.cooking_type_snapshot),
                "calorie_target": params.get("calorie_target", plan.calorie_target_snapshot),
                "sourcing_policy": params.get("sourcing_policy")
                or _enum(plan.recipe_usage_policy),
                "include_juicing": include_juicing,
                "notes": params.get("notes"),
                "week_start_date": (
                    params.get("week_start_date") or plan.week_start_date.isoformat()
                ),
            },
            "skeleton_inputs": {
                "duration_days": duration_days,
                "include_juicing": include_juicing,
                "juicing_config": juicing,
                "pins": pins,
            },
            "snapshots": snapshots,
        }
    )


async def _find_job(
    db: AsyncSession,
    *,
    job_prefix: str | None,
    latest: bool,
) -> JobQueue:
    if latest:
        plan_row = await db.execute(
            select(MealPlan.id).order_by(MealPlan.created_at.desc()).limit(1)
        )
        plan_id = plan_row.scalar_one_or_none()
        if plan_id is None:
            raise SystemExit("No meal_plans rows")
        job_row = await db.execute(
            select(JobQueue)
            .where(
                JobQueue.plan_id == plan_id,
                JobQueue.llm_output.is_not(None),
            )
            .order_by(JobQueue.created_at.desc())
            .limit(1)
        )
        job = job_row.scalar_one_or_none()
        if job is None:
            raise SystemExit(f"Newest plan {plan_id} has no checkpoint")
        return job

    if job_prefix is None or _PREFIX.fullmatch(job_prefix) is None:
        raise SystemExit("--job-prefix must be 8 hex characters")
    rows = await db.execute(
        text("SELECT id FROM job_queue WHERE id::text LIKE :prefix"),
        {"prefix": f"{job_prefix.lower()}%"},
    )
    ids = [row[0] for row in rows.all()]
    if len(ids) == 0:
        raise SystemExit(f"No job matches prefix {job_prefix}")
    if len(ids) > 1:
        raise SystemExit(
            f"Prefix {job_prefix} matched {len(ids)} jobs; need exactly one"
        )
    job = await db.get(JobQueue, ids[0] if isinstance(ids[0], UUID) else UUID(str(ids[0])))
    if job is None:
        raise SystemExit(f"Job {ids[0]} disappeared")
    if job.llm_output is None:
        raise SystemExit(f"Job {job.id} has no llm_output")
    return job


def _llm_output(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SystemExit("llm_output is not an object")
    saved: dict[str, Any] = {}
    output = raw.get("output")
    handles = raw.get("handles")
    if not isinstance(output, dict) or not isinstance(handles, dict):
        raise SystemExit("llm_output is missing output or handles")
    saved["output"] = output
    saved["handles"] = handles
    for key in ("roles", "titles", "types"):
        value = raw.get(key)
        if isinstance(value, dict):
            saved[key] = value
    return saved


async def _fill_layout_maps(db: AsyncSession, llm_output: dict[str, Any]) -> None:
    """Fill roles, titles, and recipe types the resume path would load from the DB.

    Checkpoints written before those maps existed still replay without a database.
    """
    handles = llm_output.get("handles")
    if not isinstance(handles, dict):
        return
    recipe_ids: list[UUID] = []
    for value in handles.values():
        try:
            recipe_ids.append(value if isinstance(value, UUID) else UUID(str(value)))
        except (TypeError, ValueError):
            continue
    if not recipe_ids:
        return
    rows = await db.execute(
        select(Recipe.id, Recipe.name, Recipe.recipe_type, RecipeMealDetails.meal_roles)
        .outerjoin(RecipeMealDetails, RecipeMealDetails.recipe_id == Recipe.id)
        .where(Recipe.id.in_(recipe_ids), Recipe.deleted_at.is_(None))
    )
    roles = dict(llm_output.get("roles") or {})
    titles = dict(llm_output.get("titles") or {})
    types = dict(llm_output.get("types") or {})
    for recipe_id, name, recipe_type, meal_roles in rows.all():
        key = str(recipe_id)
        if not titles.get(key):
            titles[key] = str(name)
        if not types.get(key):
            types[key] = _enum(recipe_type)
        if key not in roles:
            roles[key] = [_enum(role) for role in (meal_roles or [])]
    llm_output["roles"] = roles
    llm_output["titles"] = titles
    llm_output["types"] = types


def _saved_recipe_ids(llm_output: dict[str, Any]) -> list[UUID]:
    """Handles plus any saved recipe id already written on a plan item."""
    values: list[object] = []
    handles = llm_output.get("handles")
    if isinstance(handles, dict):
        values.extend(handles.values())
    output = llm_output.get("output")
    days = output.get("days") if isinstance(output, dict) else None
    if isinstance(days, list):
        for day in days:
            if not isinstance(day, dict):
                continue
            items = day.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    values.append(item.get("recipe_id"))
    ids: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value in (None, "generate_new"):
            continue
        try:
            recipe_id = value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError):
            continue
        if recipe_id in seen:
            continue
        seen.add(recipe_id)
        ids.append(recipe_id)
    return ids


async def _snapshots(
    db: AsyncSession, user_id: UUID, llm_output: dict[str, Any]
) -> dict[str, Any]:
    """RecipeService.load_plan_snapshots for this plan's saved recipe ids."""
    recipe_ids = _saved_recipe_ids(llm_output)
    if not recipe_ids:
        return {}
    loaded = await RecipeService().load_plan_snapshots(user_id, recipe_ids, db)
    return {
        str(recipe_id): snapshot.model_dump(mode="json")
        for recipe_id, snapshot in loaded.items()
    }


async def _juicing_rows(db: AsyncSession, plan_id: UUID) -> list[dict[str, Any]]:
    result = await db.execute(
        select(JuicingConfig)
        .where(JuicingConfig.plan_id == plan_id)
        .order_by(JuicingConfig.slot_order.asc(), JuicingConfig.time_of_day.asc())
    )
    rows: list[dict[str, Any]] = []
    for row in result.scalars().all():
        size = _enum(row.size)
        rows.append(
            {
                "time_of_day": _enum(row.time_of_day),
                "size": size,
                "size_ml": JUICE_SIZE_ML.get(size),
                "slot_order": int(row.slot_order),
            }
        )
    return rows


async def _pins(
    db: AsyncSession, plan: MealPlan, params: dict[str, Any]
) -> list[dict[str, Any]]:
    notes = params.get("notes") or plan.notes or ""
    if not str(notes).strip():
        return []
    library_rows = await db.execute(
        select(Recipe.id, Recipe.name, Recipe.recipe_type).where(
            Recipe.user_id == plan.user_id,
            Recipe.deleted_at.is_(None),
        )
    )
    library: list[RecipeTitleRef] = []
    types: dict[UUID, str] = {}
    for recipe_id, name, recipe_type in library_rows.all():
        library.append(RecipeTitleRef(id=recipe_id, name=str(name)))
        types[recipe_id] = _enum(recipe_type)
    extracted = NotesPreprocessor().extract(
        str(notes),
        library,
        duration_days=int(params.get("duration_days") or plan.num_days),
    )
    pins: list[dict[str, Any]] = []
    for assignment in extracted.hard_slot_assignments:
        pins.append(
            {
                "day": assignment.day,
                "slot": assignment.slot_type,
                "recipe_id": str(assignment.recipe_id),
                "recipe_type": types.get(assignment.recipe_id, "meal"),
                "recipe_name": assignment.recipe_name,
            }
        )
    return pins


def _enum(value: object) -> str:
    raw = value.value if hasattr(value, "value") else value
    return str(raw)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a plan checkpoint (read-only).")
    choose = parser.add_mutually_exclusive_group(required=True)
    choose.add_argument("--job-prefix", help="First 8 characters of job_queue.id")
    choose.add_argument(
        "--latest",
        action="store_true",
        help="Newest meal_plans row that has a checkpoint",
    )
    parser.add_argument("--out", required=True, help="JSON path to write")
    return parser.parse_args(argv)


async def _main(argv: list[str]) -> None:
    args = _parse_args(argv)
    async with async_session_factory() as db:
        try:
            document = await export_checkpoint(
                db,
                job_prefix=args.job_prefix,
                latest=bool(args.latest),
            )
        finally:
            await db.rollback()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {out} (job {document['job_id']})")


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
