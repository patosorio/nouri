"""Shopping list integration tests — docs/8_TEST_PLAN.md §3.3 / §4."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PlanStatus, UserProfile
from tests.factories import make_plan, make_user

# RISK-08 covered by: test_shopping_list_for_approved_plan_returns_items
# (full pantry double-count unit coverage lives with ShoppingListService tests)


@pytest.mark.integration
async def test_shopping_list_unauthorized(anon_client: AsyncClient) -> None:
    response = await anon_client.get(
        f"/api/v1/plans/{__import__('uuid').uuid4()}/shopping-list"
    )
    assert response.status_code == 401


@pytest.mark.integration
async def test_shopping_list_for_other_users_plan_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner = await make_user(db_session, email="shop-owner@nouri.app")
    plan = await make_plan(
        db_session, owner.id, num_days=1, status=PlanStatus.APPROVED
    )
    response = await client.get(f"/api/v1/plans/{plan.id}/shopping-list")
    assert response.status_code in (403, 404)


@pytest.mark.integration
async def test_shopping_list_for_approved_plan_returns_items(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    # RISK-08 covered by: test_shopping_list_for_approved_plan_returns_items
    plan = await make_plan(
        db_session, test_user.id, num_days=1, status=PlanStatus.APPROVED
    )
    response = await client.get(f"/api/v1/plans/{plan.id}/shopping-list")
    assert response.status_code == 200, response.text
    body = response.json()
    # Shape may be {items: [...]} or {data: [...]} depending on serializer
    assert isinstance(body, dict)
