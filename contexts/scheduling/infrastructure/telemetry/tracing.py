"""OpenTelemetry tracing (SPEC §9): HTTP -> use case -> SQL spans, W3C `traceparent`
propagation, exported over OTLP when OTEL_EXPORTER_OTLP_ENDPOINT is set."""

from django.conf import settings
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False


def configure_tracing(service_name: str = "unified-service-scheduler") -> None:
    """Call once per process before the WSGI app loads (gunicorn workers import wsgi.py
    after forking, so each worker gets its own exporter thread)."""
    global _configured
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if _configured or not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    DjangoInstrumentor().instrument(excluded_urls="healthz,readyz,metrics")
    PsycopgInstrumentor().instrument(enable_commenter=False)
    _configured = True
