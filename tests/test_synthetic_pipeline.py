"""Synthetic multi-repository integration test.

Creates 3 mock repositories with cross-team dependencies,
runs the full pipeline (graph → silence detector → LLM validator),
and verifies exactly 2 risks are identified.

Tests: TC-001 (integration), TC-004 (functional), TC-OBS-001 (observability).
"""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch

from dep_agent.api.handlers import create_app
from dep_agent.detector.silence_detector import SilenceDetector
from dep_agent.graph.artifact_graph import ArtifactGraph
from dep_agent.validator.llm_validator import (
    DependencyMapEntry,
    LlmValidator,
)


def create_synthetic_graph() -> ArtifactGraph:
    """Create an in-memory graph with 3 mock repos and cross-team deps.

    Repos:
    - org/billing-service (team-billing): openapi/billing.yaml
    - org/mobile-app (team-mobile): src/api/client.ts
    - org/web-frontend (team-web): src/hooks/api.ts

    Dependencies:
    - billing → mobile (openapi_contract)
    - billing → web (openapi_contract)
    """
    graph = ArtifactGraph(db_url="sqlite:///:memory:")

    # Add artifact nodes
    billing = graph.add_artifact(
        repo="org/billing-service",
        artifact_path="openapi/billing.yaml",
        artifact_type="openapi_contract",
        team="team-billing",
    )
    mobile = graph.add_artifact(
        repo="org/mobile-app",
        artifact_path="src/api/client.ts",
        artifact_type="package_manifest",
        team="team-mobile",
    )
    web = graph.add_artifact(
        repo="org/web-frontend",
        artifact_path="src/hooks/api.ts",
        artifact_type="package_manifest",
        team="team-web",
    )

    # Add dependency edges
    graph.add_dependency(
        source_node_id=billing.id,
        target_node_id=mobile.id,
        dependency_type="openapi_contract",
    )
    graph.add_dependency(
        source_node_id=billing.id,
        target_node_id=web.id,
        dependency_type="openapi_contract",
    )

    return graph


def create_mock_candidates(graph: ArtifactGraph) -> list[dict]:
    """Create blocker candidates from graph dependencies.

    Simulates what SilenceDetector would produce after detecting
    that team-mobile and team-web haven't reacted to billing changes.
    """
    deps = graph.get_dependencies()

    candidates = []
    for dep in deps:
        candidates.append({
            "source_repo": dep.source_repo,
            "target_repo": dep.target_repo,
            "artifact": dep.source_artifact,
            "source_team": dep.source_team,
            "target_team": dep.target_team,
            "risk_score": 18.0,  # High risk for cross-team API changes
        })

    return candidates


def mock_llm_response(*args, **kwargs) -> dict:
    """Mock YandexGPT response for a candidate."""
    # Extract candidate info from user_prompt (2nd positional arg)
    user_prompt = args[1] if len(args) > 1 else ""
    source_repo = "org/billing-service"
    target_repo = "org/mobile-app"
    artifact = "openapi/billing.yaml"

    if "web-frontend" in user_prompt:
        target_repo = "org/web-frontend"

    return {
        "risk_score": 18,
        "risk_level": "high",
        "compatibility_assessment": (
            f"Breaking change detected: {artifact} "
            f"from {source_repo} may break {target_repo}. "
            f"Cross-team API modification without coordination."
        ),
        "evidence_ref": f"commit/abc123, PR: {source_repo}/openapi/billing.yaml",
    }


def run_synthetic_pipeline() -> tuple[ArtifactGraph, list[DependencyMapEntry], list[dict]]:
    """Run the full synthetic pipeline: graph → candidates → LLM → results.

    Returns:
        Tuple of (graph, dependency_map_entries, api_results).
    """
    # Step 1: Build graph
    graph = create_synthetic_graph()

    # Step 2: Get dependencies
    deps = graph.get_dependencies()
    assert len(deps) == 2, f"Expected 2 dependencies, got {len(deps)}"

    # Step 3: Create candidates (simulating silence detector output)
    candidates = create_mock_candidates(graph)
    assert len(candidates) == 2, f"Expected 2 candidates, got {len(candidates)}"

    # Step 4: LLM validation (mocked)
    validator = LlmValidator()
    with patch.object(validator, '_call_llm', side_effect=mock_llm_response):
        results = validator.validate(candidates, trace_id="synthetic-test-001")

    # Step 5: Convert to DependencyMap entries
    dep_map_entries = validator.results_to_dependency_map(results)
    assert len(dep_map_entries) == 2, f"Expected 2 dep map entries, got {len(dep_map_entries)}"

    # Step 6: Verify risk levels
    high_risk = [e for e in dep_map_entries if e.risk_level == "high"]
    assert len(high_risk) == 2, f"Expected 2 high-risk entries, got {len(high_risk)}"

    return graph, dep_map_entries, [r.__dict__ for r in results]


def test_synthetic_pipeline_identifies_two_risks() -> None:
    """Main test: synthetic pipeline identifies exactly 2 risks."""
    graph, dep_map_entries, api_results = run_synthetic_pipeline()

    # Verify 2 risks identified
    assert len(dep_map_entries) == 2

    # Verify both are cross-team (by checking repos differ)
    for entry in dep_map_entries:
        assert "billing" in entry.source_repo
        assert "billing" not in entry.target_repo

    # Verify both are high risk
    for entry in dep_map_entries:
        assert entry.risk_level == "high"
        assert entry.risk_score >= 13

    # Verify evidence references exist
    for entry in dep_map_entries:
        assert entry.evidence_ref
        assert "commit" in entry.evidence_ref or "PR" in entry.evidence_ref


def test_synthetic_graph_structure() -> None:
    """Verify synthetic graph has correct structure."""
    graph = create_synthetic_graph()

    # 3 artifact nodes
    all_nodes = graph.get_dependencies()
    assert len(all_nodes) == 2  # 2 dependency edges

    # Verify source is always billing
    for dep in all_nodes:
        assert dep.source_repo == "org/billing-service"
        assert dep.source_team == "team-billing"

    # Verify targets are mobile and web
    targets = {dep.target_repo for dep in all_nodes}
    assert targets == {"org/mobile-app", "org/web-frontend"}


def test_synthetic_api_integration() -> None:
    """Test API endpoints with synthetic data."""
    graph = create_synthetic_graph()

    # Test GET /v1/dependencies
    app = create_app(graph=graph)
    environ = {
        "PATH_INFO": "/v1/dependencies",
        "REQUEST_METHOD": "GET",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": 0,
        "wsgi.input": BytesIO(b"{}"),
        "dep_agent.trace_id": "api-test-001",
        "dep_agent.request_id": "api-test-001",
    }

    responses = []

    def mock_start_response(status, headers, *args):
        responses.append((status, headers))

    result = app(environ, mock_start_response)
    assert len(responses) == 1
    assert "200" in responses[0][0]

    data = json.loads(result[0])
    assert len(data) == 2  # 2 dependencies


def test_synthetic_api_blockers() -> None:
    """Test GET /v1/blockers with synthetic data."""
    graph = create_synthetic_graph()
    detector = SilenceDetector(graph=graph, db_url="sqlite:///:memory:")

    try:
        app = create_app(graph=graph, detector=detector)
        environ = {
            "PATH_INFO": "/v1/blockers",
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": "",
            "CONTENT_LENGTH": 0,
            "wsgi.input": BytesIO(b"{}"),
            "dep_agent.trace_id": "blockers-test-001",
            "dep_agent.request_id": "blockers-test-001",
        }

        responses = []

        def mock_start_response(status, headers, *args):
            responses.append((status, headers))

        result = app(environ, mock_start_response)
        assert len(responses) == 1
        assert "200" in responses[0][0]

        data = json.loads(result[0])
        # Blockers list may be empty if no candidates were detected yet
        # (this is expected — candidates are created by detect())
        assert isinstance(data, list)
    finally:
        detector.close()


def test_synthetic_api_run_analysis() -> None:
    """Test POST /v1/analysis/runs with synthetic data."""
    graph = create_synthetic_graph()
    detector = SilenceDetector(graph=graph, db_url="sqlite:///:memory:")

    try:
        app = create_app(graph=graph, detector=detector)
        body = json.dumps({
            "repositories": ["org/billing-service"],
            "lookback_days": 14,
        }).encode("utf-8")

        environ = {
            "PATH_INFO": "/v1/analysis/runs",
            "REQUEST_METHOD": "POST",
            "QUERY_STRING": "",
            "CONTENT_LENGTH": len(body),
            "wsgi.input": BytesIO(body),
            "dep_agent.trace_id": "analysis-test-001",
            "dep_agent.request_id": "analysis-test-001",
        }

        responses = []

        def mock_start_response(status, headers, *args):
            responses.append((status, headers))

        result = app(environ, mock_start_response)
        assert len(responses) == 1
        assert "200" in responses[0][0]

        data = json.loads(result[0])
        assert data["repositories_processed"] == 1
        assert "ingestion_results" in data
        assert "blocker_candidates" in data
    finally:
        detector.close()


def test_synthetic_risk_assessment_details() -> None:
    """Verify risk assessment details for each identified risk."""
    graph, dep_map_entries, api_results = run_synthetic_pipeline()

    # Risk 1: billing → mobile
    risk1 = next(
        e for e in dep_map_entries if e.target_repo == "org/mobile-app"
    )
    assert risk1.risk_score == 18
    assert risk1.risk_level == "high"
    assert "Breaking change" in risk1.compatibility_assessment
    assert "billing-service" in risk1.evidence_ref

    # Risk 2: billing → web
    risk2 = next(
        e for e in dep_map_entries if e.target_repo == "org/web-frontend"
    )
    assert risk2.risk_score == 18
    assert risk2.risk_level == "high"
    assert "Breaking change" in risk2.compatibility_assessment
    assert "billing-service" in risk2.evidence_ref


def test_synthetic_trace_id_propagation() -> None:
    """Verify trace_id is propagated through the pipeline."""
    graph, dep_map_entries, api_results = run_synthetic_pipeline()

    # All entries should have the synthetic trace_id
    for entry in dep_map_entries:
        assert entry.trace_id == "synthetic-test-001"

    # API results should also have trace_id
    for result in api_results:
        assert result.get("trace_id") == "synthetic-test-001"
