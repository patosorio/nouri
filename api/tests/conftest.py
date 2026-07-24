"""Shared pytest fixtures — docs/8_TEST_PLAN.md / Phase 11."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from db.models import UserProfile, UserTier
from db.session import resolve_database_url
from dependencies import CurrentUser, get_current_user, get_db
from main import app
from tests.factories import (
    make_exclusion,
    make_plan,
    make_recipe,
    make_user,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def load_fixture() -> Callable[[str], Any]:
    def _load(relative_path: str) -> Any:
        path = FIXTURES_DIR / relative_path
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    return _load


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Per-test session wrapped in a rolled-back outer transaction.

    NullPool + dispose: asyncpg connections must not outlive the pytest-asyncio
    event loop (avoids "Future attached to a different loop").
    """
    url = os.environ.get("TEST_DATABASE_URL") or resolve_database_url()
    engine = create_async_engine(
        url,
        poolclass=NullPool,
    )
    try:
        connection = await engine.connect()
    except OSError as exc:
        await engine.dispose()
        pytest.skip(
            f"Test database unreachable ({exc}). "
            "Bring up Postgres (`docker compose up db`), and for host-side pytest "
            "use localhost in DATABASE_URL or set TEST_DATABASE_URL="
            "postgresql+asyncpg://nouri:nouri@localhost:5432/nouri"
        )
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> UserProfile:
    return await make_user(db_session, email="patri@nouri.app")


@pytest.fixture
async def pro_user(db_session: AsyncSession) -> UserProfile:
    return await make_user(
        db_session,
        email="pro@nouri.app",
        tier=UserTier.PRO,
        display_name="Pro User",
    )


@pytest.fixture
async def other_user(db_session: AsyncSession) -> UserProfile:
    return await make_user(
        db_session,
        email="other@nouri.app",
        display_name="Other User",
    )


def _as_current_user(profile: UserProfile) -> CurrentUser:
    email = getattr(profile, "_test_email", "test@nouri.app")
    return CurrentUser(
        id=profile.id,
        email=email,
        tier=profile.tier.value if hasattr(profile.tier, "value") else str(profile.tier),
    )


@pytest.fixture
async def client(
    db_session: AsyncSession, test_user: UserProfile
) -> AsyncIterator[AsyncClient]:
    """Authenticated ASGI client bound to the rolled-back test session."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def override_user() -> CurrentUser:
        return _as_current_user(test_user)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def anon_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Client with DB override but no auth override — expects 401."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def auth_as(
    db_session: AsyncSession,
) -> Callable[[UserProfile], None]:
    """Switch the authenticated user mid-test."""

    def _auth(profile: UserProfile) -> None:
        async def override_user() -> CurrentUser:
            return _as_current_user(profile)

        app.dependency_overrides[get_current_user] = override_user

    return _auth


@pytest.fixture
def mock_voyage(monkeypatch: pytest.MonkeyPatch) -> list[list[float]]:
    """Deterministic 1024-dim fake embeddings — never call Voyage."""
    vector = [0.01] * 1024
    calls: list[list[float]] = []

    class FakeVoyageClient:
        def embed(
            self,
            texts: list[str],
            model: str | None = None,
            input_type: str | None = None,
        ) -> Any:
            class Result:
                embeddings = [vector for _ in texts]

            calls.append(vector)
            return Result()

    monkeypatch.setattr(
        "search.recipe_search_service.voyageai.Client",
        lambda api_key=None: FakeVoyageClient(),
    )
    return calls


@pytest.fixture
def mock_anthropic(monkeypatch: pytest.MonkeyPatch, load_fixture: Callable[[str], Any]):
    """Replace AnthropicClient.complete with fixture-driven responses."""
    queue: list[Any] = []

    class FakeMessage:
        def __init__(self, tool_name: str, payload: dict[str, Any]) -> None:
            self.content = [
                type(
                    "Block",
                    (),
                    {"type": "tool_use", "name": tool_name, "input": payload},
                )()
            ]

    class FakeAnthropicClient:
        async def complete(self, *args: Any, **kwargs: Any) -> Any:
            if not queue:
                raise AssertionError("mock_anthropic queue exhausted")
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    def enqueue_tool(tool_name: str, fixture_path: str) -> None:
        payload = load_fixture(fixture_path)
        queue.append(FakeMessage(tool_name, payload))

    def enqueue_message(message: Any) -> None:
        queue.append(message)

    monkeypatch.setattr("agent.client.AnthropicClient", FakeAnthropicClient)
    monkeypatch.setattr(
        "agent.plan_generator.AnthropicClient", FakeAnthropicClient
    )
    monkeypatch.setattr(
        "agent.recipe_generator.AnthropicClient", FakeAnthropicClient
    )
    monkeypatch.setattr(
        "agent.recipe_importer.AnthropicClient", FakeAnthropicClient
    )

    return type(
        "MockAnthropic",
        (),
        {
            "enqueue_tool": staticmethod(enqueue_tool),
            "enqueue_message": staticmethod(enqueue_message),
            "queue": queue,
        },
    )()


# Re-export factories for `from tests.conftest import make_plan` convenience
__all__ = [
    "make_user",
    "make_recipe",
    "make_plan",
    "make_exclusion",
]
