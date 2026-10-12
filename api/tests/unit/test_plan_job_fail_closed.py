"""Plan jobs fail closed: no second paid model call after timeout or a saved parse."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from db.models import (
    CookingType,
    DietType,
    JobStatus,
    NotificationType,
    PlanItemSource,
    PlanSlot,
)
from exceptions import PlanGenerationFailedError, SpendLimitExceeded
from schemas.plans import GeneratedPlanData, GeneratedPlanDay, GeneratedPlanItem
from services.job_service import JobService
from services.plan_service import PlanService
from worker.handlers import handle_plan_generation, handle_recipe_nutrition_estimation
from worker.main import _process_job
from worker.retry_policy import PlanAttemptState, failure_should_retry

from tests.unit.test_plan_generator import _payload_3_day


def _job(
    job_type: str = "plan_generation",
    *,
    llm_output: object | None = None,
    started: bool = False,
    saved: bool = False,
) -> SimpleNamespace:
    job = SimpleNamespace(
        id=uuid4(),
        job_type=job_type,
        user_id=uuid4(),
        plan_id=uuid4(),
        attempts=1,
        max_attempts=3,
        payload={"trace_id": "t"},
        llm_output=llm_output,
    )
    job.plan_attempt_state = PlanAttemptState(
        model_call_started=started,
        llm_output_saved=saved,
    )
    return job


def test_plan_failure_retry_policy() -> None:
    assert failure_should_retry(_job(), timed_out=True, exc=None) is False
    assert (
        failure_should_retry(
            _job(llm_output={"days": []}),
            timed_out=False,
            exc=RuntimeError("fk"),
        )
        is False
    )
    assert (
        failure_should_retry(
            _job(started=True),
            timed_out=False,
            exc=RuntimeError("api"),
        )
        is False
    )
    assert (
        failure_should_retry(
            _job(),
            timed_out=False,
            exc=PlanGenerationFailedError("parse"),
        )
        is False
    )
    assert (
        failure_should_retry(
            _job(),
            timed_out=False,
            exc=SpendLimitExceeded("limit"),
        )
        is False
    )
    assert (
        failure_should_retry(
            _job(),
            timed_out=False,
            exc=ConnectionError("profile db"),
        )
        is True
    )
    nutrition = _job("recipe_nutrition_estimation")
    assert failure_should_retry(nutrition, timed_out=True, exc=None) is True
    assert (
        failure_should_retry(nutrition, timed_out=False, exc=RuntimeError("x"))
        is True
    )


class _Db:
    def __init__(self, job: SimpleNamespace) -> None:
        self._job = job

    async def get(self, _model: object, _job_id: object) -> SimpleNamespace:
        return self._job

    async def flush(self) -> None:
        return None


def _running(*, attempts: int, max_attempts: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        attempts=attempts,
        max_attempts=max_attempts,
        status=JobStatus.RUNNING,
        claimed_at=datetime.now(timezone.utc),
        scheduled_for=datetime.now(timezone.utc),
        error_message=None,
        completed_at=None,
    )


@pytest.mark.asyncio
async def test_pre_llm_error_requeues_until_max_attempts() -> None:
    first = _running(attempts=1, max_attempts=3)
    terminal = await JobService().mark_failed(
        uuid4(), "ConnectionError: profile db", _Db(first), retry=True
    )
    assert terminal is False
    assert first.status == JobStatus.PENDING
    assert first.claimed_at is None

    last = _running(attempts=3, max_attempts=3)
    terminal = await JobService().mark_failed(
        uuid4(), "ConnectionError: profile db", _Db(last), retry=True
    )
    assert terminal is True
    assert last.status == JobStatus.FAILED
    assert last.error_message == "ConnectionError: profile db"


@pytest.mark.asyncio
async def test_reap_stale_fails_at_max_attempts_and_requeues_below() -> None:
    exhausted = SimpleNamespace(
        attempts=3,
        max_attempts=3,
        status=JobStatus.RUNNING,
        claimed_at=datetime.now(timezone.utc),
        error_message=None,
        completed_at=None,
        updated_at=None,
        llm_output={"days": []},
        job_type="plan_generation",
    )
    resume = SimpleNamespace(
        attempts=2,
        max_attempts=3,
        status=JobStatus.RUNNING,
        claimed_at=datetime.now(timezone.utc),
        error_message=None,
        completed_at=None,
        updated_at=None,
        llm_output={"days": [{"day_number": 1}]},
        job_type="plan_generation",
    )
    with patch.object(
        JobService,
        "_select_stale",
        new=AsyncMock(return_value=[exhausted, resume]),
    ):
        count = await JobService().reap_stale(AsyncMock())
    assert count == 2
    assert exhausted.status == JobStatus.FAILED
    assert exhausted.error_message == "stale and out of attempts"
    assert resume.status == JobStatus.PENDING
    assert resume.claimed_at is None
    assert resume.llm_output == {"days": [{"day_number": 1}]}


@pytest.mark.asyncio
async def test_reap_stale_fails_plan_job_with_no_saved_output() -> None:
    claimed_at = datetime.now(timezone.utc)
    job = SimpleNamespace(
        attempts=1,
        max_attempts=3,
        status=JobStatus.RUNNING,
        claimed_at=claimed_at,
        error_message=None,
        completed_at=None,
        updated_at=None,
        llm_output=None,
        job_type="plan_generation",
    )
    with patch.object(
        JobService,
        "_select_stale",
        new=AsyncMock(return_value=[job]),
    ):
        count = await JobService().reap_stale(AsyncMock())
    assert count == 1
    assert job.status == JobStatus.FAILED
    assert job.completed_at is not None
    assert job.claimed_at is claimed_at
    assert job.error_message == (
        "stale plan job with no saved output; failing closed"
    )


@pytest.mark.asyncio
async def test_reap_stale_requeues_non_plan_job_with_no_saved_output() -> None:
    job = SimpleNamespace(
        attempts=1,
        max_attempts=3,
        status=JobStatus.RUNNING,
        claimed_at=datetime.now(timezone.utc),
        error_message=None,
        completed_at=None,
        updated_at=None,
        llm_output=None,
        job_type="recipe_generation",
    )
    with patch.object(
        JobService,
        "_select_stale",
        new=AsyncMock(return_value=[job]),
    ):
        count = await JobService().reap_stale(AsyncMock())
    assert count == 1
    assert job.status == JobStatus.PENDING
    assert job.claimed_at is None
    assert job.llm_output is None


class _Rows:
    def scalars(self) -> _Rows:
        return self

    def all(self) -> list[object]:
        return []


class _SessionCM:
    def __init__(self) -> None:
        self.session = AsyncMock()
        self.session.execute = AsyncMock(return_value=_Rows())

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


def _plan_job(**overrides: object) -> SimpleNamespace:
    job = SimpleNamespace(
        id=uuid4(),
        job_type="plan_generation",
        user_id=uuid4(),
        plan_id=uuid4(),
        attempts=1,
        max_attempts=3,
        payload={
            "params": {
                "duration_days": 3,
                "diet_type": "plant_based",
                "cooking_type": "cooked_100",
                "calorie_target": 2000,
            },
            "trace_id": "fail-closed",
        },
        llm_output=None,
    )
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=2000,
        protein_g_target=80,
        carbs_g_target=250,
        fat_g_target=70,
        fiber_g_target=30,
        diet_type=DietType.PLANT_BASED,
    )


class _Harness:
    def __init__(self) -> None:
        self.model_calls = 0
        self.failed: dict[str, object] = {}
        self.save_llm_output = AsyncMock()
        self.write_generated_plan = AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(),
                status=SimpleNamespace(value="active"),
                title="Week",
            )
        )
        self.save_generated_batch = AsyncMock(
            return_value=SimpleNamespace(recipes=[], inserted=[], id_remap={})
        )

    def install(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        complete_input: dict[str, object] | None,
        find_error: Exception | None = None,
    ) -> None:
        harness = self

        class FakeClient:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            async def complete(self, *_args: object, **_kwargs: object) -> object:
                harness.model_calls += 1
                if complete_input is None:
                    raise AssertionError("model should not be called")
                block = SimpleNamespace(
                    type="tool_use",
                    name="output_plan",
                    input=complete_input,
                )
                return SimpleNamespace(
                    content=[block],
                    stop_reason="tool_use",
                    usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                )

        monkeypatch.setattr("agent.plan_generator.AnthropicClient", FakeClient)
        search = MagicMock()
        if find_error is None:
            search.planning_candidates = AsyncMock(return_value=[])
        else:
            search.planning_candidates = AsyncMock(side_effect=find_error)
        monkeypatch.setattr(
            "agent.plan_generator.RecipeSearchService",
            MagicMock(return_value=search),
        )
        profile_service = MagicMock()
        profile_service.get_profile = AsyncMock(return_value=_profile())
        profile_service.get_exclusions = AsyncMock(return_value=[])
        monkeypatch.setattr(
            "agent.plan_generator.ProfileService",
            MagicMock(return_value=profile_service),
        )
        recipes = MagicMock()
        recipes.list_recipes = AsyncMock(return_value=SimpleNamespace(data=[]))
        recipes.load_plan_snapshots = AsyncMock(return_value={})
        monkeypatch.setattr(
            "agent.plan_generator.RecipeService",
            MagicMock(return_value=recipes),
        )
        monkeypatch.setattr(
            "worker.handlers.RecipeService",
            MagicMock(
                return_value=MagicMock(
                    save_generated_batch=self.save_generated_batch
                )
            ),
        )
        plan_service = MagicMock()
        plan_service.write_generated_plan = self.write_generated_plan
        plan_service._assert_recipes_owned = AsyncMock()
        monkeypatch.setattr(
            "worker.handlers.PlanService",
            MagicMock(return_value=plan_service),
        )
        monkeypatch.setattr(
            "worker.handlers.NotificationService",
            MagicMock(return_value=MagicMock(publish=AsyncMock())),
        )
        monkeypatch.setattr(JobService, "set_progress", AsyncMock())
        monkeypatch.setattr(JobService, "save_llm_output", self.save_llm_output)
        monkeypatch.setattr(JobService, "mark_complete", AsyncMock())
        monkeypatch.setattr(JobService, "enqueue", AsyncMock())
        monkeypatch.setattr(
            "worker.main.async_session_factory", lambda: _SessionCM()
        )

        async def fake_fail(*_args: object, **kwargs: object) -> None:
            harness.failed["retry"] = kwargs.get("retry")
            harness.failed["error"] = _args[1] if len(_args) > 1 else None

        monkeypatch.setattr("worker.main._fail_job", fake_fail)


@pytest.mark.asyncio
async def test_plan_timeout_is_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    failed: dict[str, object] = {}

    async def hang(*_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(30)

    async def fake_fail(*args: object, **kwargs: object) -> None:
        failed["retry"] = kwargs.get("retry")
        failed["error"] = args[1]

    monkeypatch.setattr("worker.main._dispatch", hang)
    monkeypatch.setattr("worker.main.MAX_JOB_RUNTIME_SECONDS", 0.05)
    monkeypatch.setattr("worker.main._fail_job", fake_fail)

    await _process_job(_plan_job(), "worker-test")

    assert failed["retry"] is False
    assert "will not be retried" in str(failed["error"])


@pytest.mark.asyncio
async def test_non_plan_timeout_still_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    failed: dict[str, object] = {}

    async def hang(*_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(30)

    async def fake_fail(*_args: object, **kwargs: object) -> None:
        failed["retry"] = kwargs.get("retry")

    monkeypatch.setattr("worker.main._dispatch", hang)
    monkeypatch.setattr("worker.main.MAX_JOB_RUNTIME_SECONDS", 0.05)
    monkeypatch.setattr("worker.main._fail_job", fake_fail)

    job = _plan_job(job_type="recipe_nutrition_estimation")
    await _process_job(job, "worker-test")
    assert failed["retry"] is True


@pytest.mark.asyncio
async def test_exception_after_llm_output_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.save_generated_batch = AsyncMock(
        side_effect=RuntimeError("insert violates foreign key constraint")
    )
    harness.install(monkeypatch, complete_input=_payload_3_day())

    await _process_job(_plan_job(), "worker-test")

    assert harness.model_calls == 1
    assert harness.save_llm_output.await_count == 1
    assert harness.failed["retry"] is False


@pytest.mark.asyncio
async def test_saved_llm_output_resumes_without_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.install(monkeypatch, complete_input=None)
    job = _plan_job(
        llm_output={"output": _payload_3_day(), "handles": {}}
    )

    await _process_job(job, "worker-test")

    assert harness.model_calls == 0
    assert harness.save_llm_output.await_count == 0
    assert harness.write_generated_plan.await_count == 1
    assert "retry" not in harness.failed


@pytest.mark.asyncio
async def test_pre_llm_worker_error_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.install(
        monkeypatch,
        complete_input=_payload_3_day(),
        find_error=ConnectionError("db down while loading candidates"),
    )

    await _process_job(_plan_job(), "worker-test")

    assert harness.model_calls == 0
    assert harness.save_llm_output.await_count == 0
    assert harness.failed["retry"] is True


@pytest.mark.asyncio
async def test_stale_plan_attempt_makes_at_most_two_model_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.install(monkeypatch, complete_input=_payload_3_day())

    class CrashBeforeCheckpoint:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def complete(self, *_args: object, **_kwargs: object) -> object:
            harness.model_calls += 1
            if harness.model_calls == 1:
                return SimpleNamespace(
                    content=[],
                    stop_reason="end_turn",
                    usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                )
            raise RuntimeError("worker died before checkpoint")

    monkeypatch.setattr(
        "agent.plan_generator.AnthropicClient", CrashBeforeCheckpoint
    )

    job = _plan_job()
    job.status = JobStatus.RUNNING
    job.claimed_at = datetime.now(timezone.utc)
    job.error_message = None
    job.completed_at = None
    job.updated_at = None

    await _process_job(job, "worker-test")

    assert job.llm_output is None
    assert harness.save_llm_output.await_count == 0

    with patch.object(
        JobService,
        "_select_stale",
        new=AsyncMock(return_value=[job]),
    ):
        await JobService().reap_stale(AsyncMock())

    assert job.status == JobStatus.FAILED
    assert job.completed_at is not None
    assert harness.model_calls <= 2


@pytest.mark.asyncio
async def test_unknown_handle_retries_once_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.install(
        monkeypatch,
        complete_input={
            "days": [
                {
                    "day_number": 1,
                    "items": [
                        {
                            "slot_type": "breakfast",
                            "recipe_id": "R99",
                            "recipe_title": "Nope",
                            "servings": 1,
                        }
                    ],
                }
            ],
            "generated_recipes": [],
        },
    )

    marked: list[bool] = []

    async def _mark_failed(*_args: object, **kwargs: object) -> bool:
        marked.append(bool(kwargs.get("retry", False)))
        return True

    monkeypatch.setattr(JobService, "mark_failed", _mark_failed)

    await _process_job(_plan_job(), "worker-test")

    assert harness.model_calls == 2
    assert harness.write_generated_plan.await_count == 0
    assert harness.save_generated_batch.await_count == 0
    assert marked == [False]


def _capture_session(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows())
    session.rollback = AsyncMock()

    class _Captured:
        async def __aenter__(self) -> AsyncMock:
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr("worker.main.async_session_factory", lambda: _Captured())
    return session


def _spy_failure(monkeypatch: pytest.MonkeyPatch) -> tuple[list[bool], list[str]]:
    marked: list[bool] = []
    published: list[str] = []

    async def mark_failed(*_args: object, **kwargs: object) -> bool:
        marked.append(bool(kwargs.get("retry", False)))
        return True

    async def publish(_user_id: object, kind: str, *_args: object, **_kwargs: object) -> None:
        published.append(kind)

    monkeypatch.setattr(JobService, "mark_failed", mark_failed)
    monkeypatch.setattr(
        "worker.handlers.NotificationService",
        MagicMock(return_value=MagicMock(publish=publish)),
    )
    return marked, published


@pytest.mark.asyncio
async def test_map_failure_rolls_back_and_is_not_requeued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.install(monkeypatch, complete_input=_payload_3_day())
    session = _capture_session(monkeypatch)
    marked, published = _spy_failure(monkeypatch)
    monkeypatch.setattr(
        "worker.handlers.map_generated_plan",
        MagicMock(
            side_effect=PlanGenerationFailedError(
                "Recipe x is not a saved or generated recipe"
            )
        ),
    )

    await _process_job(_plan_job(), "worker-test")

    assert marked == [False]
    assert published == [NotificationType.PLAN_FAILED.value]
    session.rollback.assert_awaited()
    assert harness.save_generated_batch.await_count == 0
    assert harness.write_generated_plan.await_count == 0
    assert harness.failed.get("retry") is not True


@pytest.mark.asyncio
async def test_write_ownership_failure_rolls_back_recipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.write_generated_plan = AsyncMock(
        side_effect=PlanGenerationFailedError("Recipe x not owned by user")
    )
    harness.install(monkeypatch, complete_input=_payload_3_day())
    session = _capture_session(monkeypatch)
    marked, published = _spy_failure(monkeypatch)

    await _process_job(_plan_job(), "worker-test")

    assert marked == [False]
    assert published == [NotificationType.PLAN_FAILED.value]
    session.rollback.assert_awaited()
    assert harness.save_generated_batch.await_count == 1
    assert harness.failed.get("retry") is not True


@pytest.mark.asyncio
async def test_foreign_saved_id_is_rejected_before_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign = uuid4()
    job = _plan_job()
    service_plan = GeneratedPlanData(
        days=[
            GeneratedPlanDay(
                day_number=1,
                items=[
                    GeneratedPlanItem(
                        slot_type=PlanSlot.LUNCH,
                        recipe_title="Theirs",
                        recipe_id=foreign,
                        item_source=PlanItemSource.SAVED_RECIPE,
                    )
                ],
            )
        ]
    )

    class _Owned:
        def scalars(self) -> _Owned:
            return self

        def all(self) -> list[object]:
            return []

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Owned())
    db.rollback = AsyncMock()
    save = AsyncMock()
    marked, published = _spy_failure(monkeypatch)
    monkeypatch.setattr(JobService, "set_progress", AsyncMock())
    monkeypatch.setattr(
        "worker.handlers.PlanGeneratorAgent",
        MagicMock(return_value=MagicMock(generate=AsyncMock(return_value=MagicMock()))),
    )
    monkeypatch.setattr(
        "worker.handlers.map_generated_plan",
        lambda *_args, **_kwargs: service_plan,
    )
    monkeypatch.setattr(
        "worker.handlers.RecipeService",
        MagicMock(return_value=MagicMock(save_generated_batch=save)),
    )

    with pytest.raises(PlanGenerationFailedError, match="not owned"):
        await handle_plan_generation(job, db)

    assert save.await_count == 0
    db.rollback.assert_awaited()
    assert marked == [False]
    assert published == [NotificationType.PLAN_FAILED.value]


@pytest.mark.asyncio
async def test_nutrition_unknown_pin_does_not_enqueue_estimator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin_id = uuid4()
    job = _plan_job()
    service_plan = GeneratedPlanData(
        days=[
            GeneratedPlanDay(
                day_number=1,
                items=[
                    GeneratedPlanItem(
                        slot_type=PlanSlot.BREAKFAST,
                        recipe_title="Unmeasured",
                        recipe_id=pin_id,
                        item_source=PlanItemSource.SAVED_RECIPE,
                        nutrition_unknown=True,
                    )
                ],
            )
        ]
    )

    class _Owned:
        def scalars(self) -> _Owned:
            return self

        def all(self) -> list[object]:
            return [pin_id]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Owned())
    enqueued: list[dict[str, object]] = []

    async def enqueue(
        _self: object,
        _job_type: str,
        _user_id: object,
        payload: dict[str, object],
        _db: object,
    ) -> None:
        enqueued.append(payload)

    monkeypatch.setattr(JobService, "set_progress", AsyncMock())
    monkeypatch.setattr(JobService, "enqueue", enqueue)
    monkeypatch.setattr(JobService, "mark_complete", AsyncMock())
    monkeypatch.setattr(
        "worker.handlers.NotificationService",
        MagicMock(return_value=MagicMock(publish=AsyncMock())),
    )
    monkeypatch.setattr(
        "worker.handlers.PlanGeneratorAgent",
        MagicMock(return_value=MagicMock(generate=AsyncMock(return_value=MagicMock()))),
    )
    monkeypatch.setattr(
        "worker.handlers.map_generated_plan",
        lambda *_args, **_kwargs: service_plan,
    )
    monkeypatch.setattr(
        PlanService,
        "write_generated_plan",
        AsyncMock(
            return_value=SimpleNamespace(
                id=job.plan_id,
                status=SimpleNamespace(value="reviewing"),
                title="Week",
            )
        ),
    )

    await handle_plan_generation(job, db)

    assert enqueued == []


@pytest.mark.asyncio
async def test_legacy_nutrition_job_completes_without_client_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        payload={"recipe_ids": [str(uuid4())], "trace_id": "nut"},
    )
    db = AsyncMock()
    db.get = AsyncMock(side_effect=AssertionError("estimator must not read recipes"))
    completed: dict[str, object] = {}

    async def mark_complete(
        _self: object, job_id: object, result: dict[str, object], _db: object
    ) -> None:
        completed["job_id"] = job_id
        completed["result"] = result

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("paid client must not be constructed")

    monkeypatch.setattr(JobService, "mark_complete", mark_complete)
    monkeypatch.setattr("agent.client.AnthropicClient.__init__", boom)
    monkeypatch.setattr("voyageai.Client", boom)

    result = await handle_recipe_nutrition_estimation(job, db)

    assert result == {"skipped": "estimator_removed"}
    assert completed == {
        "job_id": job.id,
        "result": {"skipped": "estimator_removed"},
    }
    db.get.assert_not_called()
