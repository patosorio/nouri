"""Shopping list — docs/4_API_DESIGN.yaml GET /plans/{plan_id}/shopping-list."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import CurrentUser, get_current_user, get_db
from routers.serializers import serialize_shopping_item
from services.shopping_list_service import ShoppingListService

router = APIRouter()
_service = ShoppingListService()


@router.get("/plans/{plan_id}/shopping-list")
async def get_plan_shopping_list(
    plan_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    items = await _service.generate(plan_id, current_user.id, db)
    return {
        "plan_id": str(plan_id),
        "items": [serialize_shopping_item(i) for i in items],
        "pantry_deducted": current_user.tier == "pro",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
