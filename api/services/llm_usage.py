"""Persist Anthropic call usage. Logging failures must not break the model call."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import config
import structlog
from db.models import LlmCall
from sqlalchemy import func, select

logger = structlog.get_logger(__name__)

_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class LlmCallDraft:
    user_id: UUID | None
    job_id: UUID | None
    task: str
    model: str
    attempt: int
    outcome: str
    http_status: int | None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    estimated_cost_usd: Decimal | None


def estimate_cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
) -> Decimal | None:
    """USD for this call, or None when this model has no configured price."""
    prices = config.LLM_TOKEN_PRICES_USD_PER_MILLION.get(model)
    if not prices:
        return None
    components = {
        "input": input_tokens,
        "output": output_tokens,
        "cache_write": cache_creation_input_tokens,
        "cache_read": cache_read_input_tokens,
    }
    total = Decimal(0)
    priced = False
    for key, tokens in components.items():
        raw = prices.get(key)
        if raw is None:
            continue
        priced = True
        total += (Decimal(tokens) * Decimal(str(raw))) / _MILLION
    if not priced:
        return None
    return total


def _utc_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


class LlmUsageService:
    async def record(self, draft: LlmCallDraft) -> None:
        try:
            from db.session import async_session_factory

            async with async_session_factory() as db:
                db.add(
                    LlmCall(
                        user_id=draft.user_id,
                        job_id=draft.job_id,
                        task=draft.task,
                        model=draft.model,
                        attempt=draft.attempt,
                        outcome=draft.outcome,
                        http_status=draft.http_status,
                        latency_ms=draft.latency_ms,
                        input_tokens=draft.input_tokens,
                        output_tokens=draft.output_tokens,
                        cache_creation_input_tokens=draft.cache_creation_input_tokens,
                        cache_read_input_tokens=draft.cache_read_input_tokens,
                        estimated_cost_usd=draft.estimated_cost_usd,
                    )
                )
                await db.commit()
        except Exception:
            logger.exception(
                "llm_call_log_failed",
                model=draft.model,
                outcome=draft.outcome,
                task=draft.task,
            )

    async def today_spend_usd(self) -> Decimal:
        from db.session import async_session_factory

        start, end = _utc_day_bounds()
        async with async_session_factory() as db:
            result = await db.execute(
                select(
                    func.coalesce(func.sum(LlmCall.estimated_cost_usd), 0)
                ).where(
                    LlmCall.created_at >= start,
                    LlmCall.created_at < end,
                )
            )
            raw = result.scalar_one()
        return Decimal(str(raw or 0))
