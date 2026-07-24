"""Plan router integration tests — docs/8_TEST_PLAN.md §4.2."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PlanStatus, UserProfile
from tests.factories import make_plan, make_user

# RISK-01 covered by: test_get_plan_returns_saved_recipe_ids_on_items
# RISK-07 covered by: (worker path — deferred; stub job creation covered here)


@pytest.mark.integration
async def test_list_plans_empty(client: AsyncClient) -> None:
    response = await client.get("/api/v1/plans")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


@pytest.mark.integration
async def test_list_plans_returns_seeded_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    plan = await make_plan(db_session, test_user.id, num_days=3)
    response = await client.get("/api/v1/plans")
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == str(plan.id)


@pytest.mark.integration
async def test_generate_plan_returns_job_202(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/plans",
        json={
            "num_days": 7,
            "diet_type": "plant_based",
            "cooking_type": "raw_80_cooked_20",
            "include_juicing": True,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] in ("pending", "running")
    assert "id" in body


@pytest.mark.integration
async def test_get_plan_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    plan = await make_plan(db_session, test_user.id, num_days=2)
    response = await client.get(f"/api/v1/plans/{plan.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(plan.id)
    assert len(body["days"]) == 2
    assert len(body["days"][0]["items"]) >= 1


@pytest.mark.integration
async def test_get_plan_returns_saved_recipe_ids_on_items(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    # RISK-01 covered by: test_get_plan_returns_saved_recipe_ids_on_items
    plan = await make_plan(db_session, test_user.id, num_days=1)
    response = await client.get(f"/api/v1/plans/{plan.id}")
    assert response.status_code == 200
    items = response.json()["days"][0]["items"]
    assert any(item.get("recipe_id") for item in items)


@pytest.mark.integration
async def test_plan_get_returns_404_for_other_users_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_as,
) -> None:
    owner = await make_user(db_session, email="owner@nouri.app")
    plan = await make_plan(db_session, owner.id, num_days=1, with_meals=False)
    # client is still authenticated as test_user
    response = await client.get(f"/api/v1/plans/{plan.id}")
    assert response.status_code in (403, 404)


@pytest.mark.integration
async def test_plans_unauthorized(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/v1/plans")
    assert response.status_code == 401


@pytest.mark.integration
async def test_approve_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    plan = await make_plan(
        db_session, test_user.id, num_days=1, status=PlanStatus.REVIEWING
    )
    response = await client.patch(
        f"/api/v1/plans/{plan.id}",
        json={"status": "approved"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
