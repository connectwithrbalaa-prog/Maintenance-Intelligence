import os

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() in ("1", "true", "yes")


def init_tracing(app_name: str = "maintenance-intelligence"):
    if not OTEL_ENABLED:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        res = Resource.create({"service.name": app_name})
        provider = TracerProvider(resource=res)
        trace.set_tracer_provider(provider)
        exporter = OTLPSpanExporter()  # configure via OTEL_EXPORTER_OTLP_ENDPOINT
        provider.add_span_processor(BatchSpanProcessor(exporter))
        return provider
    except Exception:
        return None
