from collections.abc import AsyncIterator

from app.domain.entities import ATLAS_SYSTEM_PROMPT, ChatMessage, TokenUsage, ToolCallRequest
from app.domain.interfaces import (
    ChatClient,
    ConversationRepository,
    GraphTokenProvider,
    PreferenceRepository,
    ToolProvider,
    UsageRepository,
)

_RECENT_HISTORY_LIMIT = 20

# NUL is never legal inside a model's natural-language reply, so it's a safe
# in-band delimiter for tool-status events interleaved into the plain-text
# stream — the frontend strips/interprets anything between two of these
# rather than displaying it as chat text. Keeps the wire format a single
# text/plain stream instead of needing SSE/framing on top of it.
_SENTINEL = "\x00"


def _tool_event(kind: str, tool_name: str) -> str:
    return f"{_SENTINEL}{kind}:{tool_name}{_SENTINEL}"


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
    call tools, execute them via the ToolProvider (backed by MCP servers —
    application has no idea) and ask again — this second call is streamed,
    since it's the actual answer the user reads. Tool execution itself
    happens inside the same generator as the final-answer streaming, with
    `_tool_event` sentinels marking start/end of each call, so the frontend
    can show live "running search_documents..." status instead of a silent
    pause while tools run.

    Long-term memory (Phase 9) is loaded directly here, not via a tool —
    unlike Graph/docs tools that only run when the model decides to call
    them, preferences must apply to every turn of every conversation,
    including a brand-new one that has no reason to know to ask for them.
    Writing a new preference IS a tool (mcp_servers/memory_server.py),
    since that's a decision the model makes; reading them back isn't.
    """

    def __init__(
        self,
        chat_client: ChatClient,
        conversation_repository: ConversationRepository,
        graph_token_provider: GraphTokenProvider,
        tool_provider: ToolProvider,
        preference_repository: PreferenceRepository,
        usage_repository: UsageRepository,
    ) -> None:
        self._chat_client = chat_client
        self._conversation_repository = conversation_repository
        self._graph_token_provider = graph_token_provider
        self._tool_provider = tool_provider
        self._preference_repository = preference_repository
        self._usage_repository = usage_repository

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

        preferences = await self._preference_repository.get_preferences(user_oid)
        system_prompt = ATLAS_SYSTEM_PROMPT
        if preferences:
            preferences_text = "\n".join(f"- {p.key}: {p.value}" for p in preferences)
            system_prompt += f"\n\nRemembered preferences for this user:\n{preferences_text}"

        messages = [
            ChatMessage(role="system", content=system_prompt),
            *history,
            ChatMessage(role="user", content=user_message),
        ]

        tool_specs = await self._tool_provider.get_tool_specs()
        result = await self._chat_client.complete_with_tools(messages, tool_specs)
        if result.usage:
            await self._usage_repository.record_usage(user_oid, result.usage)

        if not result.tool_calls:
            return conversation_id, self._persist_single_reply(conversation_id, result.content or "")

        assistant_tool_message = ChatMessage(
            role="assistant", content=result.content, tool_calls=result.tool_calls
        )
        messages.append(assistant_tool_message)
        await self._conversation_repository.append_message(conversation_id, assistant_tool_message)

        graph_token = await self._graph_token_provider.get_graph_token(user_oid, user_assertion)
        tool_context = {"GRAPH_ACCESS_TOKEN": graph_token, "USER_OID": user_oid}

        return conversation_id, self._run_tools_then_stream(
            conversation_id, user_oid, messages, result.tool_calls, tool_context
        )

    async def _persist_single_reply(self, conversation_id: str, content: str) -> AsyncIterator[str]:
        yield content
        await self._conversation_repository.append_message(
            conversation_id, ChatMessage(role="assistant", content=content)
        )

    async def _run_tools_then_stream(
        self,
        conversation_id: str,
        user_oid: str,
        messages: list[ChatMessage],
        tool_calls: list[ToolCallRequest],
        tool_context: dict[str, str],
    ) -> AsyncIterator[str]:
        for tool_call in tool_calls:
            yield _tool_event("TOOL_START", tool_call.name)
            tool_result = await self._tool_provider.execute_tool(tool_call, tool_context)
            tool_message = ChatMessage(
                role="tool", content=tool_result, tool_call_id=tool_call.id, name=tool_call.name
            )
            messages.append(tool_message)
            await self._conversation_repository.append_message(conversation_id, tool_message)
            yield _tool_event("TOOL_END", tool_call.name)

        assistant_text_parts: list[str] = []
        final_usage: TokenUsage | None = None

        def _capture_usage(usage: TokenUsage) -> None:
            nonlocal final_usage
            final_usage = usage

        async for chunk in self._chat_client.stream_completion(messages, on_usage=_capture_usage):
            assistant_text_parts.append(chunk)
            yield chunk

        await self._conversation_repository.append_message(
            conversation_id,
            ChatMessage(role="assistant", content="".join(assistant_text_parts)),
        )
        if final_usage:
            await self._usage_repository.record_usage(user_oid, final_usage)
