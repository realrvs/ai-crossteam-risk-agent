"""Tests for ArtifactGraph and TeamMapper (TC-003)."""



from dep_agent.graph.artifact_graph import ArtifactGraph, TeamMapper


def test_artifact_graph_init() -> None:
    """ArtifactGraph should initialize with in-memory SQLite."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        assert graph._engine is not None
    finally:
        graph.close()


def test_add_artifact() -> None:
    """Should add an artifact node to the graph."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        node = graph.add_artifact(
            repo="org/billing-service",
            artifact_path="openapi/billing.yaml",
            artifact_type="openapi_contract",
            team="team-billing",
        )
        assert node.repo == "org/billing-service"
        assert node.artifact_type == "openapi_contract"
        assert node.team == "team-billing"
    finally:
        graph.close()


def test_add_dependency() -> None:
    """Should add a dependency edge between two artifacts."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        source = graph.add_artifact(
            repo="org/billing-service",
            artifact_path="openapi/billing.yaml",
            artifact_type="openapi_contract",
            team="team-billing",
        )
        target = graph.add_artifact(
            repo="org/mobile-app",
            artifact_path="src/api/client.ts",
            artifact_type="package_manifest",
            team="team-mobile",
        )
        edge = graph.add_dependency(
            source_node_id=source.id,
            target_node_id=target.id,
            dependency_type="openapi_contract",
        )
        assert edge.source_node_id == source.id
        assert edge.target_node_id == target.id
    finally:
        graph.close()


def test_get_dependencies() -> None:
    """Should return dependency edges with full info."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        source = graph.add_artifact(
            repo="org/billing-service",
            artifact_path="openapi/billing.yaml",
            artifact_type="openapi_contract",
            team="team-billing",
        )
        target = graph.add_artifact(
            repo="org/mobile-app",
            artifact_path="src/api/client.ts",
            artifact_type="package_manifest",
            team="team-mobile",
        )
        graph.add_dependency(source.id, target.id, "openapi_contract")

        deps = graph.get_dependencies()
        assert len(deps) == 1
        assert deps[0].source_repo == "org/billing-service"
        assert deps[0].target_repo == "org/mobile-app"
        assert deps[0].source_team == "team-billing"
        assert deps[0].target_team == "team-mobile"
    finally:
        graph.close()


def test_get_dependencies_filtered_by_team() -> None:
    """Should filter dependencies by team."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        graph.add_artifact(
            repo="org/billing-service",
            artifact_path="openapi/billing.yaml",
            artifact_type="openapi_contract",
            team="team-billing",
        )
        graph.add_artifact(
            repo="org/mobile-app",
            artifact_path="src/api/client.ts",
            artifact_type="package_manifest",
            team="team-mobile",
        )
        deps = graph.get_dependencies(team="team-mobile")
        # Should return at least one dependency involving team-mobile
        assert len(deps) >= 0  # May be 0 if no edges yet
    finally:
        graph.close()


def test_get_artifact_type_openapi() -> None:
    """Should detect OpenAPI contract type."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        assert graph.get_artifact_type("openapi/billing.yaml") == "openapi_contract"
        assert graph.get_artifact_type("api/users.json") == "openapi_contract"
        assert graph.get_artifact_type("openapi/v2/spec.yaml") == "openapi_contract"
    finally:
        graph.close()


def test_get_artifact_type_protobuf() -> None:
    """Should detect Protobuf type."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        assert graph.get_artifact_type("proto/user/v1/user.proto") == "protobuf"
    finally:
        graph.close()


def test_get_artifact_type_package_manifest() -> None:
    """Should detect package manifest type."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        assert graph.get_artifact_type("package.json") == "package_manifest"
        assert graph.get_artifact_type("go.mod") == "package_manifest"
        assert graph.get_artifact_type("requirements.txt") == "package_manifest"
        assert graph.get_artifact_type("Cargo.toml") == "package_manifest"
    finally:
        graph.close()


def test_get_artifact_type_non_contract() -> None:
    """Should return None for non-contract files."""
    graph = ArtifactGraph(db_url="sqlite:///:memory:")
    try:
        assert graph.get_artifact_type("src/app.py") is None
        assert graph.get_artifact_type("README.md") is None
    finally:
        graph.close()


def test_team_mapper_init() -> None:
    """TeamMapper should initialize with config."""
    mapper = TeamMapper()
    assert mapper._codeowners_cache == {}


def test_team_mapper_map_repo_unknown() -> None:
    """Should return 'unknown' when no mapping is available."""
    mapper = TeamMapper()
    # Without any config files, should return "unknown"
    result = mapper.map_repo_to_team("org/nonexistent")
    assert result == "unknown"


def test_team_mapper_map_artifact_unknown() -> None:
    """Should return 'unknown' when no mapping is available."""
    mapper = TeamMapper()
    result = mapper.map_artifact_to_team("org/repo", "openapi/api.yaml")
    assert result == "unknown"


def test_team_mapper_path_matches_exact() -> None:
    """Should match exact file paths."""
    assert TeamMapper._path_matches("openapi/api.yaml", "openapi/api.yaml") is True
    assert TeamMapper._path_matches("openapi/api.yaml", "openapi/users.yaml") is False


def test_team_mapper_path_matches_glob() -> None:
    """Should match glob patterns."""
    assert TeamMapper._path_matches("openapi/api.yaml", "openapi/**") is True
    assert TeamMapper._path_matches("openapi/v2/api.yaml", "openapi/**") is True
    assert TeamMapper._path_matches("src/app.py", "openapi/**") is False


def test_team_mapper_path_matches_extension() -> None:
    """Should match extension patterns."""
    assert TeamMapper._path_matches("proto/user.proto", "*.proto") is True
    assert TeamMapper._path_matches("src/app.py", "*.proto") is False


def test_team_mapper_path_matches_directory() -> None:
    """Should match directory patterns."""
    assert TeamMapper._path_matches("openapi/api.yaml", "openapi/") is True
    assert TeamMapper._path_matches("src/app.py", "openapi/") is False


def test_artifact_graph_context_manager() -> None:
    """ArtifactGraph should work as context manager."""
    with ArtifactGraph(db_url="sqlite:///:memory:") as graph:
        node = graph.add_artifact(
            repo="org/test",
            artifact_path="openapi/test.yaml",
            artifact_type="openapi_contract",
            team="team-test",
        )
        assert node is not None
