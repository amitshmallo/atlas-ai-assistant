import json

import pytest

from mcp_servers import docs_server


class FakeSearchResults:
    def __init__(self, items: list[dict]) -> None:
        self._items = items

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for item in self._items:
            yield item


class FakeSearchClient:
    def __init__(self, results: list[dict]) -> None:
        self._results = results
        self.last_filter: str | None = None
        self.last_vector_queries = None

    async def search(self, search_text, vector_queries, filter, select, top):
        self.last_filter = filter
        self.last_vector_queries = vector_queries
        return FakeSearchResults(self._results)

    async def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    async def _fake_embed_query(text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(docs_server, "_embed_query", _fake_embed_query)


@pytest.fixture(autouse=True)
def user_oid_env(monkeypatch):
    monkeypatch.setenv("USER_OID", "user-123")


async def test_search_documents_returns_matches_and_filters_by_user_oid(monkeypatch):
    fake_client = FakeSearchClient(
        [{"filename": "invoice.pdf", "chunk_text": "Total due: $500"}]
    )
    monkeypatch.setattr(docs_server, "_build_search_client", lambda: fake_client)

    result = await docs_server.search_documents(query="what's the total due?", top=3)

    assert fake_client.last_filter == "user_oid eq 'user-123'"
    parsed = json.loads(result)
    assert parsed["matches"][0]["filename"] == "invoice.pdf"
    assert "500" in parsed["matches"][0]["chunk_text"]


async def test_search_documents_returns_note_when_no_matches(monkeypatch):
    fake_client = FakeSearchClient([])
    monkeypatch.setattr(docs_server, "_build_search_client", lambda: fake_client)

    result = await docs_server.search_documents(query="anything")

    parsed = json.loads(result)
    assert parsed["matches"] == []
    assert "No matching content" in parsed["note"]


async def test_search_documents_requires_user_oid_env(monkeypatch):
    monkeypatch.delenv("USER_OID", raising=False)
    fake_client = FakeSearchClient([])
    monkeypatch.setattr(docs_server, "_build_search_client", lambda: fake_client)

    with pytest.raises(RuntimeError):
        await docs_server.search_documents(query="anything")
