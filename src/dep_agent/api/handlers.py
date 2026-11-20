"""API handlers for dep_agent.

Implements HTTP endpoints with trace_id correlation:
- GET /v1/dependencies — list artifact dependencies
- GET /v1/blockers — list blocker candidates
- POST /v1/analysis/runs — trigger analysis pipeline

Covers FR-006, NFR-001, NFR-SEC-003, NFR-OBS-001.
TM Ref: TM-03 (read-only scope).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from dep_agent.config import Config
from dep_agent.detector.silence_detector import SilenceDetector
from dep_agent.graph.artifact_graph import ArtifactGraph
from dep_agent.ingestion.service import IngestionService
from dep_agent.telemetry.otel_setup import (
    extract_request_id,
    extract_trace_id,
    record_request_duration,
    run_span,
)

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    """Middleware to extract/generate trace_id and request_id."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def __call__(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        headers = {k: v for k, v in environ.items() if k.startswith("HTTP_")}
        # Normalize HTTP_ prefix
        headers = {
            k[5:].lower().replace("_", "-"): v for k, v in headers.items()
        }

        trace_id = extract_trace_id(headers)
        request_id = extract_request_id(headers)

        # Store in thread-local-like context
        import threading

        context = threading.local()
        context.trace_id = trace_id
        context.request_id = request_id

        # Inject into environ for handlers
        environ["dep_agent.trace_id"] = trace_id
        environ["dep_agent.request_id"] = request_id

        start_time = time.time()
        response_body: list[bytes] = []
        captured_status = "200 OK"

        def custom_start_response(
            status_code: str,
            response_headers: list[tuple[str, str]],
            exc_info: Any = None,
        ) -> None:
            nonlocal captured_status
            captured_status = status_code
            list(response_headers)
            # Add trace_id and request_id to response headers
            response_headers.append(("X-Trace-Id", trace_id))
            response_headers.append(("X-Request-Id", request_id))
            # Call the original start_response
            start_response(status_code, response_headers, exc_info)

        try:
            response_body = self._app(environ, custom_start_response)
            return response_body
        finally:
            duration_ms = (time.time() - start_time) * 1000
            status_code = captured_status.split()[0] if " " in captured_status else "200"
            record_request_duration(
                operation=environ.get("PATH_INFO", "unknown"),
                status=status_code,
                duration_ms=duration_ms,
                trace_id=trace_id,
            )


def get_dependencies_handler(
    environ: dict[str, Any],
    graph: ArtifactGraph,
) -> tuple[str, list[bytes]]:
    """Handle GET /v1/dependencies.

    Query params:
    - team: filter by team name
    - repo: filter by repository name
    """
    trace_id = environ.get("dep_agent.trace_id", "")
    request_id = environ.get("dep_agent.request_id", "")

    with run_span(
        "get_dependencies",
        {"trace_id": trace_id, "request_id": request_id},
    ):
        # Parse query params
        query_string = environ.get("QUERY_STRING", "")
        params: dict[str, str] = {}
        if query_string:
            for part in query_string.split("&"):
                if "=" in part:
                    key, value = part.split("=", 1)
                    params[key] = value

        team = params.get("team")
        repo = params.get("repo")

        deps = graph.get_dependencies(team=team, repo=repo)

        response_data = [
            {
                "source_repo": d.source_repo,
                "source_artifact": d.source_artifact,
                "source_team": d.source_team,
                "target_repo": d.target_repo,
                "target_team": d.target_team,
                "dependency_type": d.dependency_type,
            }
            for d in deps
        ]

        body = json.dumps(response_data, ensure_ascii=False).encode("utf-8")
        return "200 OK", [body]


def get_blockers_handler(
    environ: dict[str, Any],
    detector: SilenceDetector,
) -> tuple[str, list[bytes]]:
    """Handle GET /v1/blockers.

    Query params:
    - team: filter by team
    - min_risk_score: filter by minimum risk score
    """
    trace_id = environ.get("dep_agent.trace_id", "")
    request_id = environ.get("dep_agent.request_id", "")

    with run_span(
        "get_blockers",
        {"trace_id": trace_id, "request_id": request_id},
    ):
        query_string = environ.get("QUERY_STRING", "")
        params: dict[str, str] = {}
        if query_string:
            for part in query_string.split("&"):
                if "=" in part:
                    key, value = part.split("=", 1)
                    params[key] = value

        team = params.get("team")
        min_risk_score = params.get("min_risk_score")

        candidates = detector.get_candidates(
            team=team,
            min_risk_score=float(min_risk_score) if min_risk_score else None,
        )

        response_data = [
            {
                "source_repo": c.source_repo,
                "target_repo": c.target_repo,
                "artifact": c.artifact,
                "silence_days": c.silence_days,
                "silence_window_days": c.silence_window_days,
                "status": c.status,
                "detected_at": c.detected_at.isoformat() if c.detected_at else None,
            }
            for c in candidates
        ]

        body = json.dumps(response_data, ensure_ascii=False).encode("utf-8")
        return "200 OK", [body]


def run_analysis_handler(
    environ: dict[str, Any],
    config: Config,
    graph: ArtifactGraph,
    detector: SilenceDetector,
) -> tuple[str, list[bytes]]:
    """Handle POST /v1/analysis/runs.

    Body:
    {
        "repositories": ["org/repo1", "org/repo2"],
        "lookback_days": 14,
        "silence_window_days": 7
    }
    """
    trace_id = environ.get("dep_agent.trace_id", "")
    request_id = environ.get("dep_agent.request_id", "")

    with run_span(
        "run_analysis",
        {"trace_id": trace_id, "request_id": request_id},
    ):
        # Read request body
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        body = environ["wsgi.input"].read(content_length) if content_length else b"{}"

        try:
            request_data = json.loads(body)
        except json.JSONDecodeError:
            error_body = json.dumps({
                "error": "Invalid JSON body",
                "trace_id": trace_id,
            }).encode("utf-8")
            return "400 Bad Request", [error_body]

        repositories = request_data.get("repositories", [])
        lookback_days = request_data.get("lookback_days", 14)
        request_data.get("silence_window_days", 7)

        if not repositories:
            error_body = json.dumps({
                "error": "repositories is required",
                "trace_id": trace_id,
            }).encode("utf-8")
            return "400 Bad Request", [error_body]

        # Run ingestion for each repository
        results: list[dict[str, Any]] = []
        with IngestionService(config=config) as ingestion:
            for repo in repositories:
                result = ingestion.ingest(
                    repo=repo,
                    lookback_days=lookback_days,
                    trace_id=trace_id,
                )
                results.append({
                    "repo": repo,
                    "commits_ingested": result.commits_ingested,
                    "total_files_changed": result.total_files_changed,
                    "errors": result.errors,
                })

        # Run silence detection
        candidates = detector.detect(
            lookback_days=lookback_days,
            trace_id=trace_id,
        )

        response_data = {
            "run_id": request_id,
            "trace_id": trace_id,
            "repositories_processed": len(repositories),
            "ingestion_results": results,
            "blocker_candidates": len(candidates),
            "candidates": [
                {
                    "source_repo": c.source_repo,
                    "target_repo": c.target_repo,
                    "artifact": c.artifact,
                    "silence_days": c.silence_days,
                    "risk_score": c.risk_score,
                }
                for c in candidates
            ],
        }

        body = json.dumps(response_data, ensure_ascii=False).encode("utf-8")
        return "200 OK", [body]


def create_app(
    config: Config | None = None,
    graph: ArtifactGraph | None = None,
    detector: SilenceDetector | None = None,
) -> Any:
    """Create the WSGI application.

    Args:
        config: Application config.
        graph: Artifact graph instance.
        detector: Silence detector instance.

    Returns:
        WSGI application callable.
    """
    cfg = config or Config()
    g = graph or ArtifactGraph(config=cfg)
    d = detector or SilenceDetector(config=cfg)

    def application(
        environ: dict[str, Any],
        start_response: Any,
    ) -> list[bytes]:
        """WSGI application entry point."""
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET")

        try:
            if path == "/v1/dependencies" and method == "GET":
                status, body = get_dependencies_handler(environ, g)
            elif path == "/v1/blockers" and method == "GET":
                status, body = get_blockers_handler(environ, d)
            elif path == "/v1/analysis/runs" and method == "POST":
                status, body = run_analysis_handler(environ, cfg, g, d)
            elif path == "/health":
                status, body = "200 OK", [b'{"status": "ok"}']
            else:
                status, body = "404 Not Found", [
                    json.dumps({"error": "Not found"}).encode("utf-8")
                ]

            start_response(status, [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body[0]))),
            ])
            return body

        except Exception:
            logger.exception("Unhandled error")
            error_body = json.dumps({
                "error": "Internal server error",
                "trace_id": environ.get("dep_agent.trace_id", ""),
            }).encode("utf-8")
            start_response("500 Internal Server Error", [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(error_body))),
            ])
            return [error_body]

    return RequestIdMiddleware(application)
