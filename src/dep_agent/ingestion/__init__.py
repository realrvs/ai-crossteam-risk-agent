"""Git ingestion package."""

from dep_agent.ingestion.git_client import GitClient, GitClientConfig, CommitInfo
from dep_agent.ingestion.service import IngestionService, IngestedCommit, IngestionResult

__all__ = ["GitClient", "GitClientConfig", "CommitInfo", "IngestionService", "IngestedCommit", "IngestionResult"]
