"""Application Insights telemetry through OpenTelemetry, switched on by configuration.

When ``APPLICATIONINSIGHTS_CONNECTION_STRING`` is set (in Azure, a Container
App setting), the Azure Monitor OpenTelemetry distro sends incoming requests,
outgoing HTTP calls (county data, map tiles, Blob Storage), exceptions,
metrics, and warnings logged under the ``realestate`` logger namespace to
Application Insights. When it isn't set, nothing is configured: local
development, tests, and Render run as before.

``configure()`` must run before ``fastapi.FastAPI`` is imported. The FastAPI
instrumentation replaces that class, and an app built from a class imported
earlier records no requests at all (checked against
azure-monitor-opentelemetry 1.8.10).
"""
import logging
import os
from typing import MutableMapping

# Only loggers under this namespace are exported. Naming one explicitly keeps
# the SDK's own log messages out of Application Insights, as the distro's
# documentation requires. Get loggers through get_logger() below.
LOGGER_NAMESPACE = "realestate"

# Container Apps probes /api/health every few seconds. Recorded as requests,
# the probes would dominate ingestion (and cost) and bury real traffic. The
# value is a regex searched within the URL, so /api/health/db, the database
# wake-up call the frontend makes, is still recorded.
HEALTH_PROBE_EXCLUSION = "api/health$"

# The role name Application Insights shows for this service.
SERVICE_NAME = "realestate-api"


def configure(environ: MutableMapping[str, str] = os.environ) -> bool:
    """Turn on Application Insights when a connection string is configured.

    Returns whether telemetry was enabled. Explicit OTEL_* settings take
    precedence over the defaults applied here.
    """
    if not environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return False
    environ.setdefault("OTEL_PYTHON_FASTAPI_EXCLUDED_URLS", HEALTH_PROBE_EXCLUSION)
    environ.setdefault("OTEL_SERVICE_NAME", SERVICE_NAME)

    # Imported only here: it's a heavy import, and pointless when disabled.
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(logger_name=LOGGER_NAMESPACE)
    return True


def get_logger(name: str) -> logging.Logger:
    """A logger inside the exported namespace, named ``realestate.<name>``."""
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")
