"""Chat router integration tests — docs/8_TEST_PLAN.md §4.4."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from schemas.agent import SSEEvent

# RISK-02 covered indirectly via plan notes preprocessor unit tests
# Chat stream uses mocked ChatService — no live Anthropic.


@pytest.mark.integration
async def test_chat_unauthorized(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        "/api/v1/chat",
        json={"message": "Hello"},
    )
    assert response.status_code == 401


@pytest.mark.integration
async def test_chat_returns_sse_stream(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()

    async def fake_stream(**kwargs: Any) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(type="text_delta", text="Hello from Nouri")
        yield SSEEvent(type="done", conversation_id=conversation_id)

    monkeypatch.setattr(
        "routers.chat._service.stream",
        fake_stream,
    )

    response = await client.post(
        "/api/v1/chat",
        json={"message": "what's a good raw breakfast?"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "X-Conversation-Id" in response.headers
    text = response.text
    assert "text_delta" in text
    assert "Hello from Nouri" in text


@pytest.mark.integration
async def test_chat_validation_failure(client: AsyncClient) -> None:
    # message required
    response = await client.post("/api/v1/chat", json={})
    assert response.status_code == 422
