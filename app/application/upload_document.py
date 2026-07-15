import uuid

from app.domain.entities import DocumentMetadata
from app.domain.interfaces import BlobStorageClient, DocumentRepository


class UploadDocumentUseCase:
    """Depends only on domain interfaces. Uploads the raw bytes to blob
    storage and records a `processing` row in Postgres — that's the whole
    job. OCR/chunk/embed/index happens asynchronously, out of process, in
    the blob-triggered Azure Function (azure_functions/document_processor),
    which flips the row to `ready`/`failed` when it's done. This is the
    event-driven background-processing pattern from the plan: the request
    that uploads a file returns immediately rather than blocking on OCR."""

    def __init__(self, document_repository: DocumentRepository, blob_storage_client: BlobStorageClient) -> None:
        self._document_repository = document_repository
        self._blob_storage_client = blob_storage_client

    async def execute(self, user_oid: str, filename: str, content: bytes) -> DocumentMetadata:
        # Generated here, not by the database, so it can be embedded in the
        # blob path before the row exists — see DocumentRepository.create_document.
        document_id = str(uuid.uuid4())
        blob_path = f"{user_oid}/{document_id}-{filename}"
        await self._blob_storage_client.upload(blob_path, content)
        return await self._document_repository.create_document(document_id, user_oid, filename, blob_path)
