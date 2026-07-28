from app.domain.entities import EmailSendProposal
from app.domain.interfaces import BlobStorageClient, DocumentRepository, GraphMailClient, GraphTokenProvider


class AttachmentNotFoundError(Exception):
    """Raised when proposal.attachment_filename doesn't match any of the
    requesting user's own ready documents — never any other user's, since
    the lookup is always scoped to user_oid."""


class SendEmailUseCase:
    """Exchanges the caller's JWT for a Graph token (On-Behalf-Of), then
    actually sends the email. This is the only path that can send mail —
    the model's propose_send_email tool never calls Graph itself, so this
    use case only runs when the user explicitly confirms via a direct API
    call, not as a side effect of chat (same pattern as
    CreateCalendarEventUseCase).

    attachment_filename on the proposal is resolved to a real document
    here, not trusted from the model — it's matched against the
    requesting user's own documents only, so there's no way for a prompt
    to exfiltrate another user's file by guessing a filename."""

    def __init__(
        self,
        token_provider: GraphTokenProvider,
        mail_client: GraphMailClient,
        document_repository: DocumentRepository,
        blob_storage_client: BlobStorageClient,
    ) -> None:
        self._token_provider = token_provider
        self._mail_client = mail_client
        self._document_repository = document_repository
        self._blob_storage_client = blob_storage_client

    async def execute(self, user_oid: str, user_assertion: str, proposal: EmailSendProposal) -> None:
        attachment_content: bytes | None = None
        if proposal.attachment_filename:
            attachment_content = await self._resolve_attachment(user_oid, proposal.attachment_filename)

        graph_token = await self._token_provider.get_graph_token(user_oid, user_assertion)
        await self._mail_client.send_email(graph_token, proposal, attachment_content)

    async def _resolve_attachment(self, user_oid: str, filename: str) -> bytes:
        documents = await self._document_repository.list_documents(user_oid)
        match = next((d for d in documents if d.filename == filename and d.status == "ready"), None)
        if match is None:
            raise AttachmentNotFoundError(filename)

        blob_path = await self._document_repository.get_blob_path(match.id)
        if blob_path is None:
            raise AttachmentNotFoundError(filename)

        return await self._blob_storage_client.download(blob_path)
