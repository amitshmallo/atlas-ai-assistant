import uuid

from app.domain.entities import DocumentMetadata
from app.domain.interfaces import BlobStorageClient, DocumentRepository

# Matches what the OCR pipeline (Azure Document Intelligence's prebuilt-read
# model) actually supports — anything else can never leave `processing`, so
# there's no reason to let it consume storage while it waits to fail.
_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".heif", ".heic"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class UnsupportedFileTypeError(Exception):
    """Raised when the uploaded filename's extension isn't one the OCR
    pipeline can process — checked before anything touches blob storage."""


class FileTooLargeError(Exception):
    """Raised when the upload exceeds _MAX_UPLOAD_BYTES — checked before
    anything touches blob storage."""


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
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in _ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(extension or "(no extension)")
        if len(content) > _MAX_UPLOAD_BYTES:
            raise FileTooLargeError(len(content))

        # Generated here, not by the database, so it can be embedded in the
        # blob path before the row exists — see DocumentRepository.create_document.
        document_id = str(uuid.uuid4())
        blob_path = f"{user_oid}/{document_id}-{filename}"
        await self._blob_storage_client.upload(blob_path, content)
        return await self._document_repository.create_document(document_id, user_oid, filename, blob_path)
