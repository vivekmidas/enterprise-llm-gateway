# src/core/observability.py
import structlog
import sys
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram 



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

# ========================= METRICS (M in MELT) =========================
REQUEST_COUNTER = Counter(
    'http_requests_total', 
    'Total HTTP requests', 
    ['method', 'endpoint', 'status_code']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint']
)

TOKEN_USAGE = Counter(
    'llm_tokens_total',
    'Total tokens used by LLMs',
    ['provider', 'model', 'direction']  # direction: input/output
)

# ========================= STRUCTLOG SETUP (L + E in MELT) =========================
def setup_structlog():
    """Configure structlog - single place for all logging config"""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    # Pretty console in dev, JSON in production
    if sys.stdout.isatty():
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

logger = structlog.get_logger("enterprise_llm_gateway")


# ========================= TRACING (T in MELT) =========================
def setup_tracing():
    """OpenTelemetry tracing setup"""
    trace.set_tracer_provider(TracerProvider())
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4317"))  # configurable later
    )


# ========================= MAIN SETUP =========================
def setup_observability(app):
    """Call this once in main.py - full MELT in one function"""
    setup_structlog()
    setup_tracing()
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    logger.info("Observability initialized with structlog + OpenTelemetry + Prometheus")
    return app


# Helper for easy structured logging
def get_logger():
    return logger