"""Stripe webhook — docs/4_API_DESIGN.yaml POST /webhooks/stripe (no JWT)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from config import settings

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> JSONResponse:
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

    event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    logger.info("stripe_webhook_received", event_type=event_type)

    # Tier updates land when billing is fully wired; acknowledge all known events.
    handled = {
        "checkout.session.completed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_failed",
    }
    if event_type not in handled:
        logger.info("stripe_webhook_ignored", event_type=event_type)

    return JSONResponse(status_code=200, content={"received": True})
