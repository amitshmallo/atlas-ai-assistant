import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

from app.domain.entities import ChatCompletionResult, ChatMessage, TokenUsage, ToolCallRequest
from app.infrastructure.config import settings
from app.infrastructure.resilience import retry_openai_call

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

    @retry_openai_call
    async def _create_stream(self, messages: list[ChatMessage]):
        return await self._client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[_to_openai_message(m) for m in messages],
            max_completion_tokens=settings.azure_openai_max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )

    async def stream_completion(
        self,
        messages: list[ChatMessage],
        on_usage: Callable[[TokenUsage], None] | None = None,
    ) -> AsyncIterator[str]:
        # Only the call that opens the stream is retried, not the iteration
        # below — a retry decorator on a generator function doesn't work as
        # you'd expect: calling it returns a generator object immediately
        # without running any code, so it can't catch failures that happen
        # partway through consuming a stream, only ones from starting it.
        stream = await self._create_stream(messages)
        async for event in stream:
            # The usage chunk (when stream_options.include_usage is set)
            # arrives last, with an empty choices list — it never carries
            # any content of its own.
            if event.usage:
                if on_usage:
                    on_usage(
                        TokenUsage(
                            prompt_tokens=event.usage.prompt_tokens,
                            completion_tokens=event.usage.completion_tokens,
                        )
                    )
                continue
            if not event.choices:
                continue
            delta = event.choices[0].delta
            if delta and delta.content:
                yield delta.content

    @retry_openai_call
    async def complete_with_tools(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> ChatCompletionResult:
        response = await self._client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[_to_openai_message(m) for m in messages],
            tools=tools,
            tool_choice="auto",
            max_completion_tokens=settings.azure_openai_max_tokens,
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

        usage = (
            TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
            if response.usage
            else None
        )

        return ChatCompletionResult(content=message.content, tool_calls=tool_calls, usage=usage)
