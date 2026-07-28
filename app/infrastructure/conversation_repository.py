import json

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import ChatMessage, ConversationSummary, ToolCallRequest
from app.infrastructure.conversation_models import ConversationModel, MessageModel

_CACHE_TTL_SECONDS = 3600
_TITLE_MAX_LENGTH = 60


class SqlAlchemyConversationRepository:
    """Concrete implementation of domain.ConversationRepository.

    Postgres is the durable source of truth; Redis is a read-through cache
    of each conversation's recent-message window, invalidated on every
    write rather than updated in place — simpler to reason about than
    maintaining a bounded list in Redis, and cheap since a cache miss just
    means one extra Postgres query.
    """

    def __init__(self, session: AsyncSession, redis_client: Redis) -> None:
        self._session = session
        self._redis = redis_client

    async def create_conversation(self, user_oid: str) -> str:
        conversation = ConversationModel(user_oid=user_oid)
        self._session.add(conversation)
        await self._session.commit()
        return str(conversation.id)

    async def get_recent_messages(self, conversation_id: str, limit: int) -> list[ChatMessage]:
        cache_key = self._cache_key(conversation_id)
        cached = await self._redis.get(cache_key)
        if cached is not None:
            return [ChatMessage(**item) for item in json.loads(cached)]

        result = await self._session.execute(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
        messages = [self._row_to_message(row) for row in rows]

        await self._redis.set(
            cache_key,
            json.dumps([m.model_dump() for m in messages]),
            ex=_CACHE_TTL_SECONDS,
        )
        return messages

    async def list_conversations(self, user_oid: str) -> list[ConversationSummary]:
        conversations_result = await self._session.execute(
            select(ConversationModel)
            .where(ConversationModel.user_oid == user_oid)
            .order_by(ConversationModel.created_at.desc())
        )
        conversations = conversations_result.scalars().all()
        if not conversations:
            return []

        conversation_ids = [c.id for c in conversations]
        messages_result = await self._session.execute(
            select(MessageModel)
            .where(MessageModel.conversation_id.in_(conversation_ids))
            .order_by(MessageModel.created_at.asc())
        )
        # Grouping in Python rather than a second aggregate query — the
        # per-conversation message count here is small (bounded by how
        # much a person chats in one session), so this is cheap and avoids
        # a fiddly window-function query for first-user-message + last-any-
        # message in one round trip.
        first_user_message_by_conversation: dict = {}
        last_message_at_by_conversation: dict = {}
        for message in messages_result.scalars().all():
            last_message_at_by_conversation[message.conversation_id] = message.created_at
            if message.role == "user" and message.conversation_id not in first_user_message_by_conversation:
                first_user_message_by_conversation[message.conversation_id] = message.content or ""

        summaries = []
        for conversation in conversations:
            title = first_user_message_by_conversation.get(conversation.id, "New conversation")
            if len(title) > _TITLE_MAX_LENGTH:
                title = title[:_TITLE_MAX_LENGTH].rstrip() + "…"
            updated_at = last_message_at_by_conversation.get(conversation.id, conversation.created_at)
            summaries.append(
                ConversationSummary(id=str(conversation.id), title=title, updated_at=updated_at.isoformat())
            )

        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries

    async def get_owner(self, conversation_id: str) -> str | None:
        try:
            result = await self._session.execute(
                select(ConversationModel.user_oid).where(ConversationModel.id == conversation_id)
            )
        except ValueError:
            # conversation_id wasn't a well-formed UUID at all.
            return None
        return result.scalar_one_or_none()

    async def append_message(self, conversation_id: str, message: ChatMessage) -> None:
        self._session.add(
            MessageModel(
                conversation_id=conversation_id,
                role=message.role,
                content=message.content,
                tool_calls=[tc.model_dump() for tc in message.tool_calls] if message.tool_calls else None,
                tool_call_id=message.tool_call_id,
                name=message.name,
            )
        )
        await self._session.commit()
        await self._redis.delete(self._cache_key(conversation_id))

    @staticmethod
    def _row_to_message(row: MessageModel) -> ChatMessage:
        return ChatMessage(
            role=row.role,
            content=row.content,
            tool_calls=[ToolCallRequest(**tc) for tc in row.tool_calls] if row.tool_calls else None,
            tool_call_id=row.tool_call_id,
            name=row.name,
        )

    @staticmethod
    def _cache_key(conversation_id: str) -> str:
        return f"conversation_messages:{conversation_id}"
