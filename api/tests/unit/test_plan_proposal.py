"""Chat plan proposal — fill the generate form, do not enqueue."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from agent.chat_agent import plan_proposal_from_tool_result
from agent.tool_executor import _handle_trigger_plan_generation
from db.models import CookingType, DietType, RecipeUsagePolicy
from schemas.agent import PlanProposal


@pytest.mark.asyncio
async def test_trigger_plan_generation_returns_proposal_not_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = MagicMock()
    profile.diet_type = DietType.PESCATARIAN
    profile.cooking_type = CookingType.RAW_80_COOKED_20
    profile.calorie_target = 2050
    profile.recipe_usage_policy = RecipeUsagePolicy.BALANCED
    profile.juicing_enabled = True

    get_profile = AsyncMock(return_value=profile)
    monkeypatch.setattr(
        "agent.tool_executor.ProfileService.get_profile",
        get_profile,
    )
    create_stub = AsyncMock()
    monkeypatch.setattr(
        "services.plan_service.PlanService.create_plan_stub",
        create_stub,
    )

    result = await _handle_trigger_plan_generation(
        {
            "duration_days": 7,
            "diet_type": "vegan",
            "notes": "Bangkok morning juice, high iron",
        },
        uuid4(),
        MagicMock(),
        MagicMock(),
    )
    assert result["status"] == "awaiting_confirmation"
    assert result["proposal"]["diet_type"] == "vegan"
    assert result["proposal"]["include_juicing"] is True
    assert result["proposal"]["notes"] == "Bangkok morning juice, high iron"
    create_stub.assert_not_called()


def test_plan_proposal_from_tool_result() -> None:
    proposal = plan_proposal_from_tool_result(
        {
            "content": (
                '{"status":"awaiting_confirmation",'
                '"proposal":{"num_days":7,"diet_type":"vegan",'
                '"include_juicing":true}}'
            )
        }
    )
    assert isinstance(proposal, PlanProposal)
    assert proposal.diet_type == DietType.VEGAN
    assert plan_proposal_from_tool_result({"is_error": True, "content": "{}"}) is None
