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


class TokenUsage(BaseModel):
    """Token counts for a single model call, reported by the Azure OpenAI
    API itself (never estimated client-side) so cost tracking reflects
    what was actually billed."""

    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ChatCompletionResult(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCallRequest] = []
    usage: TokenUsage | None = None


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


class EmailSendProposal(BaseModel):
    """An email the assistant wants to send. Never sent to Graph directly
    by the tool — only surfaced to the user for explicit confirmation via
    a separate, non-LLM-triggered API call, same pattern as
    CalendarEventProposal.

    attachment_filename is a name the model overheard the user say (e.g.
    "attach my resume"), not a document_id — the model is never given raw
    document ids, so resolving the filename to an actual document (and
    verifying the requesting user owns it) happens entirely server-side
    in SendEmailUseCase."""

    to: str
    subject: str
    body: str
    attachment_filename: str | None = None


class EmailSendResult(BaseModel):
    status: str = "sent"


class DocumentMetadata(BaseModel):
    """Tracks a user-uploaded document through the async IDP pipeline:
    processing (just uploaded, Function hasn't picked it up / is still
    chunking+embedding+indexing it) -> ready (searchable) -> failed."""

    id: str
    filename: str
    status: Literal["processing", "ready", "failed"]
    error_message: str | None = None


class UsageSummary(BaseModel):
    """Aggregated token usage/cost for a user, over some lookback window.
    Cost is an estimate (settings.azure_openai_input/output_cost_per_1k),
    not a billing-accurate figure — Azure billing is the source of truth."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    turn_count: int


class UserPreference(BaseModel):
    """A durable fact about the user, stored outside conversation history so
    it persists across brand-new conversations, not just the one it was
    stated in — e.g. {"reply_style": "concise"}."""

    key: str
    value: str


ATLAS_SYSTEM_PROMPT = (
    "You are Atlas, a personal AI executive assistant. You can help summarize "
    "email, draft replies, send new emails, manage calendar events, and answer "
    "questions about the user's inbox and documents. When you use "
    "search_documents to answer a question, cite which document(s) the answer "
    "came from by filename, and say so plainly if the uploaded documents don't "
    "contain the answer rather than guessing. When the user states a lasting "
    "preference about how you should behave (not just for this message), use "
    "the remember_preference tool to save it so it applies in future "
    "conversations too — this includes people's email addresses: the first "
    "time the user gives you a name and an email address together, remember "
    "it (key like contact_email_<name>, value the address) so you can resolve "
    "that name to an address yourself next time, without asking again. You "
    "must never send an email or create/modify a calendar event without the "
    "user explicitly approving that exact action first — always propose a "
    "draft (propose_send_email / propose_calendar_event) and ask for "
    "confirmation; never call anything that sends or creates directly. If the "
    "user asks to attach one of their uploaded documents, pass its filename "
    "as attachment_filename on the proposal — never invent or guess a "
    "filename that wasn't mentioned or found via search_documents. Be concise "
    "and direct."
)
