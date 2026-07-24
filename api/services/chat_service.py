"""ChatService — SSE stream facade over ChatAgent (docs/7_TECH_SPEC.md §10)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agent.chat_agent import ChatAgent
from db.models import Conversation
from encryption.field_encryption import FieldEncryption
from schemas.agent import AgentContext, SSEEvent
from schemas.http import ChatRequest


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
