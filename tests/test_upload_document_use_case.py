import uuid

from app.application.upload_document import UploadDocumentUseCase
from app.domain.entities import DocumentMetadata


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str, str]] = []

    async def create_document(self, document_id: str, user_oid: str, filename: str, blob_path: str):
        self.created.append((document_id, user_oid, filename, blob_path))
        return DocumentMetadata(id=document_id, filename=filename, status="processing")

    async def list_documents(self, user_oid: str):
        return []

    async def get_owner(self, document_id: str):
        return None


class FakeBlobStorageClient:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, bytes]] = []

    async def upload(self, blob_path: str, content: bytes) -> None:
        self.uploaded.append((blob_path, content))


async def test_execute_uploads_blob_and_creates_processing_row():
    repository = FakeDocumentRepository()
    blob_client = FakeBlobStorageClient()
    use_case = UploadDocumentUseCase(repository, blob_client)

    result = await use_case.execute(user_oid="user-1", filename="invoice.pdf", content=b"pdf bytes")

    assert result.status == "processing"
    assert result.filename == "invoice.pdf"

    assert len(blob_client.uploaded) == 1
    blob_path, content = blob_client.uploaded[0]
    assert content == b"pdf bytes"
    assert blob_path.startswith("user-1/")
    assert blob_path.endswith("-invoice.pdf")

    assert len(repository.created) == 1
    document_id, user_oid, filename, repo_blob_path = repository.created[0]
    assert user_oid == "user-1"
    assert filename == "invoice.pdf"
    # The id embedded in the blob path must match the DB row's id exactly —
    # the Azure Function relies on this to know which row to update.
    assert repo_blob_path == blob_path
    assert document_id == result.id
    uuid.UUID(document_id)  # must be a real UUID
