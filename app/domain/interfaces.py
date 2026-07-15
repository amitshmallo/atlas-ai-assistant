from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.domain.entities import (
    CalendarEvent,
    CalendarEventProposal,
    ChatCompletionResult,
    ChatMessage,
    EmailDraft,
    EmailMessage,
    EmailSummary,
    UserProfile,
)


class HealthCheckRepository(Protocol):
    """Abstract boundary the application layer depends on.

    infrastructure provides the concrete implementation (e.g. a SQLAlchemy
    ping against Postgres); application never imports that implementation
    directly — only this interface.
    """

    async def check_database(self) -> bool: ...


class GraphTokenProvider(Protocol):
    """Exchanges the inbound user JWT for a Graph-scoped access token via
    the On-Behalf-Of flow. The API never stores or forwards the user's
    original Graph credentials — only this short-lived derived token."""

    async def get_graph_token(self, user_oid: str, user_assertion: str) -> str: ...


class GraphClient(Protocol):
    """Abstract boundary over Microsoft Graph. application depends on this,
    never on the concrete httpx-based implementation."""

    async def get_my_profile(self, access_token: str) -> UserProfile: ...


class ChatClient(Protocol):
    """Abstract boundary over the LLM. application depends on this, never
    on the concrete Azure OpenAI SDK implementation."""

    def stream_completion(self, messages: list[ChatMessage]) -> AsyncIterator[str]: ...

    async def complete_with_tools(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> ChatCompletionResult:
        """Non-streaming: the model either answers directly or asks to call
        one or more tools. Tool-calling needs the full response to inspect
        `tool_calls`, so this can't be a stream — the final natural-language
        reply (after tool results are fed back) uses stream_completion."""
        ...


class GraphMailClient(Protocol):
    """Abstract boundary over Microsoft Graph mail endpoints."""

    async def list_recent_emails(
        self, access_token: str, top: int, unread_only: bool
    ) -> list[EmailSummary]: ...

    async def get_email(self, access_token: str, message_id: str) -> EmailMessage: ...

    async def create_draft_reply(
        self, access_token: str, message_id: str, body: str
    ) -> EmailDraft:
        """Creates a reply draft in the user's Drafts folder. Never sends
        it — sending would require a separate, explicit user action that
        no tool call can trigger on its own."""
        ...


class GraphCalendarClient(Protocol):
    """Abstract boundary over Microsoft Graph calendar endpoints. Only
    invoked by the explicit calendar-confirmation endpoint — never by a
    tool call the model can trigger directly."""

    async def create_event(self, access_token: str, proposal: CalendarEventProposal) -> CalendarEvent: ...


class ConversationRepository(Protocol):
    """Abstract boundary over conversation history storage. The concrete
    implementation persists durably to Postgres and read-through caches
    the recent window in Redis — application only ever sees this interface,
    so it has no idea storage is split across two systems."""

    async def create_conversation(self, user_oid: str) -> str:
        """Returns the new conversation's id."""
        ...

    async def get_recent_messages(self, conversation_id: str, limit: int) -> list[ChatMessage]: ...

    async def append_message(self, conversation_id: str, message: ChatMessage) -> None: ...

    async def get_owner(self, conversation_id: str) -> str | None:
        """Returns the user_oid that owns this conversation, or None if it
        doesn't exist. Callers must check this before reading or appending
        to a conversation_id supplied by the client — otherwise one user
        could read or write another user's chat history by guessing/reusing
        a conversation id."""
        ...
