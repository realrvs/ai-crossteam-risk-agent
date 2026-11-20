"""Tests for graph models."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dep_agent.graph.models import (
    ArtifactEdge,
    ArtifactNode,
    Base,
)


def test_create_in_memory_graph_store() -> None:
    """Graph store should create tables in memory."""
    from sqlalchemy import inspect

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = inspect(engine).get_table_names()
    assert sorted(tables) == sorted([
        "artifact_nodes",
        "artifact_edges",
        "silence_candidates",
        "dependency_map",
    ])


def test_artifact_node_creation() -> None:
    """ArtifactNode should be creatable and queryable."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        node = ArtifactNode(
            repo="org/service",
            artifact_path="openapi/api.yaml",
            artifact_type="openapi",
            team="team-api",
        )
        session.add(node)
        session.commit()
        assert node.id is not None
        assert node.repo == "org/service"


def test_artifact_edge_creation() -> None:
    """ArtifactEdge should link two ArtifactNodes."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = ArtifactNode(
            repo="org/service-a",
            artifact_path="openapi/a.yaml",
            artifact_type="openapi",
            team="team-a",
        )
        target = ArtifactNode(
            repo="org/service-b",
            artifact_path="openapi/b.yaml",
            artifact_type="openapi",
            team="team-b",
        )
        session.add_all([source, target])
        session.flush()
        edge = ArtifactEdge(
            source_node_id=source.id,
            target_node_id=target.id,
            dependency_type="openapi_contract",
        )
        session.add(edge)
        session.commit()
        assert edge.id is not None
        assert edge.source.repo == "org/service-a"
        assert edge.target.repo == "org/service-b"
