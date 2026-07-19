import pytest

from mcp_servers import memory_server


@pytest.fixture(autouse=True)
def user_oid_env(monkeypatch):
    monkeypatch.setenv("USER_OID", "user-123")


async def test_remember_preference_persists_via_repository(monkeypatch):
    calls: list[tuple[str, str, str]] = []

    async def fake_set_preference(user_oid: str, key: str, value: str) -> None:
        calls.append((user_oid, key, value))

    monkeypatch.setattr(memory_server, "_set_preference", fake_set_preference)

    result = await memory_server.remember_preference(key="reply_style", value="concise")

    assert calls == [("user-123", "reply_style", "concise")]
    assert "reply_style" in result
    assert "concise" in result


async def test_remember_preference_requires_user_oid_env(monkeypatch):
    monkeypatch.delenv("USER_OID", raising=False)

    async def fake_set_preference(user_oid: str, key: str, value: str) -> None:
        pass

    monkeypatch.setattr(memory_server, "_set_preference", fake_set_preference)

    with pytest.raises(RuntimeError):
        await memory_server.remember_preference(key="k", value="v")
