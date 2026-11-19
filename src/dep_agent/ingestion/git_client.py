"""Read-only Git API client for GitHub and GitLab.

Provides access to commits, changed files/diffs, and PR/MR status.
Uses token-based authentication with read-only scope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CommitInfo:
    """Normalized commit metadata."""

    sha: str
    author: str
    timestamp: datetime
    message: str
    changed_files: list[str] = field(default_factory=list)
    pr_status: str | None = None  # "open", "merged", "closed"


@dataclass
class GitClientConfig:
    """Git API client configuration."""

    base_url: str = "https://api.github.com"
    token: str = ""
    org: str = ""
    timeout: float = 30.0
    max_retries: int = 3


class GitClient:
    """Read-only GitHub/GitLab API client.

    Supports:
    - Fetching commits with metadata
    - Fetching changed file lists and diffs per commit
    - Fetching PR/MR states
    - Rate limit handling with retry
    """

    def __init__(self, config: GitClientConfig | None = None) -> None:
        self._config = config or GitClientConfig()
        self._client = httpx.Client(
            base_url=self._config.base_url,
            timeout=self._config.timeout,
            headers=self._auth_headers(),
        )

    def _auth_headers(self) -> dict[str, str]:
        """Return auth headers based on token presence."""
        if self._config.token:
            return {"Authorization": f"token {self._config.token}"}
        return {}

    def fetch_commits(
        self, repo: str, lookback_days: int = 14
    ) -> list[CommitInfo]:
        """Fetch commits for a repository within the lookback window.

        Args:
            repo: Repository in `org/repo` format.
            lookback_days: Number of days to look back.

        Returns:
            List of normalized CommitInfo objects.
        """
        commits: list[CommitInfo] = []
        page = 1
        per_page = 100

        while True:
            params = {
                "per_page": per_page,
                "page": page,
                "since": self._since_date(lookback_days),
            }
            url = f"/repos/{repo}/commits"
            response = self._request("GET", url, params=params)

            if not response:
                break

            for item in response:
                commit = self._parse_commit(item, repo)
                commits.append(commit)

            # Check for pagination
            link_header = self._client.headers.get("Link", "")
            if 'rel="next"' not in link_header:
                break

            page += 1

            # Safety cap
            if page > 100:
                logger.warning("Reached pagination cap for %s", repo)
                break

        return commits

    def fetch_diff(self, repo: str, commit_sha: str) -> list[dict[str, Any]]:
        """Fetch changed files and diffs for a commit.

        Args:
            repo: Repository in `org/repo` format.
            commit_sha: Commit SHA.

        Returns:
            List of dicts with file change info.
        """
        url = f"/repos/{repo}/commits/{commit_sha}"
        response = self._request("GET", url)

        if not response:
            return []

        files = response.get("files", [])
        return [
            {
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "patch": f.get("patch", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
            }
            for f in files
        ]

    def fetch_pr_status(
        self, repo: str, commit_sha: str
    ) -> str | None:
        """Fetch PR/MR status for a given commit.

        Args:
            repo: Repository in `org/repo` format.
            commit_sha: Commit SHA.

        Returns:
            PR status: "open", "merged", "closed", or None.
        """
        url = f"/repos/{repo}/commits/{commit_sha}/pull_requests"
        response = self._request("GET", url)

        if not response:
            return None

        # GitHub API returns list of PRs
        for pr in response:
            state = pr.get("state", "")
            if state == "merged":
                return "merged"
            if state == "open":
                return "open"

        return None

    def fetch_repo_teams(self, repo: str) -> list[str]:
        """Fetch team members with read access to a repository.

        Args:
            repo: Repository in `org/repo` format.

        Returns:
            List of team/user names with access.
        """
        url = f"/repos/{repo}/teams"
        response = self._request("GET", url)

        if not response:
            return []

        return [t.get("slug", "") for t in response if t.get("slug")]

    def _request(
        self, method: str, path: str, params: dict | None = None
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """Execute HTTP request with retry logic.

        Args:
            method: HTTP method.
            path: API path.
            params: Query parameters.

        Returns:
            Parsed JSON response, or None on failure.
        """
        for attempt in range(self._config.max_retries):
            try:
                response = self._client.request(method, path, params=params)

                if response.status_code == 403:
                    # Check rate limit
                    remaining = int(
                        response.headers.get("X-RateLimit-Remaining", 0)
                    )
                    if remaining == 0:
                        reset = int(
                            response.headers.get("X-RateLimit-Reset", 0)
                        )
                        logger.warning(
                            "Rate limit hit, resetting at %s", reset
                        )
                        # Wait until reset
                        import time

                        time.sleep(max(reset - int(time.time()), 60))
                        continue

                if response.status_code == 404:
                    logger.warning("Not found: %s %s", method, path)
                    return None

                response.raise_for_status()
                return response.json()

            except httpx.HTTPError as exc:
                logger.warning(
                    "Request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self._config.max_retries,
                    exc,
                )
                if attempt == self._config.max_retries - 1:
                    return None
                import time

                time.sleep(2 ** attempt)

        return None

    @staticmethod
    def _since_date(lookback_days: int) -> str:
        """Calculate ISO date string for lookback window."""
        from datetime import timedelta

        since = datetime.utcnow() - timedelta(days=lookback_days)
        return since.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _parse_commit(item: dict[str, Any], repo: str) -> CommitInfo:
        """Parse a commit API response into CommitInfo."""
        author_data = item.get("author", {})
        author = author_data.get("login", "unknown")

        commit_data = item.get("commit", {})
        author_date = commit_data.get("author", {}).get("date", "")
        timestamp = (
            datetime.strptime(author_date, "%Y-%m-%dT%H:%M:%SZ")
            if author_date
            else datetime.utcnow()
        )

        return CommitInfo(
            sha=item.get("sha", ""),
            author=author,
            timestamp=timestamp,
            message=commit_data.get("message", ""),
            changed_files=[
                f.get("filename", "")
                for f in item.get("files", [])
            ],
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> GitClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
