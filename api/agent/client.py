"""Anthropic async client wrapper — docs/7_TECH_SPEC.md §5.1."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

import anthropic
import httpx
import structlog
from anthropic.types import Message, ToolUseBlock
from config import settings
from exceptions import LlmDeadlineError, SpendLimitExceeded
from services.llm_usage import LlmCallDraft, LlmUsageService, estimate_cost_usd

logger = structlog.get_logger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_MAX_ATTEMPTS = 3
# Shorter than this cannot finish a useful request before the job deadline.
MIN_USEFUL_ATTEMPT_SECONDS = 60.0
_CONNECT_TIMEOUT_SECONDS = 30.0


def cached_system_blocks(text: str) -> list[dict[str, Any]]:
    # Prefixes under the model's minimum cacheable length (~1024 tokens on
    # Sonnet) are not cached; that's acceptable.
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def with_cached_last_tool(tools: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    copied = [dict(tool) for tool in tools]
    if copied:
        copied[-1]["cache_control"] = {"type": "ephemeral"}
    return copied


def attempt_fits(deadline: float | None, *, now: float | None = None) -> bool:
    """True when another model call can still finish before deadline."""
    if deadline is None:
        return True
    current = time.monotonic() if now is None else now
    return deadline - current >= MIN_USEFUL_ATTEMPT_SECONDS


class AnthropicClient:
    """Wraps anthropic.AsyncAnthropic. Never expose the raw client outside this module."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        sdk_client: Any | None = None,
        usage: LlmUsageService | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if sdk_client is not None:
            self._client = sdk_client
        else:
            timeout = httpx.Timeout(
                settings.anthropic_http_timeout_seconds,
                connect=_CONNECT_TIMEOUT_SECONDS,
            )
            # App-level retry is the only retry. max_retries=0 avoids a hidden extra HTTP call.
            self._client = anthropic.AsyncAnthropic(
                api_key=api_key or settings.anthropic_api_key,
                timeout=timeout,
                max_retries=0,
            )
        self._usage = usage or LlmUsageService()
        self._clock = clock or time.monotonic
        self.last_message: Message | None = None
        self.last_stop_reason: str | None = None

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        system: str | Sequence[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        trace_id: str | None = None,
        deadline: float | None = None,
        user_id: UUID | None = None,
        job_id: UUID | None = None,
        task: str | None = None,
    ) -> Message:
        kwargs = self._build_kwargs(
            messages=messages,
            model=model,
            tools=tools,
            max_tokens=max_tokens,
            system=system,
            tool_choice=tool_choice,
        )
        started = time.perf_counter()
        message = await self._with_retry(
            kwargs,
            model=model,
            deadline=deadline,
            user_id=user_id,
            job_id=job_id,
            task=task,
            trace_id=trace_id,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._record_and_log(
            message, model=model, duration_ms=duration_ms, trace_id=trace_id
        )
        return message

    async def stream_text(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        system: str | Sequence[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        trace_id: str | None = None,
        deadline: float | None = None,
        user_id: UUID | None = None,
        job_id: UUID | None = None,
        task: str | None = None,
    ) -> AsyncIterator[str | ToolUseBlock]:
        """Yield text deltas then completed ToolUseBlock objects for one turn."""
        kwargs = self._build_kwargs(
            messages=messages,
            model=model,
            tools=tools,
            max_tokens=max_tokens,
            system=system,
            tool_choice=tool_choice,
        )
        started = time.perf_counter()
        attempt = 0
        while True:
            attempt += 1
            await self._enforce_spend_limit(
                model=model,
                attempt=attempt,
                user_id=user_id,
                job_id=job_id,
                task=task,
            )
            timeout_s = self._timeout_seconds(deadline)
            attempt_started = time.perf_counter()
            try:
                async with self._client.messages.stream(
                    **kwargs, timeout=timeout_s
                ) as stream:
                    async for text in stream.text_stream:
                        yield text
                    message = await stream.get_final_message()
                duration_ms = int((time.perf_counter() - started) * 1000)
                self._record_and_log(
                    message, model=model, duration_ms=duration_ms, trace_id=trace_id
                )
                await self._log_attempt(
                    model=model,
                    attempt=attempt,
                    outcome="ok",
                    latency_ms=int((time.perf_counter() - attempt_started) * 1000),
                    http_status=None,
                    message=message,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                for block in message.content:
                    if block.type == "tool_use":
                        yield block
                return
            except anthropic.APITimeoutError as exc:
                await self._log_attempt(
                    model=model,
                    attempt=attempt,
                    outcome="timeout",
                    latency_ms=int((time.perf_counter() - attempt_started) * 1000),
                    http_status=None,
                    message=None,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                raise LlmDeadlineError("Model call timed out") from exc
            except TimeoutError as exc:
                await self._log_attempt(
                    model=model,
                    attempt=attempt,
                    outcome="timeout",
                    latency_ms=int((time.perf_counter() - attempt_started) * 1000),
                    http_status=None,
                    message=None,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                raise LlmDeadlineError("Model call timed out") from exc
            except anthropic.APIStatusError as exc:
                await self._log_attempt(
                    model=model,
                    attempt=attempt,
                    outcome="http_error",
                    latency_ms=int((time.perf_counter() - attempt_started) * 1000),
                    http_status=exc.status_code,
                    message=None,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                if not self._is_retryable(exc) or not self._retry_fits(
                    deadline, attempt
                ):
                    raise
                delay = _BACKOFF_SECONDS[attempt - 1]
                logger.warning(
                    "anthropic_retry",
                    model=model,
                    status_code=exc.status_code,
                    attempt=attempt,
                    delay_s=delay,
                    trace_id=trace_id,
                )
                await asyncio.sleep(delay)
            except anthropic.APIConnectionError:
                await self._log_attempt(
                    model=model,
                    attempt=attempt,
                    outcome="http_error",
                    latency_ms=int((time.perf_counter() - attempt_started) * 1000),
                    http_status=None,
                    message=None,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                raise

    def _build_kwargs(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        model: str,
        tools: Sequence[dict[str, Any]] | None,
        max_tokens: int,
        system: str | Sequence[dict[str, Any]] | None,
        tool_choice: dict[str, Any] | str | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "max_tokens": max_tokens,
        }
        if system is not None:
            kwargs["system"] = system
        if tools is not None:
            kwargs["tools"] = list(tools)
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return kwargs

    async def _with_retry(
        self,
        create_kwargs: dict[str, Any],
        *,
        model: str,
        deadline: float | None,
        user_id: UUID | None,
        job_id: UUID | None,
        task: str | None,
        trace_id: str | None,
    ) -> Message:
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            await self._enforce_spend_limit(
                model=model,
                attempt=attempt,
                user_id=user_id,
                job_id=job_id,
                task=task,
            )
            timeout_s = self._timeout_seconds(deadline)
            attempt_started = time.perf_counter()
            try:
                message = await self._client.messages.create(
                    **create_kwargs, timeout=timeout_s
                )
            except anthropic.APITimeoutError as exc:
                await self._log_http_failure(
                    model=model,
                    attempt=attempt,
                    outcome="timeout",
                    started=attempt_started,
                    http_status=None,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                raise LlmDeadlineError("Model call timed out") from exc
            except TimeoutError as exc:
                await self._log_http_failure(
                    model=model,
                    attempt=attempt,
                    outcome="timeout",
                    started=attempt_started,
                    http_status=None,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                raise LlmDeadlineError("Model call timed out") from exc
            except anthropic.APIStatusError as exc:
                last_error = exc
                await self._log_http_failure(
                    model=model,
                    attempt=attempt,
                    outcome="http_error",
                    started=attempt_started,
                    http_status=exc.status_code,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                if not self._is_retryable(exc) or not self._retry_fits(
                    deadline, attempt
                ):
                    raise
                delay = _BACKOFF_SECONDS[attempt - 1]
                logger.warning(
                    "anthropic_retry",
                    model=model,
                    status_code=exc.status_code,
                    attempt=attempt,
                    delay_s=delay,
                    trace_id=trace_id,
                )
                await asyncio.sleep(delay)
                continue
            except anthropic.APIConnectionError:
                await self._log_http_failure(
                    model=model,
                    attempt=attempt,
                    outcome="http_error",
                    started=attempt_started,
                    http_status=None,
                    user_id=user_id,
                    job_id=job_id,
                    task=task,
                )
                raise
            await self._log_attempt(
                model=model,
                attempt=attempt,
                outcome="ok",
                latency_ms=int((time.perf_counter() - attempt_started) * 1000),
                http_status=None,
                message=message,
                user_id=user_id,
                job_id=job_id,
                task=task,
            )
            return message
        assert last_error is not None
        raise last_error

    def _timeout_seconds(self, deadline: float | None) -> float:
        configured = float(settings.anthropic_http_timeout_seconds)
        if deadline is None:
            return configured
        remaining = deadline - self._clock()
        if remaining < MIN_USEFUL_ATTEMPT_SECONDS:
            raise LlmDeadlineError(
                "Not enough time left before the job deadline for a model call"
            )
        return min(configured, remaining)

    def _retry_fits(self, deadline: float | None, attempt: int) -> bool:
        if attempt >= _MAX_ATTEMPTS:
            return False
        if deadline is None:
            return True
        delay = _BACKOFF_SECONDS[attempt - 1]
        remaining_after = deadline - self._clock() - delay
        return remaining_after >= MIN_USEFUL_ATTEMPT_SECONDS

    async def _enforce_spend_limit(
        self,
        *,
        model: str,
        attempt: int,
        user_id: UUID | None,
        job_id: UUID | None,
        task: str | None,
    ) -> None:
        limit = settings.llm_daily_spend_limit_usd
        if limit is None:
            return
        try:
            spent = Decimal(str(await self._usage.today_spend_usd()))
        except Exception as exc:
            logger.exception("llm_spend_check_failed", model=model)
            await self._log_attempt(
                model=model,
                attempt=attempt,
                outcome="refused_budget",
                latency_ms=0,
                http_status=None,
                message=None,
                user_id=user_id,
                job_id=job_id,
                task=task,
            )
            raise SpendLimitExceeded("Could not verify daily LLM spend") from exc
        if spent >= Decimal(str(limit)):
            await self._log_attempt(
                model=model,
                attempt=attempt,
                outcome="refused_budget",
                latency_ms=0,
                http_status=None,
                message=None,
                user_id=user_id,
                job_id=job_id,
                task=task,
            )
            raise SpendLimitExceeded("Daily LLM spend limit reached")

    async def _log_http_failure(
        self,
        *,
        model: str,
        attempt: int,
        outcome: str,
        started: float,
        http_status: int | None,
        user_id: UUID | None,
        job_id: UUID | None,
        task: str | None,
    ) -> None:
        await self._log_attempt(
            model=model,
            attempt=attempt,
            outcome=outcome,
            latency_ms=int((time.perf_counter() - started) * 1000),
            http_status=http_status,
            message=None,
            user_id=user_id,
            job_id=job_id,
            task=task,
        )

    async def _log_attempt(
        self,
        *,
        model: str,
        attempt: int,
        outcome: str,
        latency_ms: int,
        http_status: int | None,
        message: Any | None,
        user_id: UUID | None,
        job_id: UUID | None,
        task: str | None,
    ) -> None:
        try:
            input_tokens, output_tokens, cache_write, cache_read = _usage_tokens(
                message
            )
            draft = LlmCallDraft(
                user_id=user_id,
                job_id=job_id,
                task=task or "unknown",
                model=model,
                attempt=attempt,
                outcome=outcome,
                http_status=http_status,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_input_tokens=cache_write,
                cache_read_input_tokens=cache_read,
                estimated_cost_usd=estimate_cost_usd(
                    model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_creation_input_tokens=cache_write,
                    cache_read_input_tokens=cache_read,
                ),
            )
            await self._usage.record(draft)
        except Exception:
            logger.exception(
                "llm_call_log_failed",
                model=model,
                outcome=outcome,
                attempt=attempt,
            )

    @staticmethod
    def _is_retryable(exc: anthropic.APIStatusError) -> bool:
        return exc.status_code in _RETRYABLE_STATUS

    def _record_and_log(
        self,
        message: Message,
        *,
        model: str,
        duration_ms: int,
        trace_id: str | None,
    ) -> None:
        self.last_message = message
        self.last_stop_reason = message.stop_reason
        usage = message.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        logger.info(
            "anthropic_response",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=message.stop_reason,
            duration_ms=duration_ms,
            trace_id=trace_id,
        )
        total = input_tokens + output_tokens
        if total >= settings.anthropic_token_alert_threshold:
            logger.warning(
                "anthropic_token_alert",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total,
                threshold=settings.anthropic_token_alert_threshold,
                trace_id=trace_id,
            )


def _usage_tokens(message: Any | None) -> tuple[int, int, int, int]:
    usage = getattr(message, "usage", None) if message is not None else None
    if usage is None:
        return 0, 0, 0, 0

    def _token(name: str) -> int:
        value = getattr(usage, name, None)
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    return (
        _token("input_tokens"),
        _token("output_tokens"),
        _token("cache_creation_input_tokens"),
        _token("cache_read_input_tokens"),
    )
