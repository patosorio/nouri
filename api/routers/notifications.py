"""Notifications — docs/4_API_DESIGN.yaml /notifications*."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import CurrentUser, get_current_user, get_db
from routers.serializers import pagination_meta, serialize_notification
from services.notification_service import NotificationService

router = APIRouter()
_service = NotificationService()


@router.get("/notifications")
async def list_notifications(
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=30),
    unread_only: bool = Query(False),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    rows, total = await _service.list_notifications(
        current_user.id,
        db,
        offset=offset,
        limit=limit,
        unread_only=unread_only,
    )
    return {
        "data": [serialize_notification(r) for r in rows],
        "pagination": pagination_meta(total, offset, limit),
    }


@router.post(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _service.mark_read(notification_id, current_user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/notifications/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def mark_all_notifications_read(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _service.mark_all_read(current_user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
