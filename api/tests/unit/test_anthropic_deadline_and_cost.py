"""Anthropic deadline, per-attempt cost rows, and the spend breaker. No network."""

from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from typing import Self
from uuid import uuid4

import config
import httpx
import pytest
from agent.client import AnthropicClient
from agent.plan_generator import PlanGeneratorAgent
from config import settings
from exceptions import PlanGenerationFailedError, SpendLimitExceeded
from services.llm_usage import LlmCallDraft


class MemoryUsage:
    def __init__(self, spent: Decimal = Decimal(0)) -> None:
        self.rows: list[LlmCallDraft] = []
        self.spent = spent
        self.spend_checks = 0

    async def record(self, draft: LlmCallDraft) -> None:
        self.rows.append(draft)

    async def today_spend_usd(self) -> Decimal:
        self.spend_checks += 1
        return self.spent


def _status_error(code: int) -> Exception:
    import anthropic

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(code, request=request)
    return anthropic.APIStatusError("rate limited", response=response, body=None)


def _usage_message() -> SimpleNamespace:
    return SimpleNamespace(
        content=[],
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_creation_input_tokens=1_000_000,
            cache_read_input_tokens=1_000_000,
        ),
    )


def test_sdk_client_disables_hidden_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeSDK:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("agent.client.anthropic.AsyncAnthropic", FakeSDK)
    AnthropicClient(api_key="test-key")
    assert captured["max_retries"] == 0


@pytest.mark.asyncio
async def test_deadline_skips_retry_and_caps_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic

    monkeypatch.setattr(settings, "anthropic_http_timeout_seconds", 420.0)
    clock = {"t": 1_000_000.0}
    timeouts: list[float] = []

    class Messages:
        async def create(self, **kwargs: object) -> object:
            timeout = kwargs["timeout"]
            assert isinstance(timeout, (int, float))
            timeouts.append(float(timeout))
            raise _status_error(429)

    client = AnthropicClient(
        sdk_client=SimpleNamespace(messages=Messages()),
        usage=MemoryUsage(),
        clock=lambda: clock["t"],
    )
    from agent.client import MIN_USEFUL_ATTEMPT_SECONDS

    remaining = MIN_USEFUL_ATTEMPT_SECONDS + 0.5
    deadline = clock["t"] + remaining
    with pytest.raises(anthropic.APIStatusError):
        await client.complete(
            [{"role": "user", "content": "plan"}],
            model="claude-test",
            deadline=deadline,
            task="plan_generation",
        )

    assert len(timeouts) == 1
    assert timeouts[0] == min(420.0, remaining)


@pytest.mark.asyncio
async def test_second_parse_skipped_when_deadline_cannot_fit() -> None:
    calls: list[int] = []

    class FakeClient:
        async def complete(self, *_args: object, **_kwargs: object) -> object:
            calls.append(1)
            return SimpleNamespace(content=[], stop_reason="end_turn")

    agent = PlanGeneratorAgent(client=FakeClient())  # type: ignore[arg-type]
    with pytest.raises(PlanGenerationFailedError):
        await agent._call_and_parse(
            system_prompt="system",
            user_prompt="user",
            trace_id=None,
            deadline=time.monotonic() - 5,
        )
    assert calls == [1]


@pytest.mark.asyncio
async def test_llm_call_row_usage_and_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_daily_spend_limit_usd", None)
    monkeypatch.setattr(config, "LLM_TOKEN_PRICES_USD_PER_MILLION", {})
    store = MemoryUsage()
    messages = _scripted_messages([_usage_message(), _usage_message()])
    user_id = uuid4()
    job_id = uuid4()
    client = AnthropicClient(
        sdk_client=SimpleNamespace(messages=messages),
        usage=store,
    )

    await client.complete(
        [{"role": "user", "content": "plan"}],
        model="claude-test",
        user_id=user_id,
        job_id=job_id,
        task="plan_generation",
    )
    assert store.spend_checks == 0
    assert len(store.rows) == 1
    row = store.rows[0]
    assert row.outcome == "ok"
    assert row.user_id == user_id
    assert row.job_id == job_id
    assert row.task == "plan_generation"
    assert row.input_tokens == 1_000_000
    assert row.output_tokens == 1_000_000
    assert row.cache_creation_input_tokens == 1_000_000
    assert row.cache_read_input_tokens == 1_000_000
    assert row.estimated_cost_usd is None

    monkeypatch.setattr(
        config,
        "LLM_TOKEN_PRICES_USD_PER_MILLION",
        {
            "claude-test": {
                "input": 3,
                "output": 15,
                "cache_write": 6,
                "cache_read": 1,
            }
        },
    )
    await client.complete(
        [{"role": "user", "content": "plan"}],
        model="claude-test",
        task="plan_generation",
    )
    assert store.rows[1].estimated_cost_usd == Decimal(25)


@pytest.mark.asyncio
async def test_stream_writes_llm_call_row() -> None:
    message = _usage_message()

    class Stream:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        @property
        def text_stream(self) -> object:
            async def chunks():
                yield "hello"

            return chunks()

        async def get_final_message(self) -> SimpleNamespace:
            return message

    class Messages:
        def stream(self, **_kwargs: object) -> Stream:
            return Stream()

    store = MemoryUsage()
    client = AnthropicClient(
        sdk_client=SimpleNamespace(messages=Messages()),
        usage=store,
    )
    text = [
        item
        async for item in client.stream_text(
            [{"role": "user", "content": "hi"}],
            model="claude-test",
            task="conversation",
        )
    ]
    assert text == ["hello"]
    assert len(store.rows) == 1
    assert store.rows[0].outcome == "ok"
    assert store.rows[0].input_tokens == 1_000_000
    assert store.rows[0].estimated_cost_usd is None


@pytest.mark.asyncio
async def test_spend_breaker_refuses_without_calling_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_daily_spend_limit_usd", 1.0)
    store = MemoryUsage(spent=Decimal("1.0"))

    class Messages:
        async def create(self, **_kwargs: object) -> object:
            raise AssertionError("model client should not be called")

    client = AnthropicClient(
        sdk_client=SimpleNamespace(messages=Messages()),
        usage=store,
    )
    with pytest.raises(SpendLimitExceeded):
        await client.complete(
            [{"role": "user", "content": "plan"}],
            model="claude-test",
            task="plan_generation",
        )
    assert store.spend_checks == 1
    assert len(store.rows) == 1
    assert store.rows[0].outcome == "refused_budget"


def test_configured_models_have_a_price_entry() -> None:
    from config import LLM_TOKEN_PRICES_USD_PER_MILLION

    for model in (settings.anthropic_model_agent, settings.anthropic_model_fast):
        prices = LLM_TOKEN_PRICES_USD_PER_MILLION[model]
        assert set(prices) == {"input", "output", "cache_write", "cache_read"}
        assert all(value > 0 for value in prices.values())


@pytest.mark.asyncio
async def test_spend_breaker_trips_from_a_priced_usage_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A filled price table gives the fake row a cost, so the breaker can trip."""
    from services.llm_usage import estimate_cost_usd

    cost = estimate_cost_usd(
        settings.anthropic_model_agent,
        input_tokens=1_000_000,
        output_tokens=0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert cost == Decimal(3)
    haiku = estimate_cost_usd(
        settings.anthropic_model_fast,
        input_tokens=1_000_000,
        output_tokens=0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert haiku == Decimal("0.1")
    monkeypatch.setattr(settings, "llm_daily_spend_limit_usd", 1.0)
    store = MemoryUsage(spent=cost or Decimal(0))

    class Messages:
        async def create(self, **_kwargs: object) -> object:
            raise AssertionError("model client should not be called")

    client = AnthropicClient(
        sdk_client=SimpleNamespace(messages=Messages()),
        usage=store,
    )
    with pytest.raises(SpendLimitExceeded):
        await client.complete(
            [{"role": "user", "content": "plan"}],
            model=settings.anthropic_model_agent,
            task="plan_generation",
        )
    assert store.spend_checks == 1
    assert store.rows[0].outcome == "refused_budget"


class _ScriptedMessages:
    def __init__(self, replies: list[SimpleNamespace]) -> None:
        self._replies = list(replies)

    async def create(self, **_kwargs: object) -> SimpleNamespace:
        if not self._replies:
            raise AssertionError("scripted messages exhausted")
        return self._replies.pop(0)


def _scripted_messages(replies: list[SimpleNamespace]) -> _ScriptedMessages:
    return _ScriptedMessages(replies)
