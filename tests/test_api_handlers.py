"""Tests for API handlers (TC-006, TC-SEC-003)."""

import json
from io import BytesIO

from dep_agent.api.handlers import (
    create_app,
    get_blockers_handler,
    get_dependencies_handler,
    run_analysis_handler,
)
from dep_agent.config import Config
from dep_agent.detector.silence_detector import SilenceDetector
from dep_agent.graph.artifact_graph import ArtifactGraph


def create_mock_environ(
    path: str = "/v1/dependencies",
    method: str = "GET",
    query_string: str = "",
    body: bytes = b"{}",
) -> dict:
    """Create a mock WSGI environ dict."""
    return {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "QUERY_STRING": query_string,
        "CONTENT_LENGTH": len(body),
        "wsgi.input": BytesIO(body),
        "dep_agent.trace_id": "test-trace-123",
        "dep_agent.request_id": "test-request-456",
    }


def test_create_app() -> None:
    """create_app should return a WSGI callable."""
    app = create_app()
    assert callable(app)


def test_get_dependencies_handler_no_deps() -> None:
    """Should return empty list when no dependencies exist."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        environ = create_mock_environ("/v1/dependencies")
        status, body = get_dependencies_handler(environ, graph)
        assert status == "200 OK"
        data = json.loads(body[0])
        assert data == []
    finally:
        graph.close()


def test_get_dependencies_handler_with_deps() -> None:
    """Should return dependencies with full info."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        source = graph.add_artifact(
            repo="org/billing",
            artifact_path="openapi/api.yaml",
            artifact_type="openapi_contract",
            team="team-billing",
        )
        target = graph.add_artifact(
            repo="org/mobile",
            artifact_path="src/api/client.ts",
            artifact_type="package_manifest",
            team="team-mobile",
        )
        graph.add_dependency(source.id, target.id, "openapi_contract")

        environ = create_mock_environ("/v1/dependencies")
        status, body = get_dependencies_handler(environ, graph)
        assert status == "200 OK"
        data = json.loads(body[0])
        assert len(data) == 1
        assert data[0]["source_repo"] == "org/billing"
        assert data[0]["target_repo"] == "org/mobile"
    finally:
        graph.close()


def test_get_dependencies_handler_filtered_by_team() -> None:
    """Should filter dependencies by team query param."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        graph.add_artifact(
            repo="org/service-a",
            artifact_path="openapi/a.yaml",
            artifact_type="openapi_contract",
            team="team-a",
        )
        graph.add_artifact(
            repo="org/service-b",
            artifact_path="openapi/b.yaml",
            artifact_type="openapi_contract",
            team="team-b",
        )

        environ = create_mock_environ(
            "/v1/dependencies",
            query_string="team=team-a",
        )
        status, body = get_dependencies_handler(environ, graph)
        assert status == "200 OK"
    finally:
        graph.close()


def test_get_blockers_handler_empty() -> None:
    """Should return empty list when no blockers exist."""
    detector = SilenceDetector(db_url="sqlite:///:memory:")
    try:
        environ = create_mock_environ("/v1/blockers")
        status, body = get_blockers_handler(environ, detector)
        assert status == "200 OK"
        data = json.loads(body[0])
        assert data == []
    finally:
        detector.close()


def test_get_blockers_handler_filtered() -> None:
    """Should filter blockers by team and min_risk_score."""
    detector = SilenceDetector(db_url="sqlite:///:memory:")
    try:
        environ = create_mock_environ(
            "/v1/blockers",
            query_string="team=team-billing&min_risk_score=3",
        )
        status, body = get_blockers_handler(environ, detector)
        assert status == "200 OK"
    finally:
        detector.close()


def test_run_analysis_handler_no_repositories() -> None:
    """Should return 400 when repositories is empty."""
    config = Config()
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    detector = SilenceDetector(db_url="sqlite:///:memory:")
    try:
        body = json.dumps({"repositories": []}).encode("utf-8")
        environ = create_mock_environ(
            "/v1/analysis/runs",
            method="POST",
            body=body,
        )
        status, response = run_analysis_handler(environ, config, graph, detector)
        assert status == "400 Bad Request"
        data = json.loads(response[0])
        assert "error" in data
    finally:
        graph.close()
        detector.close()


def test_run_analysis_handler_invalid_json() -> None:
    """Should return 400 for invalid JSON body."""
    config = Config()
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    detector = SilenceDetector(db_url="sqlite:///:memory:")
    try:
        environ = create_mock_environ(
            "/v1/analysis/runs",
            method="POST",
            body=b"not json",
        )
        status, response = run_analysis_handler(environ, config, graph, detector)
        assert status == "400 Bad Request"
    finally:
        graph.close()
        detector.close()


def test_run_analysis_handler_success() -> None:
    """Should return 200 with analysis results."""
    config = Config()
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    detector = SilenceDetector(db_url="sqlite:///:memory:")
    try:
        body = json.dumps({
            "repositories": ["org/test-repo"],
            "lookback_days": 14,
        }).encode("utf-8")
        environ = create_mock_environ(
            "/v1/analysis/runs",
            method="POST",
            body=body,
        )
        status, response = run_analysis_handler(environ, config, graph, detector)
        assert status == "200 OK"
        data = json.loads(response[0])
        assert "run_id" in data
        assert "trace_id" in data
        assert "repositories_processed" in data
        assert "ingestion_results" in data
        assert "blocker_candidates" in data
    finally:
        graph.close()
        detector.close()


def test_wsgi_app_routing() -> None:
    """WSGI app should route requests correctly."""
    app = create_app()

    # Health check
    environ = create_mock_environ("/health")

    responses = []

    def mock_start_response(status, headers, *args):
        responses.append((status, headers))

    result = app(environ, mock_start_response)
    assert len(responses) == 1
    assert responses[0][0] == "200 OK"
    data = json.loads(result[0])
    assert data["status"] == "ok"


def test_wsgi_app_404() -> None:
    """WSGI app should return 404 for unknown paths."""
    app = create_app()

    environ = create_mock_environ("/unknown/path")

    responses = []

    def mock_start_response(status, headers, *args):
        responses.append((status, headers))

    app(environ, mock_start_response)
    assert len(responses) == 1
    assert "404" in responses[0][0]


def test_wsgi_app_adds_trace_id_header() -> None:
    """WSGI app should add X-Trace-Id header."""
    app = create_app()

    environ = create_mock_environ("/health")
    # Pass traceparent header to control trace_id
    environ["HTTP_TRACEPARENT"] = "00-1d68870a5ead429cad38392d966130e7-00f067aa0ba902b7-01"
    environ["HTTP_X_REQUEST_ID"] = "custom-request-id"

    responses = []

    def mock_start_response(status, headers, *args):
        responses.append((status, headers))

    app(environ, mock_start_response)
    assert len(responses) == 1
    headers = dict(responses[0][1])
    assert headers.get("X-Trace-Id") == "1d68870a5ead429cad38392d966130e7"
    assert headers.get("X-Request-Id") == "custom-request-id"
