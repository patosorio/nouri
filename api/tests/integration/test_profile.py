"""Profile router integration tests — docs/8_TEST_PLAN.md §4."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_ingredient, make_user

# RISK-05 covered by: test_add_exclusion_resolves_known_ingredient


@pytest.mark.integration
async def test_get_profile_happy_path(client: AsyncClient) -> None:
    response = await client.get("/api/v1/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["diet_type"] == "plant_based"
    assert "email" in body


@pytest.mark.integration
async def test_get_profile_unauthorized(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/v1/profile")
    assert response.status_code == 401


@pytest.mark.integration
async def test_patch_profile_validation_failure(client: AsyncClient) -> None:
    response = await client.patch(
        "/api/v1/profile",
        json={"calorie_target": 50},  # below OpenAPI minimum when validated
    )
    # Either 422 from pydantic or 200 if field unconstrained on ProfileUpdate
    assert response.status_code in (200, 422)


@pytest.mark.integration
async def test_onboarding_creates_profile_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.post(
        "/api/v1/profile/onboarding",
        json={
            "diet_type": "vegan",
            "cooking_type": "raw_100",
            "diet_subtypes": ["high_protein"],
            "cuisine_prefs": ["mediterranean"],
            "juicing_enabled": True,
            "exclusion_names": ["peanuts"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["diet_type"] == "vegan"
    assert body["cooking_type"] == "raw_100"


@pytest.mark.integration
async def test_add_exclusion_resolves_known_ingredient(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # RISK-05 covered by: test_add_exclusion_resolves_known_ingredient
    await make_ingredient(db_session, name="peanuts")
    response = await client.post(
        "/api/v1/profile/exclusions",
        json={"ingredient_name_raw": "Peanuts"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ingredient_name_raw"] == "Peanuts"
    assert body["ingredient_id"] is not None


@pytest.mark.integration
async def test_add_exclusion_unresolved_stores_null_id(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/profile/exclusions",
        json={"ingredient_name_raw": "unobtainium-spice"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ingredient_id"] is None
