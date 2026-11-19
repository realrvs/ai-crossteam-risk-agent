"""Tests for config loader."""

from dep_agent.config import Config


def test_config_default_loads() -> None:
    """Config should load without errors even if config file is missing."""
    config = Config(config_dir="nonexistent")
    assert config.raw == {}


def test_config_get_default() -> None:
    config = Config(config_dir="nonexistent")
    assert config.get("nonexistent_key", "default") == "default"


def test_config_section_accessors() -> None:
    config = Config(config_dir="nonexistent")
    assert config.git is not None
    assert config.llm is not None
    assert config.otel is not None
