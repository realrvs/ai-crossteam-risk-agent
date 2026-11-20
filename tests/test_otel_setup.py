"""Tests for OpenTelemetry setup (TC-OBS-001)."""

from dep_agent.telemetry.otel_setup import (
    extract_request_id,
    extract_trace_id,
    get_tracer,
    record_commits_filtered,
    record_request_duration,
)


def test_setup_otel_console() -> None:
    """OTel should initialize without errors in console mode."""
    # setup_otel is already called in conftest
    tracer = get_tracer()
    assert tracer is not None


def test_extract_trace_id_from_headers() -> None:
    """Should extract trace_id from W3C traceparent header."""
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    headers = {"traceparent": traceparent}
    trace_id = extract_trace_id(headers)
    assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_extract_trace_id_no_headers() -> None:
    """Should generate new trace_id when no traceparent present."""
    trace_id = extract_trace_id()
    assert len(trace_id) == 32  # UUID hex is 32 chars


def test_extract_request_id_from_headers() -> None:
    """Should extract X-Request-ID from headers."""
    headers = {"X-Request-ID": "req-12345"}
    request_id = extract_request_id(headers)
    assert request_id == "req-12345"


def test_extract_request_id_no_headers() -> None:
    """Should generate UUID when no X-Request-ID present."""
    request_id = extract_request_id()
    assert len(request_id) == 32  # UUID hex is 32 chars


def test_get_tracer() -> None:
    """Should return a valid tracer."""
    tracer = get_tracer()
    assert tracer is not None


def test_record_commits_filtered() -> None:
    """Should record commits filtered metric without error."""
    record_commits_filtered(
        repo="org/service",
        outcome="dropped",
        trace_id="test-trace-123",
        count=5,
    )


def test_record_request_duration() -> None:
    """Should record request duration metric without error."""
    record_request_duration(
        operation="list_dependencies",
        status="200",
        duration_ms=150.5,
        trace_id="test-trace-123",
    )
