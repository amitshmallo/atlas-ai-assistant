from collections.abc import AsyncIterator

from app.domain.entities import ATLAS_SYSTEM_PROMPT, ChatMessage
from app.domain.interfaces import ChatClient


class SendChatMessageUseCase:
    """Depends only on the ChatClient interface, not on any concrete LLM
    SDK. Prepends the Atlas system prompt so the persona/guardrails are
    enforced consistently regardless of caller."""

    def __init__(self, chat_client: ChatClient) -> None:
        self._chat_client = chat_client

    async def execute(self, history: list[ChatMessage]) -> AsyncIterator[str]:
        messages = [ChatMessage(role="system", content=ATLAS_SYSTEM_PROMPT), *history]
        async for chunk in self._chat_client.stream_completion(messages):
            yield chunk
