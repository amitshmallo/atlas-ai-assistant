"""Distributed tracing across process boundaries: the FastAPI app and every
MCP server subprocess it spawns (app/infrastructure/mcp_tool_provider.py)
all call configure_telemetry() and export to the same Application Insights
resource. A single chat turn that triggers a tool call therefore produces
one connected trace — API span, MCP subprocess span, and the outbound
Graph/Azure OpenAI HTTP calls each subprocess makes — not four disconnected
ones, because the W3C traceparent is propagated via an env var when the
subprocess is spawned (see inject_trace_context/extract_trace_context).

Telemetry is entirely opt-in: with no connection string configured (the
local dev default), every function here is a no-op, so nothing about
normal operation depends on Application Insights being reachable.
"""

import os
from contextlib import AbstractContextManager, nullcontext

from opentelemetry import trace
from opentelemetry.propagate import extract, inject

from app.infrastructure.config import settings

_TRACEPARENT_ENV_KEY = "TRACEPARENT"
_configured = False


def configure_telemetry(service_name: str) -> None:
    global _configured
    if _configured or not settings.applicationinsights_connection_string:
        return

    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    configure_azure_monitor(
        connection_string=settings.applicationinsights_connection_string,
        service_name=service_name,
    )
    # Auto-instruments FastAPI/SQLAlchemy/etc, but not httpx — that's what
    # both the openai SDK and every Graph client call use, so without this
    # explicit instrumentation the outbound Graph/Azure OpenAI calls
    # wouldn't show up as spans at all.
    HTTPXClientInstrumentor().instrument()
    _configured = True


def inject_trace_context() -> dict[str, str]:
    """Call from the parent process before spawning a subprocess that
    should be correlated into the same trace."""
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


def traced_subprocess_span(tracer_name: str, span_name: str) -> AbstractContextManager:
    """Call from inside a spawned subprocess (an MCP server). Reads the
    TRACEPARENT env var injected by the parent via inject_trace_context()
    and starts a span parented to it, so this subprocess's work shows up
    as a child of the API request that spawned it rather than as an
    unrelated trace. No-ops (returns a null context) if telemetry isn't
    configured, so this is always safe to wrap tool bodies in."""
    if not settings.applicationinsights_connection_string:
        return nullcontext()

    traceparent = os.environ.get(_TRACEPARENT_ENV_KEY)
    parent_context = extract({"traceparent": traceparent}) if traceparent else None
    tracer = trace.get_tracer(tracer_name)
    return tracer.start_as_current_span(span_name, context=parent_context)
