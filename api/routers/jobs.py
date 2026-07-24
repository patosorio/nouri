"""Job status poll — docs/4_API_DESIGN.yaml GET /jobs/{job_id}."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import CurrentUser, get_current_user, get_db
from routers.serializers import serialize_job
from services.job_service import JobService

router = APIRouter()
_service = JobService()


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    job = await _service.get_status(job_id, current_user.id, db)
    return serialize_job(job)
