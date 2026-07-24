"""Pantry routes — docs/4_API_DESIGN.yaml /pantry*."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import CurrentUser, get_current_user, get_db
from routers.serializers import pagination_meta, serialize_pantry_item
from schemas.http import PantryItemPayload
from services.pantry_service import PantryService

router = APIRouter()
_service = PantryService()


@router.get("/pantry")
async def list_pantry_items(
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=30),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    items, total = await _service.list_pantry(
        current_user.id, db, offset=offset, limit=limit
    )
    return {
        "data": [serialize_pantry_item(i) for i in items],
        "pagination": pagination_meta(total, offset, limit),
    }


@router.post("/pantry/items", status_code=status.HTTP_201_CREATED)
async def add_pantry_item(
    body: PantryItemPayload,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    item = await _service.add_item_from_payload(
        current_user.id,
        ingredient_name_raw=body.ingredient_name_raw,
        quantity=body.quantity,
        unit=body.unit,
        notes=body.notes,
        expires_at=body.expires_at,
        db=db,
    )
    return serialize_pantry_item(item)


@router.patch("/pantry/items/{item_id}")
async def update_pantry_item(
    item_id: UUID,
    body: PantryItemPayload,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    item = await _service.update_item(
        item_id,
        current_user.id,
        db,
        quantity=body.quantity,
        unit=body.unit,
        notes=body.notes,
        expires_at=body.expires_at,
        ingredient_name_raw=body.ingredient_name_raw,
    )
    return serialize_pantry_item(item)


@router.delete(
    "/pantry/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_pantry_item(
    item_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _service.remove_item(item_id, current_user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
