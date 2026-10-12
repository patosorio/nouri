"""Conversation display flattening and list/get endpoints."""

from __future__ import annotations

from uuid import uuid4

import pytest
from db.models import Conversation, UserProfile
from httpx import AsyncClient
from services.chat_service import ChatService, display_messages
from sqlalchemy.ext.asyncio import AsyncSession


def test_display_messages_unwraps_user_content_and_assistant_text() -> None:
    rows = display_messages(
        [
            {"role": "user", "content": "<user_content>Make me a week</user_content>"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "The form is ready on the right."},
                    {"type": "tool_use", "name": "trigger_plan_generation"},
                ],
            },
        ]
    )
    assert rows == [
        {"role": "user", "content": "Make me a week"},
        {"role": "assistant", "content": "The form is ready on the right."},
    ]


@pytest.mark.asyncio
async def test_list_and_get_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    service = ChatService()
    conversation = Conversation(
        user_id=test_user.id,
        messages=[
            {"role": "user", "content": "<user_content>hello</user_content>"},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi — I'm Nouri."}],
            },
        ],
        tool_call_logs=[],
    )
    db_session.add(conversation)
    await db_session.flush()
    await service._encrypt_conversation_messages(conversation.id, db_session)

    listed = await client.get("/api/v1/conversations")
    assert listed.status_code == 200
    body = listed.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == str(conversation.id)
    assert body["data"][0]["message_count"] == 2

    got = await client.get(f"/api/v1/conversations/{conversation.id}")
    assert got.status_code == 200
    messages = got.json()["messages"]
    assert messages[0]["content"] == "hello"
    assert messages[1]["content"] == "Hi — I'm Nouri."


@pytest.mark.asyncio
async def test_get_conversation_other_user_is_404(
    client: AsyncClient,
    db_session: AsyncSession,
    other_user: UserProfile,
) -> None:
    conversation = Conversation(
        user_id=other_user.id, messages=[], tool_call_logs=[]
    )
    db_session.add(conversation)
    await db_session.flush()

    response = await client.get(f"/api/v1/conversations/{conversation.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: UserProfile,
) -> None:
    conversation = Conversation(
        user_id=test_user.id, messages=[], tool_call_logs=[]
    )
    db_session.add(conversation)
    await db_session.flush()
    conv_id = conversation.id

    response = await client.delete(f"/api/v1/conversations/{conv_id}")
    assert response.status_code == 204
    missing = await client.get(f"/api/v1/conversations/{conv_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_list_conversations_empty(client: AsyncClient) -> None:
    response = await client.get("/api/v1/conversations")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_get_missing_conversation(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/conversations/{uuid4()}")
    assert response.status_code == 404
