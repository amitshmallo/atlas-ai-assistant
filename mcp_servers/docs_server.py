"""Standalone MCP server exposing document search (RAG) over Azure AI
Search. The index is populated out-of-process by the blob-triggered Azure
Function (azure_functions/document_processor) — this server only ever
reads from it.

Every user's chunks live in the same index, isolated by a `user_oid`
filter at query time (not a separate index per user) — simpler to operate,
and the isolation guarantee lives in one place (this file) rather than in
per-user infrastructure. The user_oid comes from the USER_OID environment
variable injected at process spawn time, same pattern as the graph
server's GRAPH_ACCESS_TOKEN — never a tool argument the model could supply
itself.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from azure.core.credentials import AzureKeyCredential  # noqa: E402
from azure.identity import DefaultAzureCredential, get_bearer_token_provider  # noqa: E402
from azure.search.documents.aio import SearchClient  # noqa: E402
from azure.search.documents.models import VectorizedQuery  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402
from openai import AsyncAzureOpenAI  # noqa: E402

from app.infrastructure.config import settings  # noqa: E402

mcp = FastMCP("docs")

_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


def _build_search_client() -> SearchClient:
    credential = (
        AzureKeyCredential(settings.azure_search_api_key)
        if settings.azure_search_api_key
        else DefaultAzureCredential()
    )
    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=credential,
    )


def _build_openai_client() -> AsyncAzureOpenAI:
    if settings.azure_openai_api_key:
        return AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
    token_provider = get_bearer_token_provider(DefaultAzureCredential(), _COGNITIVE_SERVICES_SCOPE)
    return AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_ad_token_provider=token_provider,
        api_version=settings.azure_openai_api_version,
    )


async def _embed_query(text: str) -> list[float]:
    client = _build_openai_client()
    try:
        response = await client.embeddings.create(model=settings.azure_openai_embedding_deployment, input=text)
        return response.data[0].embedding
    finally:
        await client.close()


def _user_oid() -> str:
    oid = os.environ.get("USER_OID")
    if not oid:
        raise RuntimeError("USER_OID was not set for this MCP server process")
    return oid


@mcp.tool()
async def search_documents(query: str, top: int = 5) -> str:
    """Search the user's uploaded documents for content relevant to the
    query. Returns matching chunks along with the filename each one came
    from, so you can cite sources. If nothing matches, say so plainly
    instead of guessing."""
    query_vector = await _embed_query(query)

    search_client = _build_search_client()
    try:
        vector_query = VectorizedQuery(vector=query_vector, k_nearest_neighbors=top, fields="content_vector")
        results = await search_client.search(
            search_text=None,
            vector_queries=[vector_query],
            filter=f"user_oid eq '{_user_oid()}'",
            select=["filename", "chunk_text"],
            top=top,
        )
        matches = [{"filename": r["filename"], "chunk_text": r["chunk_text"]} async for r in results]
    finally:
        await search_client.close()

    if not matches:
        return json.dumps({"matches": [], "note": "No matching content found in the user's uploaded documents."})
    return json.dumps({"matches": matches})


if __name__ == "__main__":
    mcp.run()
