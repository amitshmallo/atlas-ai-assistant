from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

from app.infrastructure.config import settings


def _build_client() -> BlobServiceClient:
    if settings.azure_storage_connection_string:
        return BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)

    # No connection string configured: authenticate as the Container App's
    # managed identity in Azure (or the local `az login` principal in dev),
    # same pattern as AzureOpenAIChatClient.
    return BlobServiceClient(account_url=settings.azure_storage_account_url, credential=DefaultAzureCredential())


class AzureBlobStorageClient:
    """Concrete implementation of the domain.BlobStorageClient interface.
    Uploads land in a container a blob-triggered Azure Function watches —
    see azure_functions/document_processor."""

    def __init__(self) -> None:
        self._client = _build_client()

    async def upload(self, blob_path: str, content: bytes) -> None:
        container_client = self._client.get_container_client(settings.azure_storage_documents_container)
        try:
            await container_client.create_container()
        except ResourceExistsError:
            pass
        await container_client.upload_blob(name=blob_path, data=content, overwrite=True)
