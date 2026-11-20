"""Git ingestion package."""

from dep_agent.ingestion.git_client import CommitInfo, GitClient, GitClientConfig
from dep_agent.ingestion.service import IngestedCommit, IngestionResult, IngestionService

__all__ = ["GitClient", "GitClientConfig", "CommitInfo", "IngestionService", "IngestedCommit", "IngestionResult"]
