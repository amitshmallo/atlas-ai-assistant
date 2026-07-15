from collections.abc import AsyncIterator

import pytest

from app.application.chat import ConversationNotFoundError, SendChatMessageUseCase
from app.domain.entities import ChatCompletionResult, ChatMessage, ToolCallRequest


class FakeChatClient:
    def __init__(
        self,
        completion: ChatCompletionResult | None = None,
        final_stream_chunks: list[str] | None = None,
    ) -> None:
        self._completion = completion or ChatCompletionResult(content="ok", tool_calls=[])
        self._final_stream_chunks = final_stream_chunks or []
        self.messages_seen_by_complete: list[ChatMessage] | None = None
        self.messages_seen_by_stream: list[ChatMessage] | None = None

    async def complete_with_tools(self, messages, tools) -> ChatCompletionResult:
        self.messages_seen_by_complete = messages
        return self._completion

    async def stream_completion(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.messages_seen_by_stream = messages
        for chunk in self._final_stream_chunks:
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


class FakeGraphTokenProvider:
    def __init__(self) -> None:
        self.last_call: tuple[str, str] | None = None

    async def get_graph_token(self, user_oid: str, user_assertion: str) -> str:
        self.last_call = (user_oid, user_assertion)
        return "graph-token"


class FakeToolProvider:
    def __init__(self, result: str = "tool result", specs: list[dict] | None = None) -> None:
        self._result = result
        self._specs = specs if specs is not None else []
        self.calls: list[tuple[ToolCallRequest, dict]] = []

    async def get_tool_specs(self) -> list[dict]:
        return self._specs

    async def execute_tool(self, tool_call: ToolCallRequest, context: dict) -> str:
        self.calls.append((tool_call, context))
        return self._result


async def _drain(stream: AsyncIterator[str]) -> list[str]:
    return [chunk async for chunk in stream]


def _make_use_case(chat_client, repository, token_provider=None, tool_provider=None):
    return SendChatMessageUseCase(
        chat_client,
        repository,
        token_provider or FakeGraphTokenProvider(),
        tool_provider or FakeToolProvider(),
    )


async def test_execute_without_tool_call_persists_both_sides():
    fake_client = FakeChatClient(completion=ChatCompletionResult(content="Hello world", tool_calls=[]))
    repository = FakeConversationRepository()
    use_case = _make_use_case(fake_client, repository)

    conversation_id, stream = await use_case.execute(
        user_oid="user-1", conversation_id=None, user_message="Hi Atlas", user_assertion="jwt"
    )
    collected = await _drain(stream)

    assert collected == ["Hello world"]
    assert repository.conversations[conversation_id] == "user-1"
    assert [m.role for m in repository.messages[conversation_id]] == ["user", "assistant"]
    assert repository.messages[conversation_id][1].content == "Hello world"


async def test_execute_prepends_system_prompt_and_persisted_history():
    fake_client = FakeChatClient(completion=ChatCompletionResult(content="ok", tool_calls=[]))
    repository = FakeConversationRepository()
    conversation_id = await repository.create_conversation("user-1")
    await repository.append_message(conversation_id, ChatMessage(role="user", content="earlier question"))
    await repository.append_message(conversation_id, ChatMessage(role="assistant", content="earlier answer"))

    use_case = _make_use_case(fake_client, repository)
    _, stream = await use_case.execute(
        user_oid="user-1", conversation_id=conversation_id, user_message="follow-up", user_assertion="jwt"
    )
    await _drain(stream)

    assert fake_client.messages_seen_by_complete is not None
    roles_and_content = [(m.role, m.content) for m in fake_client.messages_seen_by_complete]
    assert roles_and_content == [
        ("system", fake_client.messages_seen_by_complete[0].content),
        ("user", "earlier question"),
        ("assistant", "earlier answer"),
        ("user", "follow-up"),
    ]


async def test_execute_rejects_conversation_owned_by_another_user():
    fake_client = FakeChatClient()
    repository = FakeConversationRepository()
    conversation_id = await repository.create_conversation("owner-user")

    use_case = _make_use_case(fake_client, repository)

    with pytest.raises(ConversationNotFoundError):
        await use_case.execute(
            user_oid="different-user",
            conversation_id=conversation_id,
            user_message="hi",
            user_assertion="jwt",
        )


async def test_execute_with_tool_call_executes_tool_and_streams_final_answer():
    tool_call = ToolCallRequest(id="call-1", name="list_recent_emails", arguments={"top": 5})
    fake_client = FakeChatClient(
        completion=ChatCompletionResult(content=None, tool_calls=[tool_call]),
        final_stream_chunks=["You have ", "3 unread emails."],
    )
    repository = FakeConversationRepository()
    token_provider = FakeGraphTokenProvider()
    tool_provider = FakeToolProvider(result='[{"subject": "Hi"}]')
    use_case = _make_use_case(fake_client, repository, token_provider, tool_provider)

    conversation_id, stream = await use_case.execute(
        user_oid="user-1",
        conversation_id=None,
        user_message="Summarize my unread emails",
        user_assertion="the-jwt",
    )
    collected = await _drain(stream)

    assert collected == ["You have ", "3 unread emails."]

    # The Graph token was exchanged using the inbound JWT, not a stored credential.
    assert token_provider.last_call == ("user-1", "the-jwt")

    # The tool was actually executed with that token, plus the user_oid for
    # tools (like document search) that need per-user isolation rather than
    # a Graph credential.
    assert len(tool_provider.calls) == 1
    executed_call, context = tool_provider.calls[0]
    assert executed_call.name == "list_recent_emails"
    assert context == {"GRAPH_ACCESS_TOKEN": "graph-token", "USER_OID": "user-1"}

    # Full round trip persisted: user msg, assistant tool-call msg, tool result msg, final assistant msg.
    persisted_roles = [m.role for m in repository.messages[conversation_id]]
    assert persisted_roles == ["user", "assistant", "tool", "assistant"]
    assert repository.messages[conversation_id][1].tool_calls == [tool_call]
    assert repository.messages[conversation_id][2].tool_call_id == "call-1"
    assert repository.messages[conversation_id][3].content == "You have 3 unread emails."

    # The final streaming call saw the tool result in its message history.
    assert fake_client.messages_seen_by_stream is not None
    assert fake_client.messages_seen_by_stream[-1].role == "tool"
    assert fake_client.messages_seen_by_stream[-1].content == '[{"subject": "Hi"}]'
