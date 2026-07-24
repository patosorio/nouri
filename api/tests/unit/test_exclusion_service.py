"""ExclusionService unit tests — docs/8_TEST_PLAN.md §3.4 / RISK-05."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from preprocessing.exclusion_service import ExclusionService
from tests.factories import make_ingredient

# RISK-05 covered by: test_resolve_name_exact_match, test_resolve_name_case_insensitive


@pytest.mark.integration
async def test_resolve_name_exact_match(db_session: AsyncSession) -> None:
    # RISK-05 covered by: test_resolve_name_exact_match
    ing = await make_ingredient(db_session, name="peanuts")
    resolved = await ExclusionService().resolve_name("peanuts", db_session)
    assert resolved == ing.id


@pytest.mark.integration
async def test_resolve_name_case_insensitive(db_session: AsyncSession) -> None:
    # RISK-05 covered by: test_resolve_name_case_insensitive
    ing = await make_ingredient(db_session, name="Spinach")
    resolved = await ExclusionService().resolve_name("SPINACH", db_session)
    assert resolved == ing.id


@pytest.mark.integration
async def test_resolve_name_no_match(db_session: AsyncSession) -> None:
    resolved = await ExclusionService().resolve_name(
        "definitely-not-an-ingredient-xyz", db_session
    )
    assert resolved is None


@pytest.mark.integration
async def test_resolve_name_alias_match_deferred(db_session: AsyncSession) -> None:
    """aliases[] not in ERD — documented gap in missing.txt. Placeholder assert."""
    # RISK-05 covered by: test_resolve_name_alias_match_deferred (pending ERD aliases)
    await make_ingredient(db_session, name="peanuts")
    resolved = await ExclusionService().resolve_name("groundnuts", db_session)
    assert resolved is None  # until ingredients.aliases exists
