from collections.abc import AsyncIterator

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

from app.domain.entities import ChatMessage
from app.infrastructure.config import settings

_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


def _build_client() -> AsyncAzureOpenAI:
    if settings.azure_openai_api_key:
        return AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    # No API key configured: authenticate as the Container App's managed
    # identity in Azure (or the local `az login` principal in dev) instead
    # of a long-lived secret.
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), _COGNITIVE_SERVICES_SCOPE
    )
    return AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_ad_token_provider=token_provider,
        api_version=settings.azure_openai_api_version,
    )


class AzureOpenAIChatClient:
    """Concrete implementation of the domain.ChatClient interface."""

    def __init__(self) -> None:
        self._client = _build_client()

    async def stream_completion(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            stream=True,
        )
        async for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta
            if delta and delta.content:
                yield delta.content
