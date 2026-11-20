"""Cross-repository artifact dependency graph and team mapping.

Builds a directed graph of artifact dependencies between repositories,
maps artifacts to teams via CODEOWNERS or YAML registry.

Covers FR-003, DEC-002 (CODEOWNERS + YAML fallback), DEC-004 (SQLite/SQLAlchemy).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dep_agent.config import Config
from dep_agent.graph.models import (
    ArtifactEdge,
    ArtifactNode,
    Base,
    create_graph_store,
)
from sqlalchemy.orm import aliased, joinedload

logger = logging.getLogger(__name__)

# CODEOWNERS pattern: paths followed by owners
# e.g. "openapi/ @team-billing" or "*.proto @team-protobuf"
CODEOWNERS_LINE_RE = re.compile(r"^(\S+)\s+(.+)$", re.MULTILINE)
CODEOWNERS_OWNER_RE = re.compile(r"@[A-Za-z0-9_-]+")


@dataclass
class ArtifactEdgeEntry:
    """A single edge in the artifact dependency graph."""

    source_repo: str
    source_artifact: str
    source_team: str
    target_repo: str
    target_team: str
    dependency_type: str


class ArtifactGraph:
    """Cross-repository artifact dependency graph.

    Stores artifact nodes (repo + artifact path + team) and edges
    (source → target dependencies).
    """

    def __init__(
        self,
        config: Config | None = None,
        db_url: str | None = None,
    ) -> None:
        self._config = config or Config()
        self._db_url = db_url or self._config.graph_store.get(
            "url", "sqlite:///dep_agent.db"
        )
        self._engine = create_engine(self._db_url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        Base.metadata.create_all(self._engine)

    def _session(self) -> Session:
        """Create a new database session."""
        return self._session_factory()

    def add_artifact(
        self,
        repo: str,
        artifact_path: str,
        artifact_type: str,
        team: str,
    ) -> ArtifactNode:
        """Add or update an artifact node."""
        with self._session() as session:
            # Check if node exists
            existing = (
                session.query(ArtifactNode)
                .filter_by(repo=repo, artifact_path=artifact_path)
                .first()
            )
            if existing:
                existing.artifact_type = artifact_type
                existing.team = team
                session.commit()
                return existing

            node = ArtifactNode(
                repo=repo,
                artifact_path=artifact_path,
                artifact_type=artifact_type,
                team=team,
            )
            session.add(node)
            session.commit()
            return node

    def add_dependency(
        self,
        source_node_id: int,
        target_node_id: int,
        dependency_type: str,
    ) -> ArtifactEdge:
        """Add a dependency edge between two artifact nodes."""
        with self._session() as session:
            edge = ArtifactEdge(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                dependency_type=dependency_type,
            )
            session.add(edge)
            session.commit()
            return edge

    def get_dependencies(
        self,
        team: str | None = None,
        repo: str | None = None,
    ) -> list[ArtifactEdgeEntry]:
        """Query dependency edges.

        Args:
            team: Filter by team name.
            repo: Filter by repository name.

        Returns:
            List of ArtifactEdgeEntry with full source/target info.
        """
        with self._session() as session:
            SourceNode = aliased(ArtifactNode)
            TargetNode = aliased(ArtifactNode)

            query = (
                session.query(ArtifactEdge, SourceNode, TargetNode)
                .join(SourceNode, ArtifactEdge.source_node_id == SourceNode.id)
                .outerjoin(TargetNode, ArtifactEdge.target_node_id == TargetNode.id)
            )

            if team:
                query = query.filter(
                    (SourceNode.team == team) | (TargetNode.team == team)
                )
            if repo:
                query = query.filter(
                    (SourceNode.repo == repo) | (TargetNode.repo == repo)
                )

            results: list[ArtifactEdgeEntry] = []
            for edge, source, target in query.all():
                results.append(ArtifactEdgeEntry(
                    source_repo=source.repo,
                    source_artifact=source.artifact_path,
                    source_team=source.team,
                    target_repo=target.repo if target else "",
                    target_team=target.team if target else "",
                    dependency_type=edge.dependency_type,
                ))

            return results

    def get_artifact_type(self, filepath: str) -> str | None:
        """Detect artifact type from file path."""
        contract_patterns: list[tuple[str, str]] = [
            (r"^openapi/", "openapi_contract"),
            (r"^api/", "openapi_contract"),
            (r"\.openapi\.ya?ml$", "openapi_contract"),
            (r"\.openapi\.json$", "openapi_contract"),
            (r"\.proto$", "protobuf"),
            (r"^package\.json$", "package_manifest"),
            (r"^go\.mod$", "package_manifest"),
            (r"^requirements\.txt$", "package_manifest"),
            (r"^Cargo\.toml$", "package_manifest"),
        ]
        for pattern, artifact_type in contract_patterns:
            if re.search(pattern, filepath):
                return artifact_type
        return None

    def close(self) -> None:
        """Close the database engine."""
        self._engine.dispose()

    def __enter__(self) -> ArtifactGraph:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class TeamMapper:
    """Maps repositories/artifacts to teams.

    Priority:
    1. CODEOWNERS from repo root
    2. YAML registry (team-mapping.yaml)
    """

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or Config()
        self._codeowners_cache: dict[str, dict[str, str]] = {}
        # { repo → { path_pattern → team } }

    def map_repo_to_team(self, repo: str) -> str:
        """Map a repository to its owning team.

        1. Try CODEOWNERS from config directory
        2. Fallback to YAML registry
        """
        # Try CODEOWNERS first
        codeowners_path = Path("config") / f"{repo.replace('/', '_')}_CODEOWNERS"
        if codeowners_path.exists():
            return self._parse_codeowners(codeowners_path, repo)

        # Try YAML registry
        registry_path = Path("config") / "team-mapping.yaml"
        if registry_path.exists():
            with open(registry_path, "r", encoding="utf-8") as fh:
                registry = yaml.safe_load(fh) or {}
            team = registry.get(repo, {}).get("team", "unknown")
            if team:
                return team

        return "unknown"

    def map_artifact_to_team(
        self, repo: str, artifact_path: str
    ) -> str:
        """Map an artifact path to its owning team.

        1. Try CODEOWNERS path matching
        2. Fallback to repo-level mapping
        """
        # Try CODEOWNERS
        codeowners_path = Path("config") / f"{repo.replace('/', '_')}_CODEOWNERS"
        if codeowners_path.exists():
            patterns = self._parse_codeowners(codeowners_path, repo)
            for pattern, team in patterns.items():
                if self._path_matches(artifact_path, pattern):
                    return team

        # Fallback to repo-level
        return self.map_repo_to_team(repo)

    def _parse_codeowners(
        self, path: Path, repo: str
    ) -> dict[str, str]:
        """Parse CODEOWNERS file into { path_pattern → team }.

        Returns:
            Dict mapping glob patterns to team names.
        """
        if repo in self._codeowners_cache:
            return self._codeowners_cache[repo]

        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()

        patterns: dict[str, str] = {}
        for line in CODEOWNERS_LINE_RE.finditer(content):
            file_pattern = line.group(1)
            owners_str = line.group(2)
            owners = CODEOWNERS_OWNER_RE.findall(owners_str)
            if owners:
                # Use first owner as team
                team = owners[0].lstrip("@")
                patterns[file_pattern] = team

        self._codeowners_cache[repo] = patterns
        return patterns

    @staticmethod
    def _path_matches(filepath: str, pattern: str) -> bool:
        """Check if a file path matches a CODEOWNERS pattern.

        Supports:
        - Exact match: "openapi/api.yaml"
        - Glob: "openapi/**"
        - Extension: "*.proto"
        """
        # Exact match
        if filepath == pattern:
            return True

        # Glob pattern with **
        if "**" in pattern:
            glob_pattern = pattern.replace("**/", "").replace("**", "")
            return filepath.startswith(glob_pattern) or filepath.endswith(glob_pattern)

        # Extension pattern
        if pattern.startswith("*"):
            extension = pattern.lstrip("*")
            return filepath.endswith(extension)

        # Prefix match (directory)
        if pattern.endswith("/"):
            return filepath.startswith(pattern)

        return False
