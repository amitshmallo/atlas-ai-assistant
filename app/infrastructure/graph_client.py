import httpx

from app.domain.entities import UserProfile

_GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"


class HttpxGraphClient:
    """Concrete implementation of the domain.GraphClient interface backed
    by a direct call to Microsoft Graph."""

    async def get_my_profile(self, access_token: str) -> UserProfile:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                _GRAPH_ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

        return UserProfile(
            id=data["id"],
            display_name=data.get("displayName", ""),
            mail=data.get("mail"),
            user_principal_name=data.get("userPrincipalName", ""),
        )
