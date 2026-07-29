import logging

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "detail": f"Rate limit exceeded: {exc.detail}"},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Registered against the base Exception type to guarantee every route
    # returns structured JSON instead of an unhandled-error stack trace, but
    # HTTPException (401s, 404s, the deliberate ones already raised
    # throughout app/api/routers/*) needs to keep going through FastAPI's
    # own handler — otherwise this would swallow them and turn every
    # expected 4xx into a generic 500.
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)

    # Genuine bugs only get here. Deliberately no exc message/traceback in
    # the response — that's for the logs (and Application Insights, since
    # exception logging propagates there), not the client.
    logger.exception("Unhandled exception processing request", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "An unexpected error occurred."},
    )
