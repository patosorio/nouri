"""Anthropic async client wrapper — docs/7_TECH_SPEC.md §5.1."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

import anthropic
import httpx
import structlog
from anthropic.types import Message, ToolUseBlock

from config import settings

logger = structlog.get_logger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_MAX_ATTEMPTS = 3
_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=30.0)


class AnthropicClient:
    """Wraps anthropic.AsyncAnthropic. Never expose the raw client outside this module."""

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or settings.anthropic_api_key,
            timeout=_HTTP_TIMEOUT,
        )
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
            lambda: self._client.messages.create(**kwargs),
            model=model,
            trace_id=trace_id,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._record_and_log(message, model=model, duration_ms=duration_ms, trace_id=trace_id)
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
            try:
                async with self._client.messages.stream(**kwargs) as stream:
                    async for text in stream.text_stream:
                        yield text
                    message = await stream.get_final_message()
                duration_ms = int((time.perf_counter() - started) * 1000)
                self._record_and_log(
                    message, model=model, duration_ms=duration_ms, trace_id=trace_id
                )
                for block in message.content:
                    if block.type == "tool_use":
                        yield block
                return
            except anthropic.APIStatusError as exc:
                if not self._is_retryable(exc) or attempt >= _MAX_ATTEMPTS:
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
        call: Any,
        *,
        model: str,
        trace_id: str | None,
    ) -> Message:
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await call()
            except anthropic.APIStatusError as exc:
                last_error = exc
                if not self._is_retryable(exc) or attempt >= _MAX_ATTEMPTS:
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
        assert last_error is not None
        raise last_error

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
        logger.info(
            "anthropic_response",
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            stop_reason=message.stop_reason,
            duration_ms=duration_ms,
            trace_id=trace_id,
        )
