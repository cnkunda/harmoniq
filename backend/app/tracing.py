"""OpenTelemetry tracing setup for Harmoniq.

Configures distributed tracing with OTLP export for Jaeger/Zipkin visibility.
Falls back gracefully if OTEL dependencies are not installed.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("harmoniq.tracing")

_tracer_provider = None


def setup_tracing(service_name: str = "harmoniq-backend") -> None:
    """Initialize OpenTelemetry tracing with OTLP exporter.

    Args:
        service_name: Service name for trace identification.
    """
    global _tracer_provider

    if _tracer_provider is not None:
        return  # Already initialized

    enabled = os.getenv("OTEL_TRACING_ENABLED", "false").lower() in ("1", "true", "yes")
    if not enabled:
        logger.debug("OpenTelemetry tracing disabled (set OTEL_TRACING_ENABLED=true to enable)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create({
            "service.name": service_name,
            "service.version": os.getenv("HARMONIQ_VERSION", "0.1.0"),
        })

        provider = TracerProvider(resource=resource)

        # Console exporter for development
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))

        # OTLP exporter if endpoint is configured
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info("OTLP trace exporter configured endpoint=%s", otlp_endpoint)
            except ImportError:
                logger.warning("OTLP exporter not installed (pip install opentelemetry-exporter-otlp)")

        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        logger.info("OpenTelemetry tracing initialized service=%s", service_name)

    except ImportError:
        logger.warning("OpenTelemetry not installed — tracing disabled")


def get_tracer(name: str = "harmoniq"):
    """Get a tracer instance.

    Args:
        name: Tracer name (typically module name).

    Returns:
        A tracer instance, or a no-op tracer if tracing is disabled.
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    """No-op tracer fallback when OpenTelemetry is not available."""

    def start_as_current_span(self, name: str, **kwargs):
        """Return a no-op context manager."""

        class _NoOpSpan:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def set_attribute(self, key: str, value) -> None:
                pass

            def add_event(self, name: str, attributes=None) -> None:
                pass

            def set_status(self, status) -> None:
                pass

        return _NoOpSpan()
