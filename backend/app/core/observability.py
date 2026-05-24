import logging
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

def filter_http_methods(_, __, event_dict):
    """Filter out logs that specify an HTTP method other than GET or POST."""
    method = event_dict.get("method") or event_dict.get("http_method")
    if method and str(method).upper() not in ["GET", "POST"]:
        raise structlog.DropEvent
    return event_dict

def setup_observability(app):
    """
    Initializes structured logging, OpenTelemetry tracing, and Prometheus metrics.
    """
    # 1. Structured Logging Setup (structlog)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            filter_http_methods,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
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
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    
    # Set global tracer provider
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI and HTTPX
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    # 3. Prometheus Metrics Setup
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return structlog.get_logger()