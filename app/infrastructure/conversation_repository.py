import json

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import ChatMessage
from app.infrastructure.conversation_models import ConversationModel, MessageModel

_CACHE_TTL_SECONDS = 3600


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
        messages = [ChatMessage(role=row.role, content=row.content) for row in rows]

        await self._redis.set(
            cache_key,
            json.dumps([m.model_dump() for m in messages]),
            ex=_CACHE_TTL_SECONDS,
        )
        return messages

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
            )
        )
        await self._session.commit()
        await self._redis.delete(self._cache_key(conversation_id))

    @staticmethod
    def _cache_key(conversation_id: str) -> str:
        return f"conversation_messages:{conversation_id}"
