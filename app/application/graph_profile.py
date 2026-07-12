from app.domain.entities import UserProfile
from app.domain.interfaces import GraphClient, GraphTokenProvider


class GetMyProfileUseCase:
    """Exchanges the caller's JWT for a Graph token (On-Behalf-Of), then
    fetches their Graph profile. Depends only on domain interfaces."""

    def __init__(
        self,
        token_provider: GraphTokenProvider,
        graph_client: GraphClient,
    ) -> None:
        self._token_provider = token_provider
        self._graph_client = graph_client

    async def execute(self, user_oid: str, user_assertion: str) -> UserProfile:
        graph_token = await self._token_provider.get_graph_token(user_oid, user_assertion)
        return await self._graph_client.get_my_profile(graph_token)
