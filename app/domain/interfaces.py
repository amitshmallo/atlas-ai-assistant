from collections.abc import AsyncIterator
from typing import Protocol

from app.domain.entities import ChatMessage, UserProfile


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
