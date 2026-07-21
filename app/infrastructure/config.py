from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://atlas:atlas@localhost:5432/atlas"
    redis_url: str = "redis://localhost:6379/0"
    allowed_origins: list[str] = ["http://localhost:5173"]

    # Entra ID (Azure AD) app registration — see README "Entra ID setup"
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""  # the API's own App ID (JWT audience)
    entra_api_client_secret: str = ""  # used for the On-Behalf-Of exchange
    # Mail.ReadWrite (not Mail.Send) is what createReply/draft endpoints need —
    # Atlas never sends mail, so Mail.Send is deliberately not requested.
    graph_scopes: list[str] = [
        "https://graph.microsoft.com/User.Read",
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Calendars.ReadWrite",
    ]

    # Azure OpenAI (via Azure AI Foundry)
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-5-mini"
    azure_openai_api_version: str = "2024-10-21"
    # Optional: only set locally if you don't want to rely on `az login`
    # credentials. In Azure, leave unset — the Container App's managed
    # identity is used instead (see infra/modules/container-app-api.bicep).
    azure_openai_api_key: str = ""
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # Blob storage — defaults to the well-known Azurite emulator connection
    # string for local dev. In Azure, leave the connection string unset and
    # set azure_storage_account_url instead; auth falls back to managed
    # identity/`az login`, same pattern as Azure OpenAI.
    azure_storage_connection_string: str = (
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
        "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    )
    azure_storage_account_url: str = ""
    azure_storage_documents_container: str = "documents"

    # Azure AI Search — backs the search_documents MCP tool
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "documents"

    # Azure AI Document Intelligence — used by the blob-triggered Function
    # for OCR, not by the API itself, but the endpoint/key live here so both
    # processes read from the same place.
    azure_document_intelligence_endpoint: str = ""
    azure_document_intelligence_api_key: str = ""

    # Application Insights — leave unset locally to disable telemetry
    # entirely; the app and every MCP server subprocess check this before
    # doing anything OpenTelemetry-related.
    applicationinsights_connection_string: str = ""

    @property
    def entra_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}"

    @property
    def entra_jwks_uri(self) -> str:
        return f"{self.entra_authority}/discovery/v2.0/keys"

    @property
    def entra_issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}/v2.0"


settings = Settings()
