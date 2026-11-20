"""Configuration loader for dep_agent.

Loads YAML config from `config/` directory with support for environment-specific overrides.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = "config"
DEFAULT_CONFIG_FILE = "default.yaml"


class Config:
    """Central configuration loader."""

    def __init__(self, config_dir: str | None = None) -> None:
        self._config_dir = Path(config_dir) if config_dir else Path(DEFAULT_CONFIG_DIR)
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        config_file = self._config_dir / DEFAULT_CONFIG_FILE
        if config_file.exists():
            with open(config_file, encoding="utf-8") as fh:
                self._data = yaml.safe_load(fh) or {}
        else:
            self._data = {}
        # Override with environment variables
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        """Override config values with environment variables."""
        env_mappings: dict[str, str] = {
            "git.github_token": "GIT_GITHUB_TOKEN",
            "git.gitlab_token": "GIT_GITLAB_TOKEN",
            "llm.oauth_token": "LLM_OAUTH_TOKEN",
            "llm.folder_id": "LLM_FOLDER_ID",
        }
        for config_key, env_var in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(self._data, config_key, value)

    @staticmethod
    def _set_nested(d: dict[str, Any], key_path: str, value: Any) -> None:
        keys = key_path.split(".")
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a nested config value by dot-separated key."""
        keys = key.split(".")
        current = self._data
        for k in keys:
            if isinstance(current, dict):
                current = current.get(k)
            else:
                return default
            if current is None:
                return default
        return current

    @property
    def raw(self) -> dict[str, Any]:
        """Return raw config dict."""
        return self._data

    @property
    def git(self) -> dict[str, Any]:
        """Git configuration section."""
        return self.get("git", {})

    @property
    def llm(self) -> dict[str, Any]:
        """LLM configuration section."""
        return self.get("llm", {})

    @property
    def otel(self) -> dict[str, Any]:
        """OpenTelemetry configuration section."""
        return self.get("otel", {})

    @property
    def prometheus(self) -> dict[str, Any]:
        """Prometheus configuration section."""
        return self.get("prometheus", {})

    @property
    def graph_store(self) -> dict[str, Any]:
        """Graph store configuration section."""
        return self.get("graph_store", {})
