from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Notification, NotificationType
from exceptions import NotFoundError, OwnershipError
from services._helpers import get_profile_or_404


class NotificationService:
    async def list_notifications(
        self,
        user_id: UUID,
        db: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 30,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        await get_profile_or_404(user_id, db)
        base = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            base = base.where(Notification.is_read.is_(False))

        from sqlalchemy import func

        count_result = await db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())
        result = await db.execute(
            base.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_unread(
        self, user_id: UUID, db: AsyncSession
    ) -> list[Notification]:
        rows, _ = await self.list_notifications(
            user_id, db, offset=0, limit=100, unread_only=True
        )
        return rows

    async def mark_read(
        self, notification_id: UUID, user_id: UUID, db: AsyncSession
    ) -> None:
        notification = await db.get(Notification, notification_id)
        if notification is None:
            raise NotFoundError("Notification not found")
        if notification.user_id != user_id:
            raise OwnershipError("Notification not found")
        notification.is_read = True
        await db.flush()

    async def mark_all_read(self, user_id: UUID, db: AsyncSession) -> None:
        await get_profile_or_404(user_id, db)
        result = await db.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        for notification in result.scalars().all():
            notification.is_read = True
        await db.flush()

    async def publish(
        self,
        user_id: UUID,
        notification_type: str,
        payload: dict[str, Any],
        db: AsyncSession,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> Notification:
        await get_profile_or_404(user_id, db)
        try:
            ntype = NotificationType(notification_type)
        except ValueError as exc:
            raise NotFoundError(f"Unknown notification type: {notification_type}") from exc

        notification = Notification(
            user_id=user_id,
            type=ntype,
            title=title or ntype.value.replace("_", " ").title(),
            body=body,
            data=payload,
            is_read=False,
        )
        db.add(notification)
        await db.flush()
        await db.refresh(notification)
        return notification
