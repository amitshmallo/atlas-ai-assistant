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
