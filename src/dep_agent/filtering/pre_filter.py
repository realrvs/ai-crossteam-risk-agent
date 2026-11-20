"""Deterministic noise pre-filter for dep_agent.

Filters out noise commits without LLM calls and assigns pre-scores
based on touched artifact paths and optional text markers.

Covers FR-002, NFR-SEC-004, NFR-OBS-001.
DEC-003: artifact types for v1 (OpenAPI, Protobuf, package manifests).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from dep_agent.config import Config
from dep_agent.telemetry.otel_setup import (
    extract_trace_id,
    record_commits_filtered,
    run_span,
)

logger = logging.getLogger(__name__)

# Noise commit message patterns (case-insensitive)
NOISE_PATTERNS: list[tuple[str, str]] = [
    (r"^\s*merge\b", "merge"),
    (r"^\s*chore(\(.*?\))?:", "chore"),
    (r"^\s*docs(\(.*?\))?:", "docs"),
    (r"^\s*lint(\(.*?\))?:", "lint"),
    (r"^\s*typo(\(.*?\))?:", "typo"),
    (r"^\s*style(\(.*?\))?:", "style"),
    (r"^\s*ci(\(.*?\))?:", "ci"),
    (r"^\s*refactor(\(.*?\))?:", "refactor"),
    (r"\(auto-generated\)", "auto-generated"),
    (r"^\s*update\s+README", "docs"),
]

# Contract artifact path patterns (DEC-003)
CONTRACT_PATTERNS: list[tuple[str, str]] = [
    (r"^openapi/", "openapi_contract"),
    (r"^api/", "openapi_contract"),
    (r"\.openapi\.ya?ml$", "openapi_contract"),
    (r"\.openapi\.json$", "openapi_contract"),
    (r"\.proto$", "protobuf"),
    (r"^package\.json$", "package_manifest"),
    (r"^go\.mod$", "package_manifest"),
    (r"^requirements\.txt$", "package_manifest"),
    (r"^Cargo\.toml$", "package_manifest"),
    (r"^pyproject\.toml$", "package_manifest"),
]


@dataclass
class FilterResult:
    """Result of filtering a single commit."""

    sha: str
    author: str
    message: str
    changed_files: list[str]
    kept: bool = False
    reason: str = ""
    artifact_type: str = ""
    pre_score: float = 0.0


@dataclass
class FilterBatchResult:
    """Result of filtering a batch of commits."""

    total: int = 0
    kept: int = 0
    dropped: int = 0
    results: list[FilterResult] = field(default_factory=list)


class PreFilter:
    """Deterministic noise pre-filter.

    Pipeline:
    1. Check commit message against noise patterns
    2. Check changed files against contract patterns
    3. Assign pre-score based on artifact type and message markers
    4. Keep or drop based on contract match
    """

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or Config()
        self._compiled_noise: list[tuple[re.Pattern[str], str]] = [
            (re.compile(p, re.IGNORECASE), label) for p, label in NOISE_PATTERNS
        ]
        self._compiled_contract: list[tuple[re.Pattern[str], str]] = [
            (re.compile(p), label) for p, label in CONTRACT_PATTERNS
        ]
        # Configurable exception list (paths that are always kept)
        self._exceptions: list[str] = [
            path.strip()
            for path in self._config.get("filter_exceptions", []) or []
        ]

    def evaluate(
        self,
        commits: list[dict[str, Any]],
        trace_id: str | None = None,
    ) -> FilterBatchResult:
        """Evaluate a batch of commits and filter noise.

        Args:
            commits: List of commit dicts with keys: sha, author, message, changed_files.
            trace_id: Trace ID for correlation.

        Returns:
            FilterBatchResult with filtered results.
        """
        trace_id = trace_id or extract_trace_id()
        result = FilterBatchResult()

        with run_span("pre_filter", {"trace_id": trace_id}) as span:
            for commit in commits:
                filtered = self._evaluate_single(commit, trace_id)
                result.total += 1
                result.results.append(filtered)

                if filtered.kept:
                    result.kept += 1
                    record_commits_filtered(
                        repo=commit.get("repo", "unknown"),
                        outcome="kept",
                        trace_id=trace_id,
                    )
                else:
                    result.dropped += 1
                    record_commits_filtered(
                        repo=commit.get("repo", "unknown"),
                        outcome="dropped",
                        trace_id=trace_id,
                    )

            span.set_attribute("total", result.total)
            span.set_attribute("kept", result.kept)
            span.set_attribute("dropped", result.dropped)

        return result

    def _evaluate_single(
        self, commit: dict[str, Any], trace_id: str
    ) -> FilterResult:
        """Evaluate a single commit."""
        sha = commit.get("sha", "unknown")
        author = commit.get("author", "unknown")
        message = commit.get("message", "")
        changed_files = commit.get("changed_files", [])

        # Step 1: Check noise patterns
        noise_type = self._check_noise(message)
        if noise_type:
            return FilterResult(
                sha=sha,
                author=author,
                message=message,
                changed_files=changed_files,
                kept=False,
                reason=f"noise:{noise_type}",
            )

        # Step 2: Check contract patterns
        artifact_type, score = self._check_contracts(changed_files)
        if artifact_type:
            return FilterResult(
                sha=sha,
                author=author,
                message=message,
                changed_files=changed_files,
                kept=True,
                reason=f"contract:{artifact_type}",
                artifact_type=artifact_type,
                pre_score=score,
            )

        # Step 3: Check exceptions
        for exc_path in self._exceptions:
            if any(exc_path in f for f in changed_files):
                return FilterResult(
                    sha=sha,
                    author=author,
                    message=message,
                    changed_files=changed_files,
                    kept=True,
                    reason="exception",
                    pre_score=1.0,
                )

        # No match — drop
        return FilterResult(
            sha=sha,
            author=author,
            message=message,
            changed_files=changed_files,
            kept=False,
            reason="no_contract_match",
        )

    def _check_noise(self, message: str) -> str | None:
        """Check if commit message matches noise patterns."""
        for pattern, label in self._compiled_noise:
            if pattern.search(message):
                return label
        return None

    def _check_contracts(
        self, changed_files: list[str]
    ) -> tuple[str, float]:
        """Check if any changed file matches contract patterns.

        Returns:
            Tuple of (artifact_type, pre_score).
        """
        max_score = 0.0
        best_type = ""

        for filepath in changed_files:
            for pattern, artifact_type in self._compiled_contract:
                if pattern.search(filepath):
                    score = self._calculate_score(filepath, artifact_type)
                    if score > max_score:
                        max_score = score
                        best_type = artifact_type

        return best_type, max_score

    def _calculate_score(self, filepath: str, artifact_type: str) -> float:
        """Calculate pre-score for an artifact.

        Higher score = higher likelihood of being a real contract change.
        """
        score = 1.0

        # OpenAPI contracts get highest priority
        if artifact_type == "openapi_contract":
            score = 3.0
            # Breaking change markers increase score
            if any(marker in filepath.lower() for marker in ["breaking", "migration", "v2", "v3"]):
                score = 5.0
        elif artifact_type == "protobuf":
            score = 2.5
        elif artifact_type == "package_manifest":
            score = 2.0

        return score

    def is_contract_path(self, filepath: str) -> bool:
        """Check if a file path is a known contract artifact."""
        return any(pattern.search(filepath) for pattern, _ in self._compiled_contract)

    def get_artifact_type(self, filepath: str) -> str | None:
        """Get the artifact type for a file path, or None."""
        for pattern, artifact_type in self._compiled_contract:
            if pattern.search(filepath):
                return artifact_type
        return None
