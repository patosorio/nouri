"""Stripe webhook helpers and checkout → tier (TEST_PLAN §4.5)."""

from __future__ import annotations

from uuid import uuid4

import pytest
import stripe
from db.models import UserTier
from httpx import AsyncClient
from routers.webhooks import _user_id_from_stripe_object
from services.profile_service import ProfileService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_user


def test_user_id_from_metadata() -> None:
    uid = uuid4()
    assert _user_id_from_stripe_object({"metadata": {"user_id": str(uid)}}) == uid


def test_user_id_from_client_reference_id() -> None:
    uid = uuid4()
    assert _user_id_from_stripe_object({"client_reference_id": str(uid)}) == uid


def test_user_id_invalid_returns_none() -> None:
    assert _user_id_from_stripe_object({"metadata": {"user_id": "not-a-uuid"}}) is None


@pytest.mark.asyncio
async def test_checkout_completed_sets_tier_pro(
    anon_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session, tier=UserTier.FREE)
    event = {
        "id": "evt_checkout_pro",
        "type": "checkout.session.completed",
        "created": 1_700_000_000,
        "data": {"object": {"metadata": {"user_id": str(user.id)}}},
    }
    monkeypatch.setattr(
        stripe.Webhook, "construct_event", lambda *args, **kwargs: event
    )
    response = await anon_client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=test"},
    )
    assert response.status_code == 200
    await db_session.refresh(user)
    assert user.tier == UserTier.PRO


@pytest.mark.asyncio
async def test_subscription_deleted_sets_tier_free(
    anon_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session, tier=UserTier.PRO)
    event = {
        "id": "evt_subscription_deleted",
        "type": "customer.subscription.deleted",
        "created": 1_700_000_100,
        "data": {"object": {"metadata": {"user_id": str(user.id)}}},
    }
    monkeypatch.setattr(
        stripe.Webhook, "construct_event", lambda *args, **kwargs: event
    )
    response = await anon_client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=test"},
    )
    assert response.status_code == 200
    await db_session.refresh(user)
    assert user.tier == UserTier.FREE


@pytest.mark.asyncio
async def test_stripe_webhook_missing_signature_400(anon_client: AsyncClient) -> None:
    response = await anon_client.post("/api/v1/webhooks/stripe", content=b"{}")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_stripe_webhook_bad_signature_400(
    anon_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _reject(*_args: object, **_kwargs: object) -> None:
        raise ValueError("bad signature")

    monkeypatch.setattr(stripe.Webhook, "construct_event", _reject)
    response = await anon_client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=bad"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_same_stripe_event_is_processed_once(
    anon_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session, tier=UserTier.FREE)
    event = {
        "id": "evt_once",
        "type": "checkout.session.completed",
        "created": 1_700_000_200,
        "data": {"object": {"metadata": {"user_id": str(user.id)}}},
    }
    monkeypatch.setattr(
        stripe.Webhook, "construct_event", lambda *args, **kwargs: event
    )
    calls = {"n": 0}
    real = ProfileService.set_tier

    async def _counted(
        self: ProfileService, *args: object, **kwargs: object
    ) -> object:
        calls["n"] += 1
        return await real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ProfileService, "set_tier", _counted)
    for _ in range(2):
        response = await anon_client.post(
            "/api/v1/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=test"},
        )
        assert response.status_code == 200
    assert calls["n"] == 1
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM processed_stripe_events WHERE event_id = 'evt_once'"
        )
    )
    assert count == 1


@pytest.mark.asyncio
async def test_older_subscription_update_does_not_downgrade(
    anon_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session, tier=UserTier.FREE)
    events = [
        {
            "id": "evt_newer",
            "type": "customer.subscription.updated",
            "created": 2_000,
            "data": {
                "object": {
                    "metadata": {"user_id": str(user.id)},
                    "status": "active",
                    "current_period_start": 2_000,
                }
            },
        },
        {
            "id": "evt_older",
            "type": "customer.subscription.updated",
            "created": 1_000,
            "data": {
                "object": {
                    "metadata": {"user_id": str(user.id)},
                    "status": "canceled",
                    "current_period_start": 1_000,
                }
            },
        },
    ]
    pending = iter(events)

    def _next(*_args: object, **_kwargs: object) -> dict[str, object]:
        return next(pending)

    monkeypatch.setattr(stripe.Webhook, "construct_event", _next)
    for _ in range(2):
        response = await anon_client.post(
            "/api/v1/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=test"},
        )
        assert response.status_code == 200
    await db_session.refresh(user)
    assert user.tier == UserTier.PRO


@pytest.mark.asyncio
async def test_processing_error_leaves_no_processed_event(
    anon_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session, tier=UserTier.FREE)
    event = {
        "id": "evt_fails",
        "type": "checkout.session.completed",
        "created": 1_700_000_300,
        "data": {"object": {"metadata": {"user_id": str(user.id)}}},
    }
    monkeypatch.setattr(
        stripe.Webhook, "construct_event", lambda *args, **kwargs: event
    )

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("tier write failed")

    monkeypatch.setattr(ProfileService, "set_tier", _boom)
    with pytest.raises(RuntimeError, match="tier write failed"):
        await anon_client.post(
            "/api/v1/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=test"},
        )
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM processed_stripe_events WHERE event_id = 'evt_fails'"
        )
    )
    assert count == 0

