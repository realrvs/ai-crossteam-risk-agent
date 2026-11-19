"""Git ingestion service for dep_agent.

Normalizes commits, diffs, and PR/MR status from GitHub/GitLab API.
Uses SecretRedactor to sanitize secrets before storage.
Emits telemetry via OTel/Prometheus.

Covers FR-001, NFR-001.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dep_agent.config import Config
from dep_agent.ingestion.git_client import GitClient, GitClientConfig
from dep_agent.security.redactor import SecretRedactor
from dep_agent.telemetry.otel_setup import (
    extract_trace_id,
    record_commits_filtered,
    run_span,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestedCommit:
    """Normalized commit after ingestion."""

    sha: str
    author: str
    timestamp: datetime
    message: str
    changed_files: list[str] = field(default_factory=list)
    diffs: list[dict[str, Any]] = field(default_factory=list)
    pr_status: str | None = None
    trace_id: str = ""


@dataclass
class IngestionResult:
    """Result of an ingestion run."""

    repo: str
    commits_ingested: int = 0
    total_files_changed: int = 0
    trace_id: str = ""
    errors: list[str] = field(default_factory=list)


class IngestionService:
    """Orchestrates commit/diff/PR ingestion from Git repositories.

    Pipeline:
    1. Fetch commits from Git API
    2. Fetch diffs for each commit
    3. Fetch PR status for each commit
    4. Redact secrets
    5. Normalize and return
    """

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or Config()
        self._redactor = SecretRedactor(
            enabled=self._config.get("security.secret_redaction_enabled", True),
            strict=self._config.get("security.strict_mode", False),
        )
        self._client: GitClient | None = None

    def _get_client(self) -> GitClient:
        """Get or create Git client."""
        if self._client is None:
            git_cfg = self._config.git
            self._client = GitClient(
                GitClientConfig(
                    base_url=git_cfg.get("base_url", "https://api.github.com"),
                    token=git_cfg.get("github_token", ""),
                    org=git_cfg.get("org", ""),
                    timeout=git_cfg.get("timeout", 30.0),
                    max_retries=git_cfg.get("max_retries", 3),
                )
            )
        return self._client

    def ingest(
        self,
        repo: str,
        lookback_days: int = 14,
        trace_id: str | None = None,
    ) -> IngestionResult:
        """Ingest commits, diffs, and PR status for a repository.

        Args:
            repo: Repository in `org/repo` format.
            lookback_days: Number of days to look back.
            trace_id: Trace ID for correlation.

        Returns:
            IngestionResult with normalized data.
        """
        trace_id = trace_id or extract_trace_id()
        result = IngestionResult(repo=repo, trace_id=trace_id)

        with run_span(
            "ingestion",
            {"repo.source": repo, "trace_id": trace_id},
        ) as span:
            try:
                client = self._get_client()
                commits = client.fetch_commits(repo, lookback_days)

                for commit_data in commits:
                    ingested = self._process_commit(client, commit_data, trace_id)
                    result.commits_ingested += 1
                    result.total_files_changed += len(ingested.diffs)

                    # Record telemetry
                    outcome = "kept" if ingested.changed_files else "dropped"
                    record_commits_filtered(
                        repo=repo,
                        outcome=outcome,
                        trace_id=trace_id,
                        count=len(ingested.changed_files),
                    )

                span.set_attribute("commits_ingested", result.commits_ingested)
                span.set_attribute("total_files_changed", result.total_files_changed)

            except Exception as exc:
                error_msg = f"Ingestion failed for {repo}: {exc}"
                logger.error(error_msg)
                result.errors.append(error_msg)
                span.record_exception(exc)
                span.set_status("error")

        return result

    def _process_commit(
        self,
        client: GitClient,
        commit_data: Any,
        trace_id: str,
    ) -> IngestedCommit:
        """Process a single commit: fetch diffs and PR status, redact secrets."""
        sha = commit_data.sha

        # Fetch diffs
        diffs = client.fetch_diff(
            commit_data.changed_files[0].split("/")[0] if commit_data.changed_files else "unknown",
            sha,
        ) if hasattr(commit_data, 'changed_files') and commit_data.changed_files else []

        # Fetch PR status
        pr_status = client.fetch_pr_status(
            commit_data.changed_files[0].split("/")[0] if commit_data.changed_files else "unknown",
            sha,
        ) if hasattr(commit_data, 'changed_files') and commit_data.changed_files else None

        # Redact secrets in message and diffs
        message = self._redactor.redact(commit_data.message, component="ingestion", trace_id=trace_id)
        diffs = self._redactor.redact_list(
            [str(d) for d in diffs],
            component="ingestion",
            trace_id=trace_id,
        )

        return IngestedCommit(
            sha=sha,
            author=commit_data.author,
            timestamp=commit_data.timestamp,
            message=message,
            changed_files=list(commit_data.changed_files) if hasattr(commit_data, 'changed_files') else [],
            diffs=diffs,
            pr_status=pr_status,
            trace_id=trace_id,
        )

    def close(self) -> None:
        """Close the Git client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> IngestionService:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
