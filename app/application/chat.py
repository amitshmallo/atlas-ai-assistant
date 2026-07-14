from collections.abc import AsyncIterator

from app.domain.entities import ATLAS_SYSTEM_PROMPT, ChatMessage
from app.domain.interfaces import ChatClient, ConversationRepository

_RECENT_HISTORY_LIMIT = 20


class ConversationNotFoundError(Exception):
    """Raised when a client-supplied conversation_id doesn't exist or
    doesn't belong to the requesting user."""


class SendChatMessageUseCase:
    """Depends only on domain interfaces, never on concrete Postgres/Redis/
    LLM SDK implementations. Loads persisted history before calling the
    model and appends both the user's message and the assistant's full
    reply afterward — this is what makes the API stateless: any instance
    handling the next request reconstructs the same context from storage.
    """

    def __init__(
        self,
        chat_client: ChatClient,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._chat_client = chat_client
        self._conversation_repository = conversation_repository

    async def execute(
        self,
        user_oid: str,
        conversation_id: str | None,
        user_message: str,
    ) -> tuple[str, AsyncIterator[str]]:
        if conversation_id is None:
            conversation_id = await self._conversation_repository.create_conversation(user_oid)
        else:
            owner = await self._conversation_repository.get_owner(conversation_id)
            if owner != user_oid:
                raise ConversationNotFoundError(conversation_id)

        history = await self._conversation_repository.get_recent_messages(
            conversation_id, limit=_RECENT_HISTORY_LIMIT
        )
        await self._conversation_repository.append_message(
            conversation_id, ChatMessage(role="user", content=user_message)
        )

        messages = [
            ChatMessage(role="system", content=ATLAS_SYSTEM_PROMPT),
            *history,
            ChatMessage(role="user", content=user_message),
        ]

        return conversation_id, self._stream_and_persist(conversation_id, messages)

    async def _stream_and_persist(
        self, conversation_id: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        assistant_text_parts: list[str] = []
        async for chunk in self._chat_client.stream_completion(messages):
            assistant_text_parts.append(chunk)
            yield chunk

        await self._conversation_repository.append_message(
            conversation_id,
            ChatMessage(role="assistant", content="".join(assistant_text_parts)),
        )
