from app.application.graph_profile import GetMyProfileUseCase
from app.domain.entities import UserProfile


class FakeTokenProvider:
    def __init__(self, token: str) -> None:
        self._token = token
        self.last_call: tuple[str, str] | None = None

    async def get_graph_token(self, user_oid: str, user_assertion: str) -> str:
        self.last_call = (user_oid, user_assertion)
        return self._token


class FakeGraphClient:
    def __init__(self, profile: UserProfile) -> None:
        self._profile = profile
        self.last_access_token: str | None = None

    async def get_my_profile(self, access_token: str) -> UserProfile:
        self.last_access_token = access_token
        return self._profile


async def test_get_my_profile_exchanges_token_then_calls_graph():
    expected_profile = UserProfile(
        id="abc-123",
        display_name="Julia Yoshpe",
        mail="julia@example.com",
        user_principal_name="julia@example.com",
    )
    token_provider = FakeTokenProvider(token="graph-token-xyz")
    graph_client = FakeGraphClient(profile=expected_profile)
    use_case = GetMyProfileUseCase(token_provider, graph_client)

    result = await use_case.execute(user_oid="user-oid-1", user_assertion="inbound-jwt")

    assert result == expected_profile
    assert token_provider.last_call == ("user-oid-1", "inbound-jwt")
    assert graph_client.last_access_token == "graph-token-xyz"
