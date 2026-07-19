from typing import Any, Literal

from pydantic import BaseModel


class HealthStatus(BaseModel):
    api: bool
    database: bool

    @property
    def healthy(self) -> bool:
        return self.api and self.database


class AuthenticatedUser(BaseModel):
    """The identity extracted from a validated Entra ID JWT — not the Graph
    profile. `oid` is the stable per-user object id used as our internal key."""

    oid: str
    name: str | None = None
    preferred_username: str | None = None


class UserProfile(BaseModel):
    """The user's Microsoft Graph /me profile."""

    id: str
    display_name: str
    mail: str | None = None
    user_principal_name: str


class ToolCallRequest(BaseModel):
    """A single function call the model asked to make."""

    id: str
    name: str
    arguments: dict[str, Any]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    # Present on assistant messages that requested tool calls — must be
    # echoed back verbatim on the next request per the OpenAI tool-calling
    # protocol, so the model sees what it asked for.
    tool_calls: list[ToolCallRequest] | None = None
    # Present on role="tool" messages: which call this result answers.
    tool_call_id: str | None = None
    name: str | None = None


class ChatCompletionResult(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCallRequest] = []


class EmailSummary(BaseModel):
    id: str
    subject: str
    from_address: str | None = None
    received_at: str | None = None
    is_read: bool = False
    preview: str = ""


class EmailMessage(BaseModel):
    id: str
    subject: str
    from_address: str | None = None
    received_at: str | None = None
    body: str = ""


class EmailDraft(BaseModel):
    id: str
    status: str = "draft created — not sent"


class CalendarEventProposal(BaseModel):
    """A calendar event the assistant wants to create. Never sent to Graph
    directly by the tool — only surfaced to the user for explicit
    confirmation via a separate, non-LLM-triggered API call."""

    subject: str
    start: str
    end: str
    attendees: list[str] = []


class CalendarEvent(BaseModel):
    id: str
    subject: str
    start: str
    end: str


class DocumentMetadata(BaseModel):
    """Tracks a user-uploaded document through the async IDP pipeline:
    processing (just uploaded, Function hasn't picked it up / is still
    chunking+embedding+indexing it) -> ready (searchable) -> failed."""

    id: str
    filename: str
    status: Literal["processing", "ready", "failed"]
    error_message: str | None = None


class UserPreference(BaseModel):
    """A durable fact about the user, stored outside conversation history so
    it persists across brand-new conversations, not just the one it was
    stated in — e.g. {"reply_style": "concise"}."""

    key: str
    value: str


ATLAS_SYSTEM_PROMPT = (
    "You are Atlas, a personal AI executive assistant. You can help summarize "
    "email, draft replies, manage calendar events, and answer questions about "
    "the user's inbox and documents. When you use search_documents to answer "
    "a question, cite which document(s) the answer came from by filename, "
    "and say so plainly if the uploaded documents don't contain the answer "
    "rather than guessing. When the user states a lasting preference about "
    "how you should behave (not just for this message), use the "
    "remember_preference tool to save it so it applies in future "
    "conversations too. You must never send an email or create/modify a "
    "calendar event without the user explicitly approving that exact action "
    "first — always propose a draft and ask for confirmation. Be concise "
    "and direct."
)
