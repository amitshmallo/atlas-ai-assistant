from app.domain.interfaces import BlobStorageClient, DocumentRepository, DocumentSearchIndex


class DocumentNotFoundError(Exception):
    """Raised when a client-supplied document_id doesn't exist or doesn't
    belong to the requesting user — same ownership-check pattern as
    ConversationNotFoundError."""


class DeleteDocumentUseCase:
    """Depends only on domain interfaces. Cleans up the search index and
    blob first (best-effort — a document stuck mid-cleanup shouldn't block
    the user from retrying), then removes the Postgres row last, since
    that's the source of truth for what the user sees in their document
    list. Deleting the row first and failing on the blob/index after would
    leave the document invisible but its content still live and
    searchable — worse than the reverse order's small chance of an
    orphaned blob or index entry with no row pointing at it."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        blob_storage_client: BlobStorageClient,
        document_search_index: DocumentSearchIndex,
    ) -> None:
        self._document_repository = document_repository
        self._blob_storage_client = blob_storage_client
        self._document_search_index = document_search_index

    async def execute(self, user_oid: str, document_id: str) -> None:
        owner = await self._document_repository.get_owner(document_id)
        if owner != user_oid:
            raise DocumentNotFoundError(document_id)

        blob_path = await self._document_repository.get_blob_path(document_id)

        await self._document_search_index.delete_document_chunks(document_id, user_oid)
        if blob_path:
            await self._blob_storage_client.delete(blob_path)
        await self._document_repository.delete_document(document_id)
