import pytest

from app.application.send_email import AttachmentNotFoundError, SendEmailUseCase
from app.domain.entities import DocumentMetadata, EmailSendProposal


class FakeGraphTokenProvider:
    async def get_graph_token(self, user_oid: str, user_assertion: str) -> str:
        return f"graph-token-for-{user_oid}"


class FakeGraphMailClient:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_email(self, access_token, proposal, attachment_content):
        self.sent.append((access_token, proposal, attachment_content))


class FakeDocumentRepository:
    def __init__(self, documents: list[DocumentMetadata], blob_paths: dict[str, str]) -> None:
        self._documents = documents
        self._blob_paths = blob_paths

    async def list_documents(self, user_oid: str):
        return self._documents

    async def get_blob_path(self, document_id: str):
        return self._blob_paths.get(document_id)


class FakeBlobStorageClient:
    def __init__(self, content_by_path: dict[str, bytes]) -> None:
        self._content_by_path = content_by_path

    async def download(self, blob_path: str) -> bytes:
        return self._content_by_path[blob_path]


async def test_execute_sends_without_attachment_when_none_requested():
    mail_client = FakeGraphMailClient()
    use_case = SendEmailUseCase(
        FakeGraphTokenProvider(), mail_client, FakeDocumentRepository([], {}), FakeBlobStorageClient({})
    )
    proposal = EmailSendProposal(to="a@example.com", subject="Hi", body="Hello")

    await use_case.execute(user_oid="user-1", user_assertion="raw-jwt", proposal=proposal)

    assert len(mail_client.sent) == 1
    token, sent_proposal, attachment = mail_client.sent[0]
    assert token == "graph-token-for-user-1"
    assert sent_proposal == proposal
    assert attachment is None


async def test_execute_resolves_and_downloads_matching_ready_attachment():
    documents = [
        DocumentMetadata(id="doc-1", filename="resume.pdf", status="ready"),
        DocumentMetadata(id="doc-2", filename="resume.pdf", status="processing"),
    ]
    mail_client = FakeGraphMailClient()
    use_case = SendEmailUseCase(
        FakeGraphTokenProvider(),
        mail_client,
        FakeDocumentRepository(documents, {"doc-1": "user-1/doc-1-resume.pdf"}),
        FakeBlobStorageClient({"user-1/doc-1-resume.pdf": b"pdf bytes"}),
    )
    proposal = EmailSendProposal(to="a@example.com", subject="Hi", body="Hello", attachment_filename="resume.pdf")

    await use_case.execute(user_oid="user-1", user_assertion="raw-jwt", proposal=proposal)

    _, _, attachment = mail_client.sent[0]
    assert attachment == b"pdf bytes"


async def test_execute_raises_when_attachment_not_found():
    use_case = SendEmailUseCase(
        FakeGraphTokenProvider(), FakeGraphMailClient(), FakeDocumentRepository([], {}), FakeBlobStorageClient({})
    )
    proposal = EmailSendProposal(to="a@example.com", subject="Hi", body="Hello", attachment_filename="missing.pdf")

    with pytest.raises(AttachmentNotFoundError):
        await use_case.execute(user_oid="user-1", user_assertion="raw-jwt", proposal=proposal)


async def test_execute_raises_when_attachment_only_exists_for_another_status():
    documents = [DocumentMetadata(id="doc-1", filename="resume.pdf", status="failed")]
    use_case = SendEmailUseCase(
        FakeGraphTokenProvider(),
        FakeGraphMailClient(),
        FakeDocumentRepository(documents, {"doc-1": "user-1/doc-1-resume.pdf"}),
        FakeBlobStorageClient({}),
    )
    proposal = EmailSendProposal(to="a@example.com", subject="Hi", body="Hello", attachment_filename="resume.pdf")

    with pytest.raises(AttachmentNotFoundError):
        await use_case.execute(user_oid="user-1", user_assertion="raw-jwt", proposal=proposal)
