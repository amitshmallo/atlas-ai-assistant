from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient

from app.infrastructure.config import settings


def _build_client() -> SearchClient:
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


class AzureSearchDocumentIndex:
    """Concrete implementation of domain.DocumentSearchIndex. The only
    write path the API needs against the index the Function populates —
    deleting a document's chunks when the user deletes the document."""

    async def delete_document_chunks(self, document_id: str, user_oid: str) -> None:
        client = _build_client()
        try:
            # Chunk keys are "{document_id}-{chunk_index}" (see
            # azure_functions/document_processor/function_app.py's
            # _index_chunks) — there's no separate filterable document_id
            # field on the index, so this filters to the owning user first
            # (cheap, indexed) and matches the id prefix client-side.
            results = await client.search(
                search_text="*",
                filter=f"user_oid eq '{user_oid}'",
                select=["id"],
                top=1000,
            )
            prefix = f"{document_id}-"
            matching_ids = [r["id"] async for r in results if r["id"].startswith(prefix)]
            if matching_ids:
                await client.delete_documents(documents=[{"id": key} for key in matching_ids])
        finally:
            await client.close()
