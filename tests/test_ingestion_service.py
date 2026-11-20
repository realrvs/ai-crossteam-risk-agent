"""Tests for IngestionService (TC-001)."""

from unittest.mock import MagicMock, patch

from dep_agent.ingestion.service import IngestedCommit, IngestionService


def test_ingestion_service_init() -> None:
    """IngestionService should initialize with config."""
    service = IngestionService()
    assert service._redactor is not None


def test_ingestion_service_context_manager() -> None:
    """IngestionService should work as context manager."""
    with IngestionService() as service:
        assert service is not None


@patch("dep_agent.ingestion.service.GitClient")
def test_ingest_calls_git_client(mock_git_client: MagicMock) -> None:
    """Ingest should call GitClient.fetch_commits."""
    mock_client_instance = MagicMock()
    mock_git_client.return_value = mock_client_instance
    mock_client_instance.fetch_commits.return_value = []

    service = IngestionService()
    result = service.ingest("org/test-repo", lookback_days=14)

    mock_client_instance.fetch_commits.assert_called_once_with("org/test-repo", 14)
    assert result.repo == "org/test-repo"
    assert result.commits_ingested == 0


@patch("dep_agent.ingestion.service.GitClient")
def test_ingest_with_commits(mock_git_client: MagicMock) -> None:
    """Ingest should process commits and record telemetry."""
    mock_client_instance = MagicMock()
    mock_git_client.return_value = mock_client_instance

    mock_commit = MagicMock()
    mock_commit.sha = "abc123"
    mock_commit.author = "test-user"
    mock_commit.timestamp = MagicMock()
    mock_commit.message = "test commit message"
    mock_commit.changed_files = ["openapi/api.yaml"]
    mock_commit.__iter__ = lambda self: iter([])

    mock_client_instance.fetch_commits.return_value = [mock_commit]
    mock_client_instance.fetch_diff.return_value = []
    mock_client_instance.fetch_pr_status.return_value = None

    service = IngestionService()
    result = service.ingest("org/test-repo", lookback_days=7)

    assert result.commits_ingested == 1
    assert result.total_files_changed == 0


def test_ingested_commit_creation() -> None:
    """IngestedCommit should be creatable."""
    commit = IngestedCommit(
        sha="abc123",
        author="test-user",
        timestamp=MagicMock(),
        message="test",
        changed_files=["file.py"],
        trace_id="test-trace",
    )
    assert commit.sha == "abc123"
    assert commit.trace_id == "test-trace"
