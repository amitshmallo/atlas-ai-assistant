from collections.abc import AsyncIterator

from app.application.chat import SendChatMessageUseCase
from app.domain.entities import ChatMessage


class FakeChatClient:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.last_messages: list[ChatMessage] | None = None

    async def stream_completion(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.last_messages = messages
        for chunk in self._chunks:
            yield chunk


async def test_execute_prepends_system_prompt_and_streams_chunks():
    fake_client = FakeChatClient(chunks=["Hello", " ", "world"])
    use_case = SendChatMessageUseCase(fake_client)
    history = [ChatMessage(role="user", content="Hi Atlas")]

    collected = [chunk async for chunk in use_case.execute(history)]

    assert collected == ["Hello", " ", "world"]
    assert fake_client.last_messages is not None
    assert fake_client.last_messages[0].role == "system"
    assert fake_client.last_messages[1] == history[0]
