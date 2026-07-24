"""Profile routes — docs/4_API_DESIGN.yaml /profile*."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import CurrentUser, get_current_user, get_db
from exceptions import NotFoundError
from routers.serializers import serialize_exclusion, serialize_profile
from schemas.http import ExclusionPayload, OnboardingPayload
from schemas.profile import ProfileCreate, ProfileUpdate
from services.profile_service import ProfileService

router = APIRouter()
_service = ProfileService()


@router.get("/profile")
async def get_profile(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    profile = await _service.get_profile(current_user.id, db)
    return serialize_profile(profile, email=current_user.email)


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    profile = await _service.update_profile(current_user.id, body, db)
    return serialize_profile(profile, email=current_user.email)


@router.post("/profile/onboarding")
async def complete_onboarding(
    body: OnboardingPayload,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    create = ProfileCreate.model_validate(
        body.model_dump(exclude={"exclusion_names"})
    )
    try:
        await _service.get_profile(current_user.id, db)
        profile = await _service.update_profile(
            current_user.id,
            ProfileUpdate.model_validate(
                create.model_dump(exclude_unset=False)
            ),
            db,
        )
    except NotFoundError:
        profile = await _service.create_profile(current_user.id, create, db)

    for name in body.exclusion_names:
        await _service.add_exclusion_by_name(current_user.id, name, db)

    return serialize_profile(profile, email=current_user.email)


@router.get("/profile/exclusions")
async def list_exclusions(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    rows = await _service.get_exclusions(current_user.id, db)
    return {"data": [serialize_exclusion(r) for r in rows]}


@router.post("/profile/exclusions", status_code=status.HTTP_201_CREATED)
async def add_exclusion(
    body: ExclusionPayload,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    row = await _service.add_exclusion_by_name(
        current_user.id, body.ingredient_name_raw, db
    )
    return serialize_exclusion(row)


@router.delete(
    "/profile/exclusions/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_exclusion(
    item_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _service.remove_exclusion(current_user.id, item_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
