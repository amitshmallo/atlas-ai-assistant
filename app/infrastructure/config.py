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
    graph_scopes: list[str] = ["https://graph.microsoft.com/User.Read"]

    # Azure OpenAI (via Azure AI Foundry)
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_version: str = "2024-10-21"
    # Optional: only set locally if you don't want to rely on `az login`
    # credentials. In Azure, leave unset — the Container App's managed
    # identity is used instead (see infra/modules/container-app-api.bicep).
    azure_openai_api_key: str = ""

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
