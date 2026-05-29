import logging
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator
from rich.console import Console
from rich.traceback import install

class FilterInternalSpansProcessor(BatchSpanProcessor):
    """Filters out spans with SpanKind.INTERNAL to reduce terminal noise."""
    def on_end(self, span: ReadableSpan) -> None:
        # Do not process/export spans that are marked as INTERNAL
        if span.kind == trace.SpanKind.INTERNAL:
            return
        super().on_end(span)

def filter_http_methods(_, __, event_dict):
    """Filter out logs that specify an HTTP method other than GET or POST."""
    method = event_dict.get("method") or event_dict.get("http_method")
    if method and str(method).upper() not in ["GET", "POST"] :
        raise structlog.DropEvent
    print(event_dict)
    name = event_dict.get("name")
    return event_dict

def setup_observability(app):
    """
    Initializes structured logging, OpenTelemetry tracing, and Prometheus metrics.
    """
    console = Console()
    install()
    # 1. Structured Logging Setup (structlog)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            filter_http_methods,
            structlog.dev.set_exc_info,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 2. OpenTelemetry Tracing Setup
    # Define the service resource
    resource = Resource.create({"service.name": "enterprise-llm-gateway"})
    
    # Initialize TracerProvider
    provider = TracerProvider(resource=resource)
    
    # Use ConsoleSpanExporter for development. In production, use OTLPSpanExporter.
    processor = FilterInternalSpansProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    
    # Set global tracer provider
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI and HTTPX
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    # 3. Prometheus Metrics Setup
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return structlog.get_logger()