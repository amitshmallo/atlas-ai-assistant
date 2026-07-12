import msal
from redis.asyncio import Redis

from app.infrastructure.config import settings

_CACHE_KEY_PREFIX = "graph_token:"
_EXPIRY_SAFETY_MARGIN_SECONDS = 60


class MsalOboTokenProvider:
    """Exchanges the user's API access token for a Graph-scoped token via
    Azure AD's On-Behalf-Of flow. The API itself never sees or stores the
    user's Microsoft password — only short-lived derived tokens, cached in
    Redis per user until just before expiry."""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client
        self._confidential_app = msal.ConfidentialClientApplication(
            client_id=settings.entra_api_client_id,
            client_credential=settings.entra_api_client_secret,
            authority=settings.entra_authority,
        )

    async def get_graph_token(self, user_oid: str, user_assertion: str) -> str:
        cache_key = f"{_CACHE_KEY_PREFIX}{user_oid}"
        cached = await self._redis.get(cache_key)
        if cached:
            return cached

        result = self._confidential_app.acquire_token_on_behalf_of(
            user_assertion=user_assertion,
            scopes=settings.graph_scopes,
        )

        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "unknown error"))
            raise RuntimeError(f"On-Behalf-Of token exchange failed: {error}")

        access_token: str = result["access_token"]
        expires_in: int = result.get("expires_in", 3600)
        ttl = max(expires_in - _EXPIRY_SAFETY_MARGIN_SECONDS, 0)
        if ttl > 0:
            await self._redis.set(cache_key, access_token, ex=ttl)

        return access_token
