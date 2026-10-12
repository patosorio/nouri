"""meal_roles backfill: exact titles only, idempotent, dry-run writes nothing."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from db.models import MealRole, PrimaryProtein, Recipe, RecipeMealDetails, RecipeType
from scripts.backfill_meal_roles import backfill_meal_roles, main
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_recipe, make_user


def _role_values(row: RecipeMealDetails) -> list[str]:
    return [
        role.value if hasattr(role, "value") else str(role) for role in row.meal_roles
    ]


def _recipe_category_fn() -> Callable[..., Any] | None:
    root = Path(__file__).resolve().parents[2]
    for path in root.rglob("*.py"):
        if any(part in {"tests", "scripts", "__pycache__"} for part in path.parts):
            continue
        source = path.read_text(encoding="utf-8")
        if "def recipe_category(" not in source:
            continue
        module_name = ".".join(path.relative_to(root).with_suffix("").parts)
        module = importlib.import_module(module_name)
        fn = getattr(module, "recipe_category", None)
        if callable(fn):
            return fn
    return None


def _category(fn: Callable[..., Any], recipe: Recipe, roles: list[str]) -> str:
    params = [
        name
        for name, param in inspect.signature(fn).parameters.items()
        if param.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]
    kwargs: dict[str, Any] = {}
    if "recipe_type" in params:
        kwargs["recipe_type"] = recipe.recipe_type
    if "meal_roles" in params:
        kwargs["meal_roles"] = roles
    if "recipe" in params:
        kwargs["recipe"] = recipe
    if "name" in params:
        kwargs["name"] = recipe.name
    result = fn(**kwargs) if kwargs else fn(recipe.recipe_type, roles)
    return result.value if hasattr(result, "value") else str(result)


@pytest.mark.asyncio
async def test_backfill_meal_roles_is_idempotent_and_dry_run_writes_nothing(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, email="backfill-roles@nouri.app")
    other = await make_user(db_session, email="backfill-other@nouri.app")
    other_oats = await make_recipe(
        db_session, other.id, name="Golden Turmeric Overnight Oats"
    )
    oats = await make_recipe(
        db_session, user.id, name="Golden Turmeric Overnight Oats"
    )
    miso = await make_recipe(
        db_session, user.id, name="Miso-Glazed Roasted Cauliflower Steaks"
    )
    pad_thai = await make_recipe(
        db_session, user.id, name="Zucchini Pad Thai with Almond Sauce"
    )
    salad = await make_recipe(
        db_session, user.id, name="Citrus Herb Chickpea Salad"
    )
    bowl = await make_recipe(
        db_session,
        user.id,
        name="Spinach Mango Smoothie Bowl",
        recipe_type=RecipeType.SMOOTHIE,
    )
    near_miss = await make_recipe(db_session, user.id, name="Zucchini Pad Thai")
    deleted = await make_recipe(
        db_session, user.id, name="Golden Turmeric Overnight Oats"
    )
    deleted.deleted_at = datetime.now(timezone.utc)
    db_session.add(
        RecipeMealDetails(
            recipe_id=pad_thai.id,
            primary_protein_source=PrimaryProtein.LEGUMES,
            meal_roles=[],
        )
    )
    db_session.add(
        RecipeMealDetails(
            recipe_id=salad.id,
            primary_protein_source=PrimaryProtein.EGGS,
            meal_roles=[MealRole.DINNER, MealRole.LUNCH],
        )
    )
    await db_session.flush()

    dry = await backfill_meal_roles(db_session, dry_run=True, user_id=user.id)
    assert any("'Zucchini Pad Thai'" in line for line in dry.near_misses)
    assert await db_session.get(RecipeMealDetails, oats.id) is None
    assert await db_session.get(RecipeMealDetails, miso.id) is None
    assert await db_session.get(RecipeMealDetails, bowl.id) is None
    assert await db_session.get(RecipeMealDetails, near_miss.id) is None
    assert await db_session.get(RecipeMealDetails, deleted.id) is None
    pad_row = await db_session.get(RecipeMealDetails, pad_thai.id)
    salad_row = await db_session.get(RecipeMealDetails, salad.id)
    assert pad_row is not None and _role_values(pad_row) == []
    assert salad_row is not None
    assert _role_values(salad_row) == ["dinner", "lunch"]
    assert salad_row.primary_protein_source == PrimaryProtein.EGGS

    first = await backfill_meal_roles(db_session, dry_run=False, user_id=user.id)
    assert "Golden Turmeric Overnight Oats (meal)" not in first.not_found
    assert "Spinach Mango Smoothie Bowl (smoothie)" not in first.not_found

    oats_row = await db_session.get(RecipeMealDetails, oats.id)
    miso_row = await db_session.get(RecipeMealDetails, miso.id)
    bowl_row = await db_session.get(RecipeMealDetails, bowl.id)
    pad_row = await db_session.get(RecipeMealDetails, pad_thai.id)
    salad_row = await db_session.get(RecipeMealDetails, salad.id)
    assert oats_row is not None
    assert miso_row is not None
    assert bowl_row is not None
    assert pad_row is not None
    assert salad_row is not None
    assert _role_values(oats_row) == ["breakfast"]
    assert oats_row.primary_protein_source == PrimaryProtein.NONE
    assert _role_values(miso_row) == ["lunch", "dinner"]
    assert _role_values(pad_row) == ["lunch", "dinner"]
    assert pad_row.primary_protein_source == PrimaryProtein.LEGUMES
    assert _role_values(bowl_row) == ["breakfast"]
    assert _role_values(salad_row) == ["dinner", "lunch"]
    assert salad_row.primary_protein_source == PrimaryProtein.EGGS
    assert await db_session.get(RecipeMealDetails, near_miss.id) is None
    assert await db_session.get(RecipeMealDetails, deleted.id) is None
    assert await db_session.get(RecipeMealDetails, other_oats.id) is None

    second = await backfill_meal_roles(
        db_session, dry_run=False, user_id=user.id
    )
    assert second.inserted == 0
    assert second.updated == 0
    salad_again = await db_session.get(RecipeMealDetails, salad.id)
    assert salad_again is not None
    assert _role_values(salad_again) == ["dinner", "lunch"]

    category_fn = _recipe_category_fn()
    if category_fn is None:
        assert _role_values(oats_row) == ["breakfast"]
        assert _role_values(bowl_row) == ["breakfast"]
        assert _role_values(miso_row) == ["lunch", "dinner"]
        assert _role_values(pad_row) == ["lunch", "dinner"]
        assert _role_values(salad_again) == ["dinner", "lunch"]
        return

    assert _category(category_fn, oats, _role_values(oats_row)) == "breakfast"
    assert _category(category_fn, bowl, _role_values(bowl_row)) == "breakfast"
    assert _category(category_fn, miso, _role_values(miso_row)) == "lunch_dinner"
    assert _category(category_fn, pad_thai, _role_values(pad_row)) == "lunch_dinner"
    assert _category(category_fn, salad, _role_values(salad_again)) == "lunch_dinner"


def test_missing_user_id_is_a_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["backfill_meal_roles"])
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code != 0
