from collections.abc import AsyncIterator

import pytest

from app.application.chat import ConversationNotFoundError, SendChatMessageUseCase
from app.domain.entities import ChatMessage


class FakeChatClient:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.last_messages: list[ChatMessage] | None = None

    async def stream_completion(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.last_messages = messages
        for chunk in self._chunks:
            yield chunk


class FakeConversationRepository:
    def __init__(self) -> None:
        self.conversations: dict[str, str] = {}  # conversation_id -> user_oid
        self.messages: dict[str, list[ChatMessage]] = {}
        self._next_id = 0

    async def create_conversation(self, user_oid: str) -> str:
        self._next_id += 1
        conversation_id = f"conv-{self._next_id}"
        self.conversations[conversation_id] = user_oid
        self.messages[conversation_id] = []
        return conversation_id

    async def get_recent_messages(self, conversation_id: str, limit: int) -> list[ChatMessage]:
        return self.messages.get(conversation_id, [])[-limit:]

    async def append_message(self, conversation_id: str, message: ChatMessage) -> None:
        self.messages.setdefault(conversation_id, []).append(message)

    async def get_owner(self, conversation_id: str) -> str | None:
        return self.conversations.get(conversation_id)


async def _drain(stream: AsyncIterator[str]) -> list[str]:
    return [chunk async for chunk in stream]


async def test_execute_creates_conversation_and_persists_both_sides():
    fake_client = FakeChatClient(chunks=["Hello", " ", "world"])
    repository = FakeConversationRepository()
    use_case = SendChatMessageUseCase(fake_client, repository)

    conversation_id, stream = await use_case.execute(
        user_oid="user-1", conversation_id=None, user_message="Hi Atlas"
    )
    collected = await _drain(stream)

    assert collected == ["Hello", " ", "world"]
    assert repository.conversations[conversation_id] == "user-1"
    assert [m.role for m in repository.messages[conversation_id]] == ["user", "assistant"]
    assert repository.messages[conversation_id][1].content == "Hello world"


async def test_execute_prepends_system_prompt_and_persisted_history():
    fake_client = FakeChatClient(chunks=["ok"])
    repository = FakeConversationRepository()
    conversation_id = await repository.create_conversation("user-1")
    await repository.append_message(conversation_id, ChatMessage(role="user", content="earlier question"))
    await repository.append_message(conversation_id, ChatMessage(role="assistant", content="earlier answer"))

    use_case = SendChatMessageUseCase(fake_client, repository)
    _, stream = await use_case.execute(
        user_oid="user-1", conversation_id=conversation_id, user_message="follow-up"
    )
    await _drain(stream)

    assert fake_client.last_messages is not None
    roles_and_content = [(m.role, m.content) for m in fake_client.last_messages]
    assert roles_and_content == [
        ("system", fake_client.last_messages[0].content),
        ("user", "earlier question"),
        ("assistant", "earlier answer"),
        ("user", "follow-up"),
    ]


async def test_execute_rejects_conversation_owned_by_another_user():
    fake_client = FakeChatClient(chunks=["ok"])
    repository = FakeConversationRepository()
    conversation_id = await repository.create_conversation("owner-user")

    use_case = SendChatMessageUseCase(fake_client, repository)

    with pytest.raises(ConversationNotFoundError):
        await use_case.execute(
            user_oid="different-user", conversation_id=conversation_id, user_message="hi"
        )
