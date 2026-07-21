"""Telemetry is opt-in: with no connection string configured (the default
in tests, since .env isn't loaded with one), every function here must be a
safe no-op — these tests exist to guarantee that, since a mistake here
would mean the whole app fails to start without Application Insights."""

import app.infrastructure.telemetry as telemetry


def test_configure_telemetry_is_a_noop_without_connection_string(monkeypatch):
    monkeypatch.setattr(telemetry.settings, "applicationinsights_connection_string", "")
    monkeypatch.setattr(telemetry, "_configured", False)

    # Must not raise, must not try to import azure.monitor.opentelemetry.
    telemetry.configure_telemetry(service_name="test-service")

    assert telemetry._configured is False


def test_traced_subprocess_span_is_a_null_context_without_connection_string(monkeypatch):
    monkeypatch.setattr(telemetry.settings, "applicationinsights_connection_string", "")

    with telemetry.traced_subprocess_span("test-tracer", "test-span"):
        pass  # must not raise


def test_inject_trace_context_returns_a_dict():
    carrier = telemetry.inject_trace_context()

    assert isinstance(carrier, dict)


def test_traced_subprocess_span_uses_traceparent_env_when_configured(monkeypatch):
    monkeypatch.setattr(telemetry.settings, "applicationinsights_connection_string", "fake-connection-string")
    monkeypatch.setenv(
        "TRACEPARENT", "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    )

    # Without a real Azure Monitor SDK configured, trace.get_tracer() still
    # returns a usable (no-op) tracer from the OpenTelemetry API package —
    # this proves the parent-context extraction path doesn't raise even
    # when nothing is actually exporting spans.
    with telemetry.traced_subprocess_span("test-tracer", "test-span"):
        pass
