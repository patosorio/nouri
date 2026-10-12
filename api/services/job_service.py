from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from db.models import JobQueue, JobStatus
from exceptions import NotFoundError, OwnershipError
from jobs.types import PLAN_JOB_TYPES
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services._helpers import get_profile_or_404


class JobService:
    async def enqueue(
        self,
        job_type: str,
        user_id: UUID,
        payload: dict[str, Any],
        db: AsyncSession,
        *,
        plan_id: UUID | None = None,
    ) -> JobQueue:
        await get_profile_or_404(user_id, db)
        job = JobQueue(
            job_type=job_type,
            user_id=user_id,
            plan_id=plan_id,
            status=JobStatus.PENDING,
            payload=payload,
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        return job

    async def claim_next(
        self, worker_id: str, db: AsyncSession
    ) -> JobQueue | None:
        # FOR UPDATE SKIP LOCKED — docs/7_TECH_SPEC.md §8 / docs/3_ERD.md §4.6
        result = await db.execute(
            text(
                """
                SELECT id FROM job_queue
                WHERE status = 'pending'
                  AND scheduled_for <= NOW()
                ORDER BY scheduled_for ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
        )
        row = result.fetchone()
        if row is None:
            return None

        job_id = row[0]
        job = await db.get(JobQueue, job_id)
        if job is None:
            return None

        job.status = JobStatus.RUNNING
        job.claimed_at = datetime.now(timezone.utc)
        job.attempts = job.attempts + 1
        # worker_id recorded in payload for observability (no dedicated column in ERD)
        payload = dict(job.payload or {})
        payload["claimed_by"] = worker_id
        job.payload = payload
        await db.flush()
        await db.refresh(job)
        return job

    async def mark_complete(
        self, job_id: UUID, result: dict[str, Any], db: AsyncSession
    ) -> None:
        job = await db.get(JobQueue, job_id)
        if job is None:
            raise NotFoundError("Job not found")
        job.status = JobStatus.COMPLETED
        job.result = result
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = None
        await db.flush()

    async def mark_failed(
        self,
        job_id: UUID,
        error: str,
        db: AsyncSession,
        *,
        retry: bool = False,
    ) -> bool:
        """Mark failed, or re-queue if retry and attempts remain. True = terminal."""
        job = await db.get(JobQueue, job_id)
        if job is None:
            raise NotFoundError("Job not found")
        if retry and job.attempts < job.max_attempts:
            delay = min(60, 2 ** job.attempts)
            job.status = JobStatus.PENDING
            job.claimed_at = None
            job.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=delay)
            job.error_message = error
            await db.flush()
            return False
        job.status = JobStatus.FAILED
        job.error_message = error
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return True

    async def save_llm_output(
        self, job_id: UUID, llm_output: dict[str, Any]
    ) -> None:
        """Commit parsed model output on its own so a later rollback cannot drop it."""
        from db.session import async_session_factory

        async with async_session_factory() as session:
            job = await session.get(JobQueue, job_id)
            if job is None:
                raise NotFoundError("Job not found")
            job.llm_output = llm_output
            job.llm_output_saved_at = datetime.now(timezone.utc)
            await session.commit()

    async def get_status(
        self, job_id: UUID, user_id: UUID, db: AsyncSession
    ) -> JobQueue:
        job = await db.get(JobQueue, job_id)
        if job is None:
            raise NotFoundError("Job not found")
        if job.user_id != user_id:
            raise OwnershipError("Job not found")
        return job

    async def set_progress(
        self,
        job_id: UUID,
        *,
        progress_pct: int,
        stage: str,
        days_completed: int = 0,
        days_total: int = 7,
    ) -> None:
        """Commit progress so the API can poll it while the worker job is running."""
        from db.session import async_session_factory

        async with async_session_factory() as db:
            job = await db.get(JobQueue, job_id)
            if job is None:
                return
            job.result = {
                "progress_pct": max(0, min(100, progress_pct)),
                "stage": stage,
                "days_completed": days_completed,
                "days_total": days_total,
            }
            await db.commit()

    async def latest_for_plans(
        self, plan_ids: list[UUID], db: AsyncSession
    ) -> dict[UUID, JobQueue]:
        if not plan_ids:
            return {}
        result = await db.execute(
            select(JobQueue)
            .where(
                JobQueue.plan_id.in_(plan_ids),
                JobQueue.job_type.in_(("generate_plan", "plan_generation")),
            )
            .order_by(JobQueue.created_at.desc())
        )
        latest: dict[UUID, JobQueue] = {}
        for job in result.scalars().all():
            if job.plan_id is not None and job.plan_id not in latest:
                latest[job.plan_id] = job
        return latest

    async def reap_stale(
        self, db: AsyncSession, *, older_than_minutes: int = 10
    ) -> int:
        """Reset jobs stuck in running — docs/2_SAD.md §9.2 durability.

        A stale plan job with no saved llm_output fails terminally, so a crash
        during the model call cannot start another paid attempt. A stale plan
        job that already stored llm_output, and any non-plan job, is requeued
        while attempts remain. llm_output is left unchanged. At max_attempts
        the job fails with "stale and out of attempts".
        """
        stale = await self._select_stale(db, older_than_minutes=older_than_minutes)
        now = datetime.now(timezone.utc)
        for job in stale:
            unsaved_plan = (
                job.job_type in PLAN_JOB_TYPES and job.llm_output is None
            )
            if unsaved_plan:
                job.status = JobStatus.FAILED
                job.error_message = (
                    "stale plan job with no saved output; failing closed"
                )
                job.completed_at = now
            elif job.attempts >= job.max_attempts:
                job.status = JobStatus.FAILED
                job.error_message = "stale and out of attempts"
                job.completed_at = now
            else:
                job.status = JobStatus.PENDING
                job.claimed_at = None
            job.updated_at = now
        if stale:
            await db.flush()
        return len(stale)

    async def _select_stale(
        self, db: AsyncSession, *, older_than_minutes: int
    ) -> list[JobQueue]:
        result = await db.execute(
            text(
                """
                SELECT id FROM job_queue
                WHERE status = 'running'
                  AND claimed_at IS NOT NULL
                  AND claimed_at < NOW() - make_interval(mins => :minutes)
                FOR UPDATE
                """
            ),
            {"minutes": older_than_minutes},
        )
        jobs: list[JobQueue] = []
        for row in result.fetchall():
            job = await db.get(JobQueue, row[0])
            if job is not None:
                jobs.append(job)
        return jobs
