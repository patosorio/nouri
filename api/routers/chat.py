"""Chat SSE — docs/4_API_DESIGN.yaml POST /chat / docs/7_TECH_SPEC.md §10."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from dependencies import CurrentUser, get_current_user, get_db
from main import limiter
from schemas.http import ChatRequest
from services.chat_service import ChatService

router = APIRouter()
_service = ChatService()


@router.post("/chat")
@limiter.limit(f"{settings.rate_limit_chat_per_hour}/hour")
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
