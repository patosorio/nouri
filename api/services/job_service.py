from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import JobQueue, JobStatus
from exceptions import NotFoundError, OwnershipError
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
        self, job_id: UUID, error: str, db: AsyncSession
    ) -> None:
        job = await db.get(JobQueue, job_id)
        if job is None:
            raise NotFoundError("Job not found")
        job.status = JobStatus.FAILED
        job.error_message = error
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()

    async def get_status(
        self, job_id: UUID, user_id: UUID, db: AsyncSession
    ) -> JobQueue:
        job = await db.get(JobQueue, job_id)
        if job is None:
            raise NotFoundError("Job not found")
        if job.user_id != user_id:
            raise OwnershipError("Job not found")
        return job

    async def reap_stale(
        self, db: AsyncSession, *, older_than_minutes: int = 10
    ) -> int:
        """Reset jobs stuck in running — docs/2_SAD.md §9.2 durability."""
        result = await db.execute(
            text(
                """
                UPDATE job_queue
                SET status = 'pending',
                    claimed_at = NULL,
                    updated_at = NOW()
                WHERE status = 'running'
                  AND claimed_at IS NOT NULL
                  AND claimed_at < NOW() - make_interval(mins => :minutes)
                RETURNING id
                """
            ),
            {"minutes": older_than_minutes},
        )
        return len(result.fetchall())
