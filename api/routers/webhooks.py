"""Stripe webhook — docs/4_API_DESIGN.yaml POST /webhooks/stripe (no JWT).

TEST_PLAN §4.5: checkout.session.completed → pro; subscription.deleted → free.
Event ids are claimed in processed_stripe_events in the same transaction as
the tier write. A processing error rolls that insert back so Stripe can retry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from config import settings
from db.models import UserProfile, UserTier
from db.session import get_db
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from services.profile_service import ProfileService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

router = APIRouter()
_db = Depends(get_db)

_PRO_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.updated",
    }
)
_FREE_EVENTS = frozenset(
    {
        "customer.subscription.deleted",
        "invoice.payment_failed",
    }
)
_ORDERED_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }
)


def _event_type(event: Any) -> str | None:
    if isinstance(event, dict):
        raw = event.get("type")
        return raw if isinstance(raw, str) else None
    raw = getattr(event, "type", None)
    return raw if isinstance(raw, str) else None


def _event_id(event: Any) -> str | None:
    if isinstance(event, dict):
        raw = event.get("id")
    else:
        raw = getattr(event, "id", None)
    if isinstance(raw, str) and raw:
        return raw
    return None


def _event_object(event: Any) -> Any:
    if isinstance(event, dict):
        data = event.get("data") or {}
        if isinstance(data, dict):
            return data.get("object")
        return None
    data = getattr(event, "data", None)
    return getattr(data, "object", None) if data is not None else None


def _field(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _unix_datetime(raw: object) -> datetime | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _ordering_at(event: Any) -> datetime | None:
    """Subscription current_period_start, otherwise the event's created time."""
    stamped = _unix_datetime(_field(_event_object(event), "current_period_start"))
    if stamped is not None:
        return stamped
    return _unix_datetime(_field(event, "created"))


def _user_id_from_stripe_object(obj: Any) -> UUID | None:
    if obj is None:
        return None
    metadata: Any
    client_ref: Any
    if isinstance(obj, dict):
        metadata = obj.get("metadata") or {}
        client_ref = obj.get("client_reference_id")
    else:
        metadata = getattr(obj, "metadata", None) or {}
        client_ref = getattr(obj, "client_reference_id", None)
    raw = None
    if isinstance(metadata, dict):
        raw = metadata.get("user_id")
    if raw is None:
        raw = client_ref
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _tier_for_event(event: Any, event_type: str) -> UserTier | None:
    if event_type in _PRO_EVENTS:
        if event_type == "customer.subscription.updated":
            status_obj = _field(_event_object(event), "status")
            if status_obj in ("canceled", "unpaid", "incomplete_expired"):
                return UserTier.FREE
        return UserTier.PRO
    if event_type in _FREE_EVENTS:
        return UserTier.FREE
    return None


async def _claim_event(db: AsyncSession, event_id: str, event_type: str) -> bool:
    result = await db.execute(
        text(
            """
            INSERT INTO processed_stripe_events (event_id, type)
            VALUES (:event_id, :type)
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
            """
        ),
        {"event_id": event_id, "type": event_type},
    )
    return result.scalar_one_or_none() is not None


async def _apply_event(event: Any, event_type: str, db: AsyncSession) -> None:
    user_id = _user_id_from_stripe_object(_event_object(event))
    tier = _tier_for_event(event, event_type)
    if tier is None:
        logger.info("stripe_webhook_ignored", event_type=event_type)
        return
    if user_id is None:
        logger.warning("stripe_webhook_missing_user_id", event_type=event_type)
        return

    incoming = _ordering_at(event) if event_type in _ORDERED_EVENTS else None
    if event_type in _ORDERED_EVENTS and incoming is not None:
        profile = await db.get(UserProfile, user_id)
        stored = (
            profile.stripe_subscription_event_at if profile is not None else None
        )
        if stored is not None and incoming < stored:
            logger.info(
                "stale stripe event ignored",
                event_type=event_type,
                user_id=str(user_id),
            )
            return

    await ProfileService().set_tier(user_id, tier, db)
    if incoming is None:
        return
    profile = await db.get(UserProfile, user_id)
    if profile is None:
        return
    profile.stripe_subscription_event_at = incoming
    await db.flush()


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = _db,
) -> JSONResponse:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_SIGNATURE",
                    "message": "Missing Stripe-Signature header",
                }
            },
        )

    try:
        import stripe

        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret,
        )
    except Exception as exc:
        logger.warning("stripe_webhook_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_SIGNATURE",
                    "message": "Invalid Stripe webhook signature",
                }
            },
        ) from exc

    event_type = _event_type(event)
    event_id = _event_id(event)
    logger.info("stripe_webhook_received", event_type=event_type, event_id=event_id)
    if event_id is None or event_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_EVENT",
                    "message": "Stripe event is missing id or type",
                }
            },
        )

    async with db.begin_nested():
        claimed = await _claim_event(db, event_id, event_type)
        if not claimed:
            logger.info(
                "stripe_webhook_duplicate",
                event_id=event_id,
                event_type=event_type,
            )
        else:
            await _apply_event(event, event_type, db)

    return JSONResponse(status_code=200, content={"received": True})
