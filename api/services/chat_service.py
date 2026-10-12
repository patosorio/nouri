"""ChatService — SSE stream facade over ChatAgent (docs/7_TECH_SPEC.md §10)."""

from __future__ import annotations

import json
from binascii import Error as BinasciiError
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import structlog
from agent.chat_agent import ChatAgent
from cryptography.exceptions import InvalidTag
from db.models import Conversation
from encryption.field_encryption import FieldEncryption
from exceptions import NotFoundError, OwnershipError
from schemas.agent import AgentContext, SSEEvent
from schemas.http import ChatRequest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# A bad ciphertext must not fail the conversation list. Count it as empty.
_MESSAGE_DECRYPT_ERRORS = (
    BinasciiError,
    InvalidTag,
    TypeError,
    UnicodeDecodeError,
    ValueError,
    json.JSONDecodeError,
)

_USER_OPEN = "<user_content>"
_USER_CLOSE = "</user_content>"


def display_messages(stored: list[object] | None) -> list[dict[str, str]]:
    """Flatten persisted agent turns into OpenAPI ChatMessage rows."""
    out: list[dict[str, str]] = []
    for raw in stored or []:
        if not isinstance(raw, dict):
            continue
        role = raw.get("role")
        content = raw.get("content")
        if role == "user" and isinstance(content, str):
            text = content
            if text.startswith(_USER_OPEN) and text.endswith(_USER_CLOSE):
                text = text[len(_USER_OPEN) : -len(_USER_CLOSE)]
            out.append({"role": "user", "content": text})
        elif role == "assistant":
            text = _assistant_text(content)
            if text:
                out.append({"role": "assistant", "content": text})
    return out


def _assistant_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts).strip()


class ChatService:
    def __init__(
        self,
        chat_agent: ChatAgent | None = None,
        encryption: FieldEncryption | None = None,
    ) -> None:
        self._agent = chat_agent or ChatAgent()
        self._encryption = encryption or FieldEncryption()

    async def stream(
        self,
        user_id: UUID,
        message: str,
        conversation_id: UUID | None,
        context: dict[str, object] | None,
        db: AsyncSession,
        *,
        trace_id: str | None = None,
    ) -> AsyncIterator[SSEEvent]:
        conv_id = conversation_id or uuid4()
        agent_context = self._build_context(context, trace_id=trace_id)

        # Service-layer encryption boundary: decrypt for the agent, encrypt after.
        await self._prepare_plaintext_conversation(
            conv_id, user_id, agent_context, db
        )

        async for event in self._agent.run(
            user_id=user_id,
            conversation_id=conv_id,
            new_message=message,
            context=agent_context,
            db=db,
        ):
            # OpenAPI: tool calls are resolved server-side and not streamed.
            if event.type == "tool_call":
                continue
            if event.type == "done" and event.conversation_id is None:
                yield event.model_copy(update={"conversation_id": conv_id})
            else:
                yield event

        await self._encrypt_conversation_messages(conv_id, db)

    async def stream_from_request(
        self,
        user_id: UUID,
        request: ChatRequest,
        db: AsyncSession,
        *,
        trace_id: str | None = None,
    ) -> AsyncIterator[SSEEvent]:
        async for event in self.stream(
            user_id=user_id,
            message=request.message,
            conversation_id=request.conversation_id,
            context=request.context,
            db=db,
            trace_id=trace_id,
        ):
            yield event

    def _build_context(
        self,
        context: dict[str, object] | None,
        *,
        trace_id: str | None,
    ) -> AgentContext:
        if not context:
            return AgentContext(trace_id=trace_id)
        current_plan_id = context.get("current_plan_id")
        active_recipe_id = context.get("active_recipe_id")
        return AgentContext(
            current_plan_id=UUID(str(current_plan_id)) if current_plan_id else None,
            active_recipe_id=UUID(str(active_recipe_id)) if active_recipe_id else None,
            trace_id=trace_id,
        )

    async def _prepare_plaintext_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        context: AgentContext,
        db: AsyncSession,
    ) -> None:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None:
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                plan_id=context.current_plan_id,
                messages=[],
                tool_call_logs=[],
            )
            db.add(conversation)
            await db.flush()
            return

        from exceptions import OwnershipError

        if conversation.user_id != user_id:
            raise OwnershipError("Conversation not found")
        conversation.messages = self.decrypt_messages(
            list(conversation.messages or [])
        )
        await db.flush()

    async def _encrypt_conversation_messages(
        self, conversation_id: UUID, db: AsyncSession
    ) -> None:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None:
            return
        messages = conversation.messages
        if not isinstance(messages, list) or not messages:
            return
        if (
            len(messages) == 1
            and isinstance(messages[0], dict)
            and messages[0].get("_encrypted") is True
        ):
            return
        token = self._encryption.encrypt_json(json.dumps(messages))
        conversation.messages = [{"_encrypted": True, "ciphertext": token}]
        await db.flush()

    def decrypt_messages(self, stored: list[object] | None) -> list[object]:
        if not stored:
            return []
        if (
            len(stored) == 1
            and isinstance(stored[0], dict)
            and stored[0].get("_encrypted") is True
        ):
            raw = self._encryption.decrypt_json(str(stored[0]["ciphertext"]))
            return list(json.loads(raw))
        return list(stored)

    async def list_conversations(
        self,
        user_id: UUID,
        db: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[Conversation], list[int], int]:
        base = select(Conversation).where(Conversation.user_id == user_id)
        count_result = await db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())
        result = await db.execute(
            base.order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = list(result.scalars().all())
        counts: list[int] = []
        for conversation in rows:
            try:
                plaintext = self.decrypt_messages(list(conversation.messages or []))
                counts.append(len(display_messages(plaintext)))
            except _MESSAGE_DECRYPT_ERRORS:
                logger.warning(
                    "conversation_message_count_failed",
                    user_id=str(user_id),
                    conversation_id=str(conversation.id),
                    operation="list_conversations",
                    exc_info=True,
                )
                counts.append(0)
        return rows, counts, total

    async def get_conversation(
        self, conversation_id: UUID, user_id: UUID, db: AsyncSession
    ) -> tuple[Conversation, list[dict[str, str]]]:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        if conversation.user_id != user_id:
            raise OwnershipError("Conversation not found")
        plaintext = self.decrypt_messages(list(conversation.messages or []))
        return conversation, display_messages(plaintext)

    async def delete_conversation(
        self, conversation_id: UUID, user_id: UUID, db: AsyncSession
    ) -> None:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        if conversation.user_id != user_id:
            raise OwnershipError("Conversation not found")
        await db.delete(conversation)
        await db.flush()
