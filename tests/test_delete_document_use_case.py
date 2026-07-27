import pytest

from app.application.delete_document import DeleteDocumentUseCase, DocumentNotFoundError


class FakeDocumentRepository:
    def __init__(self, owner: str | None, blob_path: str | None) -> None:
        self._owner = owner
        self._blob_path = blob_path
        self.deleted: list[str] = []

    async def get_owner(self, document_id: str):
        return self._owner

    async def get_blob_path(self, document_id: str):
        return self._blob_path

    async def delete_document(self, document_id: str) -> None:
        self.deleted.append(document_id)


class FakeBlobStorageClient:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, blob_path: str) -> None:
        self.deleted.append(blob_path)


class FakeDocumentSearchIndex:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    async def delete_document_chunks(self, document_id: str, user_oid: str) -> None:
        self.deleted.append((document_id, user_oid))


async def test_execute_deletes_search_chunks_blob_and_row_in_order():
    repository = FakeDocumentRepository(owner="user-1", blob_path="user-1/doc-1-invoice.pdf")
    blob_client = FakeBlobStorageClient()
    search_index = FakeDocumentSearchIndex()
    use_case = DeleteDocumentUseCase(repository, blob_client, search_index)

    await use_case.execute(user_oid="user-1", document_id="doc-1")

    assert search_index.deleted == [("doc-1", "user-1")]
    assert blob_client.deleted == ["user-1/doc-1-invoice.pdf"]
    assert repository.deleted == ["doc-1"]


async def test_execute_raises_when_document_not_found():
    repository = FakeDocumentRepository(owner=None, blob_path=None)
    use_case = DeleteDocumentUseCase(repository, FakeBlobStorageClient(), FakeDocumentSearchIndex())

    with pytest.raises(DocumentNotFoundError):
        await use_case.execute(user_oid="user-1", document_id="doc-1")

    assert repository.deleted == []


async def test_execute_raises_when_requesting_user_is_not_the_owner():
    repository = FakeDocumentRepository(owner="someone-else", blob_path="someone-else/doc-1-invoice.pdf")
    use_case = DeleteDocumentUseCase(repository, FakeBlobStorageClient(), FakeDocumentSearchIndex())

    with pytest.raises(DocumentNotFoundError):
        await use_case.execute(user_oid="user-1", document_id="doc-1")

    assert repository.deleted == []
