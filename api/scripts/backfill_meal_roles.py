"""Backfill meal_roles for uncategorized saved recipes. Data only.

Patricia runs this. No model or network calls.

    cd api && python -m scripts.backfill_meal_roles --user-id UUID [--dry-run]

Juices are not updated: their category comes from recipe_type.
Only exact title + recipe_type matches are written. Near-misses are printed.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from uuid import UUID

from db.models import MealRole, Recipe, RecipeMealDetails, RecipeType
from db.session import async_session_factory
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# Exact title + recipe_type. The juice is intentionally absent.
_TARGETS: tuple[tuple[str, RecipeType, tuple[MealRole, ...]], ...] = (
    ("Golden Turmeric Overnight Oats", RecipeType.MEAL, (MealRole.BREAKFAST,)),
    (
        "Miso-Glazed Roasted Cauliflower Steaks",
        RecipeType.MEAL,
        (MealRole.LUNCH, MealRole.DINNER),
    ),
    (
        "Zucchini Pad Thai with Almond Sauce",
        RecipeType.MEAL,
        (MealRole.LUNCH, MealRole.DINNER),
    ),
    (
        "Citrus Herb Chickpea Salad",
        RecipeType.MEAL,
        (MealRole.LUNCH, MealRole.DINNER),
    ),
    (
        "Spinach Mango Smoothie Bowl",
        RecipeType.SMOOTHIE,
        (MealRole.BREAKFAST,),
    ),
)


@dataclass(frozen=True, slots=True)
class BackfillResult:
    inserted: int
    updated: int
    skipped: int
    not_found: tuple[str, ...]
    near_misses: tuple[str, ...]


def _normalize_title(title: str) -> list[str]:
    chars = [ch if ch.isalnum() else " " for ch in title.casefold()]
    return "".join(chars).split()


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    index = 0
    for word in haystack:
        if index < len(needle) and word == needle[index]:
            index += 1
    return index == len(needle)


def _is_near_miss(candidate: str, target: str) -> bool:
    """Punctuation differences, or one title's words contained in the other."""
    if candidate.casefold() == target.casefold():
        return False
    left = _normalize_title(candidate)
    right = _normalize_title(target)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) < 3:
        return False
    return _is_subsequence(shorter, longer)


def _label(title: str, recipe_type: RecipeType) -> str:
    return f"{title} ({recipe_type.value})"


def _roles_label(roles: tuple[MealRole, ...]) -> str:
    return "{" + ", ".join(role.value for role in roles) + "}"


async def _insert_roles(
    db: AsyncSession, recipe_id: UUID, roles: tuple[MealRole, ...]
) -> None:
    # Omit primary_protein_source so the column default ('none') applies.
    stmt = (
        pg_insert(RecipeMealDetails)
        .values(recipe_id=recipe_id, meal_roles=list(roles))
        .on_conflict_do_nothing(index_elements=["recipe_id"])
    )
    await db.execute(stmt)


async def backfill_meal_roles(
    db: AsyncSession,
    *,
    dry_run: bool,
    user_id: UUID | None = None,
) -> BackfillResult:
    """Fill empty meal_roles for exact title matches. Writes nothing when dry_run."""
    stmt = select(Recipe).where(Recipe.deleted_at.is_(None))
    if user_id is not None:
        stmt = stmt.where(Recipe.user_id == user_id)
    rows = await db.execute(stmt)
    recipes = list(rows.scalars().all())

    inserted = 0
    updated = 0
    skipped = 0
    not_found: list[str] = []
    near_misses: list[str] = []

    for title, recipe_type, roles in _TARGETS:
        exact = [
            recipe
            for recipe in recipes
            if recipe.recipe_type == recipe_type
            and recipe.name.casefold() == title.casefold()
        ]
        exact_ids = {recipe.id for recipe in exact}
        for recipe in recipes:
            if recipe.id in exact_ids:
                continue
            if recipe.recipe_type != recipe_type:
                continue
            if not _is_near_miss(recipe.name, title):
                continue
            line = (
                f"{recipe.name!r} ≈ target {_label(title, recipe_type)}"
                " — not written"
            )
            if line not in near_misses:
                near_misses.append(line)
                print(f"near-miss: {line}")

        if not exact:
            missing = _label(title, recipe_type)
            not_found.append(missing)
            print(f"not found: {missing}")
            continue

        for recipe in exact:
            details = await db.get(RecipeMealDetails, recipe.id)
            role_text = _roles_label(roles)
            if details is None:
                print(
                    f"{'would insert' if dry_run else 'insert'} {role_text} "
                    f"on {recipe.name!r} ({recipe.id})"
                )
                if not dry_run:
                    await _insert_roles(db, recipe.id, roles)
                inserted += 1
                continue
            current = list(details.meal_roles or [])
            if not current:
                print(
                    f"{'would update' if dry_run else 'update'} {role_text} "
                    f"on {recipe.name!r} ({recipe.id})"
                )
                if not dry_run:
                    details.meal_roles = list(roles)
                updated += 1
                continue
            print(f"skip {recipe.name!r} ({recipe.id}): meal_roles already set")
            skipped += 1

    if not dry_run:
        await db.flush()

    result = BackfillResult(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        not_found=tuple(not_found),
        near_misses=tuple(near_misses),
    )
    mode = "dry-run" if dry_run else "wrote"
    print(
        f"{mode}: inserted={result.inserted} updated={result.updated} "
        f"skipped={result.skipped}"
    )
    if result.not_found:
        print("titles not found: " + "; ".join(result.not_found))
    else:
        print("titles not found: none")
    return result


async def _run(dry_run: bool, user_id: UUID | None) -> None:
    async with async_session_factory() as session:
        await backfill_meal_roles(session, dry_run=dry_run, user_id=user_id)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill meal_roles on exact saved-recipe titles"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matches and write nothing",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="Only recipes owned by this user",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    asyncio.run(_run(dry_run=args.dry_run, user_id=UUID(args.user_id)))


if __name__ == "__main__":
    main()
