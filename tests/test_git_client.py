"""Tests for GitClient."""

from dep_agent.ingestion.git_client import GitClient, GitClientConfig, CommitInfo
from datetime import datetime


def test_git_client_config_defaults() -> None:
    config = GitClientConfig()
    assert config.base_url == "https://api.github.com"
    assert config.token == ""
    assert config.timeout == 30.0


def test_git_client_context_manager() -> None:
    config = GitClientConfig(token="test-token")
    client = GitClient(config)
    assert "Authorization" in client._auth_headers()
    client.close()


def test_commit_info_creation() -> None:
    commit = CommitInfo(
        sha="abc123",
        author="test-user",
        timestamp=datetime.utcnow(),
        message="test commit",
        changed_files=["file.py"],
    )
    assert commit.sha == "abc123"
    assert commit.changed_files == ["file.py"]
