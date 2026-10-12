"""Provision auth.users + user_profiles so conversations FK can succeed."""

from __future__ import annotations

from uuid import uuid4

import pytest
from db.models import Conversation, UserProfile
from services.profile_service import ProfileService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_ensure_profile_creates_row_and_allows_conversation(
    db_session: AsyncSession,
) -> None:
    user_id = uuid4()
    profile = await ProfileService().ensure_profile(user_id, db_session)
    assert profile.id == user_id
    again = await ProfileService().ensure_profile(user_id, db_session)
    assert again.id == profile.id

    conversation = Conversation(user_id=user_id, messages=[], tool_call_logs=[])
    db_session.add(conversation)
    await db_session.flush()
    stored = await db_session.get(Conversation, conversation.id)
    assert stored is not None
    assert stored.user_id == user_id


@pytest.mark.asyncio
async def test_ensure_profile_is_idempotent_for_existing_user(
    db_session: AsyncSession,
) -> None:
    from tests.factories import make_user

    existing = await make_user(db_session)
    profile = await ProfileService().ensure_profile(existing.id, db_session)
    assert profile.id == existing.id
    count = await db_session.get(UserProfile, existing.id)
    assert count is not None
