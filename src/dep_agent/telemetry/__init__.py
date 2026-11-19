"""Telemetry package for dep_agent."""

from dep_agent.telemetry.otel_setup import (
    extract_request_id,
    extract_trace_id,
    get_tracer,
    log_blocker_detected,
    record_commits_filtered,
    record_llm_validation_duration,
    record_request_duration,
    run_span,
    setup_otel,
)

__all__ = [
    "setup_otel",
    "get_tracer",
    "extract_trace_id",
    "extract_request_id",
    "run_span",
    "record_request_duration",
    "record_commits_filtered",
    "record_llm_validation_duration",
    "log_blocker_detected",
]
