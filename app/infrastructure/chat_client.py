import json
from collections.abc import AsyncIterator
from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

from app.domain.entities import ChatCompletionResult, ChatMessage, ToolCallRequest
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


def _to_openai_message(message: ChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in message.tool_calls
        ]
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if message.name:
        payload["name"] = message.name
    return payload


class AzureOpenAIChatClient:
    """Concrete implementation of the domain.ChatClient interface."""

    def __init__(self) -> None:
        self._client = _build_client()

    async def stream_completion(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[_to_openai_message(m) for m in messages],
            stream=True,
        )
        async for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta
            if delta and delta.content:
                yield delta.content

    async def complete_with_tools(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> ChatCompletionResult:
        response = await self._client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[_to_openai_message(m) for m in messages],
            tools=tools,
            tool_choice="auto",
        )
        message = response.choices[0].message

        tool_calls = [
            ToolCallRequest(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments or "{}"),
            )
            for tc in (message.tool_calls or [])
        ]

        return ChatCompletionResult(content=message.content, tool_calls=tool_calls)
