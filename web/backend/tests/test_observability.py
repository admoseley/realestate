"""Application Insights is configured only when a connection string is set."""
import re

import observability

CONNECTION_STRING = "InstrumentationKey=00000000-0000-0000-0000-000000000000"


def test_telemetry_stays_off_without_a_connection_string(monkeypatch):
    def unexpected(**_options):
        raise AssertionError("configure_azure_monitor must not be called")

    monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", unexpected)

    assert observability.configure({}) is False


def test_telemetry_is_configured_from_the_connection_string(monkeypatch):
    calls = []
    monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor",
                        lambda **options: calls.append(options))
    environ = {"APPLICATIONINSIGHTS_CONNECTION_STRING": CONNECTION_STRING}

    assert observability.configure(environ) is True
    assert calls == [{"logger_name": "realestate"}]
    assert environ["OTEL_PYTHON_FASTAPI_EXCLUDED_URLS"] == "api/health$"
    assert environ["OTEL_SERVICE_NAME"] == "realestate-api"


def test_explicit_opentelemetry_settings_take_precedence(monkeypatch):
    monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", lambda **_options: None)
    environ = {"APPLICATIONINSIGHTS_CONNECTION_STRING": CONNECTION_STRING,
               "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS": "custom", "OTEL_SERVICE_NAME": "other"}

    observability.configure(environ)

    assert environ["OTEL_PYTHON_FASTAPI_EXCLUDED_URLS"] == "custom"
    assert environ["OTEL_SERVICE_NAME"] == "other"


def test_only_the_health_probe_is_excluded_from_request_telemetry():
    pattern = re.compile(observability.HEALTH_PROBE_EXCLUSION)

    assert pattern.search("http://api.internal/api/health")
    assert not pattern.search("http://api.internal/api/health/db")
    assert not pattern.search("http://api.internal/api/reports")


def test_app_loggers_live_in_the_exported_namespace():
    assert observability.get_logger("jobs").name == "realestate.jobs"
