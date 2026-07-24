"""Background worker — Postgres job queue consumer (docs/2_SAD.md §9, TECH_SPEC §8)."""

from __future__ import annotations

import asyncio
import signal
import uuid
from typing import Any

import structlog

from db.models import JobQueue
from db.session import async_session_factory, engine
from exceptions import PlanGenerationFailedError
from middleware.logging import configure_structlog
from services.job_service import JobService
from worker.handlers import (
    NUTRITION_JOB_TYPE,
    PLAN_JOB_TYPES,
    handle_plan_generation,
    handle_recipe_nutrition_estimation,
)

logger = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 2.0
MAX_JOB_RUNTIME_SECONDS = 120.0
REAP_EVERY_N_POLLS = 30

_shutdown = asyncio.Event()


def _request_shutdown() -> None:
    logger.info("worker_shutdown_requested")
    _shutdown.set()


async def main() -> None:
    configure_structlog()
    worker_id = f"worker-{uuid.uuid4()}"
    logger.info("worker_started", worker_id=worker_id)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Windows / restricted environments — signals may be unavailable.
            signal.signal(sig, lambda *_args: _request_shutdown())

    jobs = JobService()
    polls_since_reap = REAP_EVERY_N_POLLS

    try:
        while not _shutdown.is_set():
            polls_since_reap += 1
            if polls_since_reap >= REAP_EVERY_N_POLLS:
                async with async_session_factory() as db:
                    reaped = await jobs.reap_stale(db)
                    await db.commit()
                if reaped:
                    logger.info("jobs_reaped", count=reaped, worker_id=worker_id)
                polls_since_reap = 0

            job = await _claim(jobs, worker_id)
            if job is None:
                try:
                    await asyncio.wait_for(
                        _shutdown.wait(), timeout=POLL_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    pass
                continue

            await _process_job(job, worker_id)
    finally:
        await engine.dispose()
        logger.info("worker_stopped", worker_id=worker_id)


async def _claim(jobs: JobService, worker_id: str) -> JobQueue | None:
    async with async_session_factory() as db:
        job = await jobs.claim_next(worker_id, db)
        await db.commit()
        if job is None:
            return None
        # Detach identity for use outside the session.
        await db.refresh(job)
        db.expunge(job)
        return job


async def _process_job(job: JobQueue, worker_id: str) -> None:
    trace_id = None
    if isinstance(job.payload, dict):
        raw_trace = job.payload.get("trace_id")
        if isinstance(raw_trace, str):
            trace_id = raw_trace

    logger.info(
        "job_started",
        job_id=str(job.id),
        job_type=job.job_type,
        user_id=str(job.user_id),
        attempt=job.attempts,
        worker_id=worker_id,
        trace_id=trace_id,
    )

    try:
        result = await asyncio.wait_for(
            _dispatch(job),
            timeout=MAX_JOB_RUNTIME_SECONDS,
        )
        logger.info(
            "job_completed",
            job_id=str(job.id),
            job_type=job.job_type,
            worker_id=worker_id,
            trace_id=trace_id,
            result=result,
        )
    except TimeoutError:
        message = f"Job exceeded max runtime of {int(MAX_JOB_RUNTIME_SECONDS)}s"
        logger.error(
            "job_timeout",
            job_id=str(job.id),
            job_type=job.job_type,
            worker_id=worker_id,
            trace_id=trace_id,
        )
        await _fail_job(job.id, message, notify_plan_failure=job.job_type in PLAN_JOB_TYPES)
    except PlanGenerationFailedError as exc:
        # Handler already marked failed + notified.
        logger.error(
            "job_failed",
            job_id=str(job.id),
            job_type=job.job_type,
            worker_id=worker_id,
            trace_id=trace_id,
            error=exc.message,
            code=exc.code,
        )
    except Exception as exc:
        logger.exception(
            "job_failed",
            job_id=str(job.id),
            job_type=job.job_type,
            worker_id=worker_id,
            trace_id=trace_id,
            error=str(exc),
        )
        await _fail_job(
            job.id,
            f"{type(exc).__name__}: {exc}",
            notify_plan_failure=job.job_type in PLAN_JOB_TYPES,
            user_id=job.user_id,
            plan_id=job.plan_id,
        )


async def _dispatch(job: JobQueue) -> dict[str, Any]:
    async with async_session_factory() as db:
        try:
            if job.job_type in PLAN_JOB_TYPES:
                result = await handle_plan_generation(job, db)
            elif job.job_type == NUTRITION_JOB_TYPE:
                result = await handle_recipe_nutrition_estimation(job, db)
            else:
                message = f"Unknown job_type: {job.job_type}"
                await JobService().mark_failed(job.id, message, db)
                await db.commit()
                logger.error(
                    "job_unknown_type",
                    job_id=str(job.id),
                    job_type=job.job_type,
                )
                return {"error": message}
            await db.commit()
            return result
        except PlanGenerationFailedError:
            await db.commit()
            raise
        except Exception:
            await db.rollback()
            raise


async def _fail_job(
    job_id: uuid.UUID,
    error: str,
    *,
    notify_plan_failure: bool = False,
    user_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
) -> None:
    from db.models import NotificationType
    from services.notification_service import NotificationService

    async with async_session_factory() as db:
        await JobService().mark_failed(job_id, error, db)
        if notify_plan_failure and user_id is not None:
            await NotificationService().publish(
                user_id,
                NotificationType.PLAN_FAILED.value,
                {
                    "job_id": str(job_id),
                    "plan_id": str(plan_id) if plan_id else None,
                    "message": error,
                },
                db,
                title="Plan generation failed",
                body=error,
            )
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
