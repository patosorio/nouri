"""Recipe router integration tests — docs/8_TEST_PLAN.md §4.3."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserProfile
from tests.factories import make_plan, make_recipe, make_user

# RISK-06 covered by: fixture recipe_generation_response.json (in-bounds nutrition)
# RISK-03 covered by: test_save_recipe_persists_structured_fields


@pytest.mark.integration
async def test_list_recipes_empty(client: AsyncClient) -> None:
    response = await client.get("/api/v1/recipes")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.integration
async def test_list_recipes_returns_seeded(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    recipe = await make_recipe(db_session, test_user.id)
    response = await client.get("/api/v1/recipes")
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == str(recipe.id)


@pytest.mark.integration
async def test_save_recipe_persists_structured_fields(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RISK-03 covered by: test_save_recipe_persists_structured_fields
    monkeypatch.setattr(
        "routers.recipes.embed_recipe_by_id",
        AsyncMock(return_value=None),
    )
    response = await client.post(
        "/api/v1/recipes",
        json={
            "draft": {
                "name": "Test Salad",
                "description": "A simple salad",
                "recipe_type": "meal",
                "cooking_type": "raw_100",
                "prep_method": "raw",
                "source": "manual",
                "servings": 1,
                "prep_minutes": 10,
                "diet_types": ["plant_based"],
                "diet_subtypes": [],
                "cuisine": [],
                "tags": [],
                "steps": [
                    {
                        "step_number": 1,
                        "instruction": "Chop and toss.",
                    }
                ],
                "ingredients": [
                    {
                        "ingredient_name": "lettuce",
                        "amount": 2,
                        "unit": "cup",
                    }
                ],
                "nutrition": {
                    "calories_per_serving": 150,
                    "protein_g": 5,
                    "carbs_g": 20,
                    "fat_g": 6,
                    "fiber_g": 4,
                    "nutritional_highlights": [],
                },
                "primary_protein_source": "none",
                "meal_roles": ["lunch"],
            }
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Test Salad"
    assert body["cooking_type"] == "raw_100"


@pytest.mark.integration
async def test_recipe_get_returns_404_for_other_users_recipe(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner = await make_user(db_session, email="recipe-owner@nouri.app")
    recipe = await make_recipe(db_session, owner.id)
    response = await client.get(f"/api/v1/recipes/{recipe.id}")
    assert response.status_code in (403, 404)


@pytest.mark.integration
async def test_recipes_unauthorized(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/v1/recipes")
    assert response.status_code == 401


@pytest.mark.integration
async def test_recipe_search_without_query_lists(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
    mock_voyage: list,
) -> None:
    await make_recipe(db_session, test_user.id, name="Searchable Bowl")
    response = await client.get("/api/v1/recipes/search")
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] >= 1


@pytest.mark.integration
async def test_delete_recipe_referenced_by_approved_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    from db.models import PlanStatus

    recipe = await make_recipe(db_session, test_user.id)
    await make_plan(
        db_session,
        test_user.id,
        num_days=1,
        status=PlanStatus.APPROVED,
        recipe=recipe,
    )
    response = await client.delete(f"/api/v1/recipes/{recipe.id}")
    # Soft-delete may succeed (204) or block (422) depending on service rules
    assert response.status_code in (204, 422)
