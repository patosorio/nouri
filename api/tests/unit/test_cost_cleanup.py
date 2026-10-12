"""Cost cleanup: no re-estimate, cached prefixes, hash-skipped embeddings."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from agent.chat_agent import CHAT_SYSTEM_PROMPT, ChatAgent
from agent.recipe_generator import RecipeGeneratorAgent
from agent.recipe_importer import RecipeImporterAgent
from config import MODEL_ROUTING, AgentTask, Settings, settings
from db.models import CookingType, DietType, UserTier
from schemas.agent import AgentContext, RecipeGenerationRequest
from search.recipe_search_service import RecipeSearchService


def test_fast_model_id_comes_from_config() -> None:
    default = Settings.model_fields["anthropic_model_fast"].default
    assert default != "claude-haiku-3-5"
    assert default == "claude-haiku-5-5"
    for task in (
        AgentTask.RECIPE_IMPORT_TEXT,
        AgentTask.PLAN_EXPLANATION,
        AgentTask.CONVERSATION_SUMMARY,
        AgentTask.NUTRITIONAL_PROFILE,
    ):
        assert MODEL_ROUTING[task] == settings.anthropic_model_fast


def _recipe_message(*, calories: float) -> SimpleNamespace:
    payload = {
        "title": "Lentil soup",
        "diet_type": "vegan",
        "prep_type": "boiled",
        "nutrition_per_serving": {
            "calories_kcal": calories,
            "protein_g": 10,
            "fat_g": 5,
            "carbohydrates_g": 20,
            "fiber_g": 4,
        },
        "ingredients": [
            {"ingredient_name": "lentils", "quantity": 1, "unit": "cup"}
        ],
        "steps": [{"step_number": 1, "instruction": "Simmer until soft."}],
    }
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="tool_use", name="output_recipe", input=payload)
        ]
    )


class _RecordingClient:
    def __init__(self, *, calories: float) -> None:
        self.calls: list[dict[str, Any]] = []
        self._calories = calories

    async def complete(self, messages: object, **kwargs: object) -> SimpleNamespace:
        self.calls.append({"messages": messages, **kwargs})
        return _recipe_message(calories=self._calories)


class _Names:
    async def resolve_name(self, _name: object, _db: object) -> None:
        return None


def _install_profile(monkeypatch: pytest.MonkeyPatch, module: str, marker: str) -> None:
    profile = SimpleNamespace(diet_type=DietType.VEGAN)
    exclusion = SimpleNamespace(ingredient_name_raw=marker, ingredient_id=None)
    service = MagicMock()
    service.get_profile = AsyncMock(return_value=profile)
    service.get_exclusions = AsyncMock(return_value=[exclusion])
    monkeypatch.setattr(f"{module}.ProfileService", MagicMock(return_value=service))


def _assert_cached(call: dict[str, Any], *, marker: str) -> None:
    system = call["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert marker not in str(system[0]["text"])
    tools = call["tools"]
    assert isinstance(tools, list) and tools
    assert tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in tool for tool in tools[:-1])


def _user_text(call: dict[str, Any]) -> str:
    messages = call["messages"]
    assert isinstance(messages, list)
    content = messages[0]["content"]
    if isinstance(content, str):
        return content
    assert isinstance(content, list)
    return "\n".join(
        str(block.get("text", "")) for block in content if isinstance(block, dict)
    )


@pytest.mark.asyncio
async def test_out_of_range_generation_makes_one_call_and_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "xylitol-marker"
    _install_profile(monkeypatch, "agent.recipe_generator", marker)
    client = _RecordingClient(calories=9000)
    agent = RecipeGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        exclusion_service=_Names(),  # type: ignore[arg-type]
    )

    draft = await agent.generate(
        uuid4(), RecipeGenerationRequest(title="Soup"), AsyncMock()
    )

    assert len(client.calls) == 1
    assert draft.nutrition_flagged is True
    _assert_cached(client.calls[0], marker=marker)
    assert marker in _user_text(client.calls[0])


@pytest.mark.asyncio
async def test_out_of_range_import_makes_one_call_and_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "xylitol-marker"
    _install_profile(monkeypatch, "agent.recipe_importer", marker)
    client = _RecordingClient(calories=9000)
    agent = RecipeImporterAgent(
        client=client,  # type: ignore[arg-type]
        exclusion_service=_Names(),  # type: ignore[arg-type]
    )

    draft = await agent.import_from_text(uuid4(), "1 cup lentils", AsyncMock())

    assert len(client.calls) == 1
    assert draft.nutrition_flagged is True
    _assert_cached(client.calls[0], marker=marker)
    assert marker in _user_text(client.calls[0])


class _TextBlock:
    type = "text"

    def model_dump(self, mode: str = "json") -> dict[str, str]:
        del mode
        return {"type": "text", "text": "ok"}


class _ChatClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.last_message: SimpleNamespace | None = None
        self.last_stop_reason: str | None = None

    async def stream_text(self, messages: object, **kwargs: object):
        self.calls.append({"messages": messages, **kwargs})
        self.last_message = SimpleNamespace(
            content=[_TextBlock()],
            stop_reason="end_turn",
        )
        self.last_stop_reason = "end_turn"
        yield "ok"


@pytest.mark.asyncio
async def test_chat_request_caches_stable_prefix_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "cashew-marker"
    profile = SimpleNamespace(
        diet_type=DietType.VEGAN,
        cooking_type=CookingType.COOKED_100,
        calorie_target=1800,
        tier=UserTier.FREE,
    )
    exclusion = SimpleNamespace(ingredient_name_raw=marker)
    service = MagicMock()
    service.get_profile = AsyncMock(return_value=profile)
    service.get_exclusions = AsyncMock(return_value=[exclusion])
    monkeypatch.setattr(
        "agent.chat_agent.ProfileService",
        MagicMock(return_value=service),
    )

    user_id = uuid4()
    conversation = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        messages=[],
        tool_call_logs=[],
        plan_id=None,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=conversation)
    client = _ChatClient()
    agent = ChatAgent(client=client)  # type: ignore[arg-type]

    events = [
        event
        async for event in agent.run(
            user_id, conversation.id, "plan dinner", AgentContext(), db
        )
    ]

    assert events[-1].type == "done"
    assert len(client.calls) == 1
    call = client.calls[0]
    _assert_cached(call, marker=marker)
    assert call["system"][0]["text"] == CHAT_SYSTEM_PROMPT
    assert marker in _user_text(call)


@pytest.mark.asyncio
async def test_embed_recipe_skips_voyage_when_hash_and_model_match() -> None:
    search = RecipeSearchService(voyage_client=object())
    text = "Lentil soup. warm. Ingredients: lentils. Diet: vegan. Prep: boiled."
    search._build_embedding_text = AsyncMock(return_value=text)  # type: ignore[method-assign]
    search.embed_texts = AsyncMock(side_effect=AssertionError("voyage"))  # type: ignore[method-assign]
    content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    stored = [0.1, 0.2]
    existing = SimpleNamespace(
        content_hash=content_hash,
        model_version=search._resolve_model(),
        embedding=stored,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=existing)

    result = await search.embed_recipe(SimpleNamespace(id=uuid4()), db)  # type: ignore[arg-type]

    assert result == stored
    search.embed_texts.assert_not_called()
    db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_embed_recipe_calls_voyage_once_when_hash_changes() -> None:
    search = RecipeSearchService(voyage_client=object())
    text = "Lentil soup. warm. Ingredients: lentils. Diet: vegan. Prep: boiled."
    search._build_embedding_text = AsyncMock(return_value=text)  # type: ignore[method-assign]
    vector = [0.3, 0.4]
    search.embed_texts = AsyncMock(return_value=[vector])  # type: ignore[method-assign]
    existing = SimpleNamespace(
        content_hash="stale",
        model_version=search._resolve_model(),
        embedding=[0.0],
        embedded_at=None,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=existing)

    result = await search.embed_recipe(SimpleNamespace(id=uuid4()), db)  # type: ignore[arg-type]

    assert search.embed_texts.await_count == 1
    assert result == vector
    assert existing.content_hash == hashlib.md5(text.encode("utf-8")).hexdigest()
    assert existing.embedding == vector
    assert existing.model_version == search._resolve_model()
