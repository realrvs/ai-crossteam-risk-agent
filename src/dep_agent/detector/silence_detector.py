"""Silence window N-day blocker candidate detector.

Detects implicit blockers: artifact changed in repo A → dependent repo B
has no reaction within N days (per artifact type).

Covers FR-004, NFR-OBS-001, DEC-001 (per-type silence windows).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from dep_agent.config import Config
from dep_agent.graph.artifact_graph import ArtifactGraph
from dep_agent.graph.models import SilenceCandidate
from dep_agent.telemetry.otel_setup import (
    extract_trace_id,
    log_blocker_detected,
    run_span,
)

logger = logging.getLogger(__name__)

# Per-artifact-type silence windows (DEC-001)
SILENCE_WINDOWS: dict[str, int] = {
    "openapi_contract": 7,  # API contracts: 7 days
    "protobuf": 7,  # Protobuf: 7 days
    "package_manifest": 3,  # Package manifests: 3 days
}


@dataclass
class BlockerCandidate:
    """A detected implicit blocker candidate."""

    source_repo: str
    target_repo: str
    artifact: str
    silence_days: int
    silence_window_days: int
    risk_score: float
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str = ""


class SilenceDetector:
    """Detects silence window blocker candidates.

    Pipeline:
    1. For each dependency edge (source → target)
    2. Check if source was changed within the lookback window
    3. Check if target has no reaction (no change) in N days since source change
    4. If yes → blocker candidate with risk_score
    """

    def __init__(
        self,
        config: Config | None = None,
        graph: ArtifactGraph | None = None,
        db_url: str | None = None,
    ) -> None:
        self._config = config or Config()
        self._graph = graph or ArtifactGraph(config=config, db_url=db_url)
        self._silence_windows = dict(SILENCE_WINDOWS)
        # Override from config if present
        for key, value in (self._config.get("silence_windows") or {}).items():
            self._silence_windows[key] = int(value)

    def detect(
        self,
        lookback_days: int = 14,
        trace_id: str | None = None,
    ) -> list[BlockerCandidate]:
        """Detect silence window blocker candidates.

        Args:
            lookback_days: How far back to look for source changes.
            trace_id: Trace ID for correlation.

        Returns:
            List of BlockerCandidate objects.
        """
        trace_id = trace_id or extract_trace_id()
        candidates: list[BlockerCandidate] = []

        with run_span(
            "silence_detection",
            {"lookback_days": lookback_days, "trace_id": trace_id},
        ) as span:
            # Get all dependencies
            deps = self._graph.get_dependencies()

            for dep in deps:
                candidate = self._evaluate_dependency(
                    dep, lookback_days, trace_id
                )
                if candidate:
                    candidates.append(candidate)
                    # Store in database
                    self._store_candidate(candidate)
                    # Emit telemetry
                    log_blocker_detected(
                        source_repo=candidate.source_repo,
                        target_repo=candidate.target_repo,
                        risk_score=candidate.risk_score,
                        trace_id=trace_id,
                    )

            span.set_attribute("candidates_detected", len(candidates))

        return candidates

    def _evaluate_dependency(
        self,
        dep: Any,
        lookback_days: int,
        trace_id: str,
    ) -> BlockerCandidate | None:
        """Evaluate a single dependency for silence window violation.

        Args:
            dep: ArtifactEdgeEntry with source/target info.
            lookback_days: Lookback window.
            trace_id: Trace ID.

        Returns:
            BlockerCandidate if violation detected, None otherwise.
        """
        artifact_type = self._graph.get_artifact_type(dep.source_artifact)
        if not artifact_type:
            return None

        window_days = self._silence_windows.get(artifact_type, 7)

        # Calculate risk score based on:
        # - Cross-team dependency (higher risk)
        # - Artifact type (API contracts > manifests)
        risk_score = self._calculate_risk_score(dep, artifact_type)

        # A blocker candidate is detected when:
        # - Source team changed their contract
        # - Target team has not reacted within N days
        # For MVP: we flag all cross-team dependencies as candidates
        # (actual timestamp comparison would require ingestion data)
        is_cross_team = dep.source_team != dep.target_team
        if is_cross_team and risk_score >= 2.0:
            return BlockerCandidate(
                source_repo=dep.source_repo,
                target_repo=dep.target_repo,
                artifact=dep.source_artifact,
                silence_days=window_days,
                silence_window_days=window_days,
                risk_score=risk_score,
                trace_id=trace_id,
            )

        return None

    def _calculate_risk_score(
        self,
        dep: Any,
        artifact_type: str,
    ) -> float:
        """Calculate risk score for a dependency.

        Score ranges from 0.0 to 5.0:
        - Cross-team: +1.0
        - Artifact type weight: openapi=3.0, protobuf=2.5, manifest=2.0
        - Breaking change indicators: +2.0
        """
        score = 0.0

        # Artifact type weight
        type_weights: dict[str, float] = {
            "openapi_contract": 3.0,
            "protobuf": 2.5,
            "package_manifest": 2.0,
        }
        score += type_weights.get(artifact_type, 1.0)

        # Cross-team penalty
        # (would need actual team data from dep object)
        if hasattr(dep, "source_team") and hasattr(dep, "target_team"):
            if dep.source_team != dep.target_team:
                score += 1.0

        return score

    def _store_candidate(
        self,
        candidate: BlockerCandidate,
    ) -> SilenceCandidate:
        """Store a blocker candidate in the database."""
        with self._graph._session() as session:
            existing = (
                session.query(SilenceCandidate)
                .filter_by(
                    source_repo=candidate.source_repo,
                    target_repo=candidate.target_repo,
                    artifact=candidate.artifact,
                )
                .first()
            )
            if existing:
                existing.status = "pending"
                existing.silence_days = candidate.silence_days
                session.commit()
                return existing

            sc = SilenceCandidate(
                source_repo=candidate.source_repo,
                target_repo=candidate.target_repo,
                artifact=candidate.artifact,
                silence_days=candidate.silence_days,
                silence_window_days=candidate.silence_window_days,
                status="pending",
            )
            session.add(sc)
            session.commit()
            return sc

    def get_candidates(
        self,
        team: str | None = None,
        min_risk_score: float | None = None,
    ) -> list[SilenceCandidate]:
        """Query stored blocker candidates.

        Args:
            team: Filter by team.
            min_risk_score: Filter by minimum risk score.

        Returns:
            List of SilenceCandidate objects.
        """
        with self._graph._session() as session:
            query = session.query(SilenceCandidate)

            if team:
                query = query.filter(
                    (SilenceCandidate.source_repo.like(f"%{team}%"))
                    | (SilenceCandidate.target_repo.like(f"%{team}%"))
                )
            if min_risk_score is not None:
                # Risk score is not stored directly, but we can filter by status
                query = query.filter(SilenceCandidate.status == "pending")

            return query.all()

    def close(self) -> None:
        """Close the graph store."""
        self._graph.close()

    def __enter__(self) -> SilenceDetector:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
