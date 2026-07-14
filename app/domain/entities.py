from typing import Literal

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


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


ATLAS_SYSTEM_PROMPT = (
    "You are Atlas, a personal AI executive assistant. You can help summarize "
    "email, draft replies, manage calendar events, and answer questions about "
    "the user's inbox and documents. You must never send an email or create/"
    "modify a calendar event without the user explicitly approving that exact "
    "action first — always propose a draft and ask for confirmation. Be "
    "concise and direct."
)
