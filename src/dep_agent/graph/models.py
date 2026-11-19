"""SQLAlchemy 2.0 models for the artifact dependency graph store.

Supports SQLite (MVP) with migration path to PostgreSQL.
Tables: artifact_nodes, artifact_edges, silence_candidates, dependency_map.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class ArtifactNode(Base):
    """A repository artifact (contract, manifest, schema, etc.)."""

    __tablename__ = "artifact_nodes"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    repo: str = Column(String(255), nullable=False, index=True)
    artifact_path: str = Column(String(512), nullable=False)
    artifact_type: str = Column(String(50), nullable=False, index=True)
    # e.g. "openapi", "protobuf", "package_manifest"
    team: str = Column(String(100), nullable=False, index=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    outgoing_edges = relationship(
        "ArtifactEdge",
        foreign_keys="ArtifactEdge.source_node_id",
        back_populates="source",
        lazy="selectin",
    )
    incoming_edges = relationship(
        "ArtifactEdge",
        foreign_keys="ArtifactEdge.target_node_id",
        back_populates="target",
        lazy="selectin",
    )


class ArtifactEdge(Base):
    """Dependency edge between two artifact nodes."""

    __tablename__ = "artifact_edges"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    source_node_id: int = Column(
        Integer, ForeignKey("artifact_nodes.id"), nullable=False, index=True
    )
    target_node_id: int = Column(
        Integer, ForeignKey("artifact_nodes.id"), nullable=False, index=True
    )
    dependency_type: str = Column(String(50), nullable=False)
    # e.g. "openapi_contract", "protobuf_service", "package_dependency"
    created_at: datetime = Column(DateTime, default=datetime.utcnow)

    # Relationships
    source = relationship(
        "ArtifactNode", foreign_keys=[source_node_id], back_populates="outgoing_edges"
    )
    target = relationship(
        "ArtifactNode", foreign_keys=[target_node_id], back_populates="incoming_edges"
    )


class SilenceCandidate(Base):
    """A candidate implicit blocker detected by the silence window detector."""

    __tablename__ = "silence_candidates"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    source_repo: str = Column(String(255), nullable=False, index=True)
    target_repo: str = Column(String(255), nullable=False, index=True)
    artifact: str = Column(String(512), nullable=False)
    silence_days: int = Column(Integer, nullable=False)
    silence_window_days: int = Column(Integer, nullable=False)
    detected_at: datetime = Column(DateTime, default=datetime.utcnow)
    status: str = Column(String(20), default="pending", index=True)
    # "pending", "validated", "dismissed"


class DependencyMap(Base):
    """Structured DEPENDENCY_MAP output from LLM validation."""

    __tablename__ = "dependency_map"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id: int = Column(
        Integer, ForeignKey("silence_candidates.id"), nullable=True
    )
    source_repo: str = Column(String(255), nullable=False)
    target_repo: str = Column(String(255), nullable=False)
    artifact: str = Column(String(512), nullable=False)
    risk_score: float = Column(Float, nullable=False)
    # 0..25
    risk_level: str = Column(String(20), nullable=False)
    # "low", "medium", "high", "critical"
    compatibility_assessment: str = Column(Text, nullable=True)
    evidence_ref: str = Column(String(255), nullable=True)
    trace_id: str = Column(String(36), nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)


def create_graph_store(db_url: str | None = None) -> Base:
    """Create and configure the graph store engine.

    Args:
        db_url: SQLAlchemy database URL. Defaults to SQLite `dep_agent.db`.

    Returns:
        Base class with all models registered.
    """
    url = db_url or "sqlite:///dep_agent.db"
    engine = create_engine(url, echo=False)
    Base.metadata.create_all(engine)
    return Base
