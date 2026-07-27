"""Shared retry policy for outbound calls to Microsoft Graph and Azure
OpenAI — both are rate-limited and occasionally return transient 5xx/429
responses that succeed on a bare retry. Exponential backoff with a small
cap keeps a flaky external call from turning into a multi-second stall on
every single chat turn.
"""

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_transient_httpx_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def _is_transient_openai_error(exc: BaseException) -> bool:
    if isinstance(exc, RateLimitError | APIConnectionError | APITimeoutError):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


retry_graph_call = retry(
    retry=retry_if_exception(_is_transient_httpx_error),
    wait=wait_exponential(multiplier=0.5, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)

retry_openai_call = retry(
    retry=retry_if_exception(_is_transient_openai_error),
    wait=wait_exponential(multiplier=0.5, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
