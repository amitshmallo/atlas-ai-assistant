from collections.abc import AsyncIterator

from app.application.graph_tools import TOOL_SPECS, GraphToolExecutor
from app.domain.entities import ATLAS_SYSTEM_PROMPT, ChatMessage
from app.domain.interfaces import ChatClient, ConversationRepository, GraphTokenProvider

_RECENT_HISTORY_LIMIT = 20


class ConversationNotFoundError(Exception):
    """Raised when a client-supplied conversation_id doesn't exist or
    doesn't belong to the requesting user."""


class SendChatMessageUseCase:
    """Depends only on domain interfaces, never on concrete Postgres/Redis/
    LLM SDK/Graph implementations. Loads persisted history before calling
    the model and appends every turn — including the intermediate tool-call
    round trip — afterward. This is what makes the API stateless: any
    instance handling the next request reconstructs the same context from
    storage, tool calls included.

    Tool calling is a two-step protocol: first ask the model (non-streaming,
    since we need the full response to see `tool_calls`); if it wants to
    call tools, execute them via GraphToolExecutor and ask again — this
    second call is streamed, since it's the actual answer the user reads.
    """

    def __init__(
        self,
        chat_client: ChatClient,
        conversation_repository: ConversationRepository,
        graph_token_provider: GraphTokenProvider,
        tool_executor: GraphToolExecutor,
    ) -> None:
        self._chat_client = chat_client
        self._conversation_repository = conversation_repository
        self._graph_token_provider = graph_token_provider
        self._tool_executor = tool_executor

    async def execute(
        self,
        user_oid: str,
        conversation_id: str | None,
        user_message: str,
        user_assertion: str,
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

        result = await self._chat_client.complete_with_tools(messages, TOOL_SPECS)

        if not result.tool_calls:
            return conversation_id, self._persist_single_reply(conversation_id, result.content or "")

        assistant_tool_message = ChatMessage(
            role="assistant", content=result.content, tool_calls=result.tool_calls
        )
        messages.append(assistant_tool_message)
        await self._conversation_repository.append_message(conversation_id, assistant_tool_message)

        graph_token = await self._graph_token_provider.get_graph_token(user_oid, user_assertion)
        for tool_call in result.tool_calls:
            tool_result = await self._tool_executor.execute(tool_call, graph_token)
            tool_message = ChatMessage(
                role="tool", content=tool_result, tool_call_id=tool_call.id, name=tool_call.name
            )
            messages.append(tool_message)
            await self._conversation_repository.append_message(conversation_id, tool_message)

        return conversation_id, self._stream_and_persist(conversation_id, messages)

    async def _persist_single_reply(self, conversation_id: str, content: str) -> AsyncIterator[str]:
        yield content
        await self._conversation_repository.append_message(
            conversation_id, ChatMessage(role="assistant", content=content)
        )

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
