"""OpenTelemetry setup for dep_agent.

Configures:
- W3C traceparent extraction/generation
- X-Request-ID propagation (UUID if missing)
- Prometheus metrics: request.duration, commits.filtered_total, llm.validation.duration
- Span: dep_agent.run.span
- OTel exporter (console/OTLP)

Covers NFR-001, NFR-OBS-001.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.semconv.attributes.service_attributes import SERVICE_NAME
from opentelemetry.trace import Span, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

# Prometheus metrics (created once)
_request_duration_histogram: Any = None
_commits_filtered_counter: Any = None
_llm_validation_duration_histogram: Any = None


def setup_otel(
    service_name: str = "dep-agent",
    exporter: str = "console",
    otlp_endpoint: str = "localhost:4317",
    sampling_rate: float = 1.0,
) -> None:
    """Initialize OpenTelemetry SDK.

    Args:
        service_name: Service name for resource attributes.
        exporter: Exporter type — "console", "otlp-grpc", "otlp-http".
        otlp_endpoint: OTLP collector endpoint.
        sampling_rate: Trace sampling rate (0.0..1.0).
    """
    resource = Resource.create({SERVICE_NAME: service_name})

    # Tracer provider
    if sampling_rate >= 1.0:
        sampler = ALWAYS_ON
    else:
        from opentelemetry.sdk.trace.sampling import ParentBasedAlwaysSample
        sampler = ParentBasedAlwaysSample()

    provider = TracerProvider(resource=resource, sampler=sampler)

    if exporter == "console":
        processor = BatchSpanProcessor(ConsoleSpanExporter())
    elif exporter in ("otlp-grpc", "otlp-http"):
        if exporter == "otlp-grpc":
            span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, secure=True)
        else:
            span_exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
        processor = BatchSpanProcessor(span_exporter)
    else:
        processor = BatchSpanProcessor(ConsoleSpanExporter())

    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Metrics
    if exporter == "console":
        metric_reader = None  # No periodic export for console
    else:
        if exporter == "otlp-grpc":
            metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
        else:
            metric_exporter = OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics")
        metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30000)
        if metric_reader:
            metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    # Initialize metrics
    _init_metrics()


def _init_metrics() -> None:
    """Create Prometheus-compatible metrics."""
    global _request_duration_histogram, _commits_filtered_counter, _llm_validation_duration_histogram

    meter = metrics.get_meter("dep_agent")

    _request_duration_histogram = meter.create_histogram(
        name="dep_agent.request.duration",
        unit="ms",
        description="Request duration in milliseconds",
    )

    _commits_filtered_counter = meter.create_counter(
        name="dep_agent.commits.filtered_total",
        unit="1",
        description="Total commits filtered",
    )

    _llm_validation_duration_histogram = meter.create_histogram(
        name="dep_agent.llm.validation.duration",
        unit="ms",
        description="LLM validation duration in milliseconds",
    )


def get_tracer(name: str = "dep_agent") -> Tracer:
    """Get the configured tracer."""
    return trace.get_tracer(name)


def extract_trace_id(headers: dict[str, str] | None = None) -> str:
    """Extract or generate trace_id.

    Args:
        headers: Incoming request headers (may contain traceparent).

    Returns:
        trace_id string.
    """
    propagator = TraceContextTextMapPropagator()
    ctx = propagator.extract(carrier=headers or {})
    span = trace.get_current_span(ctx)
    if span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return uuid.uuid4().hex


def extract_request_id(headers: dict[str, str] | None = None) -> str:
    """Extract or generate X-Request-ID.

    Args:
        headers: Incoming request headers.

    Returns:
        Request ID string.
    """
    if headers:
        request_id = headers.get("X-Request-ID") or headers.get("x-request-id")
        if request_id:
            return request_id
    return uuid.uuid4().hex


@contextmanager
def run_span(
    operation: str,
    extra_attributes: dict[str, Any] | None = None,
) -> Generator[Span, None, None]:
    """Context manager for creating a dep_agent.run.span.

    Usage:
        with run_span("ingestion", {"repo": "org/service"}):
            # ... work ...
    """
    tracer = get_tracer()
    attributes = extra_attributes or {}
    attributes.setdefault("operation", operation)

    with tracer.start_as_current_span(f"dep_agent.run.{operation}", attributes=attributes) as span:
        yield span


def record_request_duration(operation: str, status: str, duration_ms: float, trace_id: str) -> None:
    """Record request duration metric.

    Args:
        operation: Operation name (e.g. "list_dependencies").
        status: Response status (e.g. "200", "error").
        duration_ms: Duration in milliseconds.
        trace_id: Trace ID for correlation.
    """
    if _request_duration_histogram:
        _request_duration_histogram.record(
            duration_ms,
            attributes={
                "operation": operation,
                "status": status,
                "trace_id": trace_id,
            },
        )


def record_commits_filtered(repo: str, outcome: str, trace_id: str, count: int = 1) -> None:
    """Record commits filtered metric.

    Args:
        repo: Repository name.
        outcome: "kept" or "dropped".
        trace_id: Trace ID for correlation.
        count: Number of commits.
    """
    if _commits_filtered_counter:
        _commits_filtered_counter.add(
            count,
            attributes={
                "repo": repo,
                "outcome": outcome,
                "trace_id": trace_id,
            },
        )


def record_llm_validation_duration(model: str, risk_level: str, duration_ms: float, trace_id: str) -> None:
    """Record LLM validation duration metric.

    Args:
        model: LLM model name.
        risk_level: Assessed risk level.
        duration_ms: Duration in milliseconds.
        trace_id: Trace ID for correlation.
    """
    if _llm_validation_duration_histogram:
        _llm_validation_duration_histogram.record(
            duration_ms,
            attributes={
                "model": model,
                "risk_level": risk_level,
                "trace_id": trace_id,
            },
        )


def log_blocker_detected(
    source_repo: str,
    target_repo: str,
    risk_score: float,
    trace_id: str,
) -> None:
    """Log a detected blocker candidate.

    Emits structured log for Loki ingestion.
    """
    logger.warning(
        "dep_agent.blocker.detected",
        extra={
            "source_repo": source_repo,
            "target_repo": target_repo,
            "risk_score": risk_score,
            "trace_id": trace_id,
        },
    )
