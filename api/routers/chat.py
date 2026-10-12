"""Chat SSE and conversation history — docs/4_API_DESIGN.yaml POST /chat, /conversations."""

from __future__ import annotations

from uuid import UUID, uuid4

from config import settings
from dependencies import CurrentUser, get_current_user, get_db
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from main import limiter
from schemas.http import ChatRequest
from services.chat_service import ChatService
from sqlalchemy.ext.asyncio import AsyncSession

from routers.serializers import (
    pagination_meta,
    serialize_conversation,
    serialize_conversation_summary,
)

router = APIRouter()
_service = ChatService()
_current_user = Depends(get_current_user)
_db = Depends(get_db)
_offset = Query(0, ge=0)
_limit = Query(30, ge=1, le=30)


@router.post("/chat")
@limiter.limit(f"{settings.rate_limit_chat_per_hour}/hour")
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> StreamingResponse:
    conversation_id = body.conversation_id or uuid4()
    trace_id = getattr(request.state, "trace_id", None)

    async def event_generator():  # type: ignore[no-untyped-def]
        async for event in _service.stream(
            user_id=current_user.id,
            message=body.message,
            conversation_id=conversation_id,
            context=body.context,
            db=db,
            trace_id=str(trace_id) if trace_id else None,
        ):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Conversation-Id": str(conversation_id),
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/conversations")
async def list_conversations(
    offset: int = _offset,
    limit: int = _limit,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    rows, counts, total = await _service.list_conversations(
        current_user.id, db, offset=offset, limit=limit
    )
    return {
        "data": [
            serialize_conversation_summary(row, message_count=count)
            for row, count in zip(rows, counts, strict=True)
        ],
        "pagination": pagination_meta(total, offset, limit),
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    conversation, messages = await _service.get_conversation(
        conversation_id, current_user.id, db
    )
    return serialize_conversation(conversation, messages)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> Response:
    await _service.delete_conversation(conversation_id, current_user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
