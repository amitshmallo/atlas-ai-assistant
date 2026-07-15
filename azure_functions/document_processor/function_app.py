"""Blob-triggered background processing: the event-driven half of Atlas's
IDP pipeline. UploadDocumentUseCase (app/application/upload_document.py)
only uploads the raw file and writes a `processing` row — everything slow
(OCR, chunking, embedding, indexing) happens here, out of the request/
response cycle, exactly the "Azure Functions do background processing"
architecture point from the plan.

Imports directly from the `app` package (same repo, monorepo-style) rather
than duplicating config/DB code — this Function and the FastAPI app share
infrastructure code but are deployed and scaled independently.
"""

import logging
import sys
from pathlib import Path

import azure.functions as func

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from chunking import chunk_text, parse_blob_path  # noqa: E402

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient  # noqa: E402
from azure.core.credentials import AzureKeyCredential  # noqa: E402
from azure.identity import DefaultAzureCredential, get_bearer_token_provider  # noqa: E402
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential  # noqa: E402
from azure.search.documents.aio import SearchClient  # noqa: E402
from azure.search.documents.indexes.aio import SearchIndexClient  # noqa: E402
from azure.search.documents.indexes.models import (  # noqa: E402
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AsyncAzureOpenAI  # noqa: E402
from sqlalchemy import update  # noqa: E402

from app.infrastructure.config import settings  # noqa: E402
from app.infrastructure.database import async_session_factory  # noqa: E402
from app.infrastructure.document_models import DocumentModel  # noqa: E402

app = func.FunctionApp()

_EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small
_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


def _search_credential():
    if settings.azure_search_api_key:
        return AzureKeyCredential(settings.azure_search_api_key)
    return AsyncDefaultAzureCredential()


async def _extract_text(content: bytes) -> str:
    credential = (
        AzureKeyCredential(settings.azure_document_intelligence_api_key)
        if settings.azure_document_intelligence_api_key
        else AsyncDefaultAzureCredential()
    )
    client = DocumentIntelligenceClient(
        endpoint=settings.azure_document_intelligence_endpoint, credential=credential
    )
    try:
        poller = await client.begin_analyze_document(
            "prebuilt-read", body=content, content_type="application/octet-stream"
        )
        result = await poller.result()
        return result.content or ""
    finally:
        await client.close()


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


async def _embed_chunks(chunks: list[str]) -> list[list[float]]:
    client = _build_openai_client()
    try:
        response = await client.embeddings.create(model=settings.azure_openai_embedding_deployment, input=chunks)
        return [item.embedding for item in response.data]
    finally:
        await client.close()


async def _ensure_index_exists() -> None:
    index_client = SearchIndexClient(endpoint=settings.azure_search_endpoint, credential=_search_credential())
    try:
        try:
            await index_client.get_index(settings.azure_search_index_name)
            return
        except Exception:
            pass  # index doesn't exist yet — create it below

        index = SearchIndex(
            name=settings.azure_search_index_name,
            fields=[
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SimpleField(name="user_oid", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="filename", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="chunk_text", type=SearchFieldDataType.String),
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=_EMBEDDING_DIMENSIONS,
                    vector_search_profile_name="default-profile",
                ),
            ],
            vector_search=VectorSearch(
                algorithms=[HnswAlgorithmConfiguration(name="default-hnsw")],
                profiles=[
                    VectorSearchProfile(name="default-profile", algorithm_configuration_name="default-hnsw")
                ],
            ),
        )
        await index_client.create_index(index)
    finally:
        await index_client.close()


async def _index_chunks(
    document_id: str, user_oid: str, filename: str, chunks: list[str], vectors: list[list[float]]
) -> None:
    search_client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=_search_credential(),
    )
    try:
        documents = [
            {
                "id": f"{document_id}-{i}",
                "user_oid": user_oid,
                "filename": filename,
                "chunk_text": chunk,
                "content_vector": vector,
            }
            for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        await search_client.upload_documents(documents)
    finally:
        await search_client.close()


async def _update_status(document_id: str, status: str, error_message: str | None = None) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(DocumentModel)
            .where(DocumentModel.id == document_id)
            .values(status=status, error_message=error_message)
        )
        await session.commit()


@app.blob_trigger(arg_name="blob", path="documents/{name}", connection="AzureWebJobsStorage")
async def process_uploaded_document(blob: func.InputStream) -> None:
    # blob.name from the runtime is "documents/{user_oid}/{document_id}-{filename}".
    blob_path = blob.name.split("/", 1)[1]
    user_oid, document_id, filename = parse_blob_path(blob_path)

    logging.info("Processing document %s (%s) for user %s", filename, document_id, user_oid)

    try:
        text = await _extract_text(blob.read())
        chunks = chunk_text(text)
        if not chunks:
            await _update_status(document_id, "failed", "No extractable text found")
            return

        vectors = await _embed_chunks(chunks)
        await _ensure_index_exists()
        await _index_chunks(document_id, user_oid, filename, chunks, vectors)
        await _update_status(document_id, "ready")
    except Exception as exc:  # noqa: BLE001 — this is the pipeline's terminal error boundary
        logging.exception("Failed to process document %s", document_id)
        await _update_status(document_id, "failed", str(exc))
