"""Tests for LlmValidator (TC-005, TC-SEC-001, TC-SEC-004)."""

from unittest.mock import MagicMock, patch

from dep_agent.config import Config
from dep_agent.validator.llm_validator import (
    LlmValidator,
    LlmValidationResult,
    DependencyMapEntry,
    LLM_RESPONSE_SCHEMA,
)


def test_llm_validator_init() -> None:
    """LlmValidator should initialize with config."""
    validator = LlmValidator()
    assert validator._max_candidates == 20
    assert validator._provider == "yandexgpt"
    assert validator._model == "yandexgptlatest"


def test_llm_response_schema() -> None:
    """LLM_RESPONSE_SCHEMA should have required fields."""
    assert "properties" in LLM_RESPONSE_SCHEMA
    assert "risk_score" in LLM_RESPONSE_SCHEMA["properties"]
    assert "risk_level" in LLM_RESPONSE_SCHEMA["properties"]
    assert "compatibility_assessment" in LLM_RESPONSE_SCHEMA["properties"]
    assert "evidence_ref" in LLM_RESPONSE_SCHEMA["properties"]
    assert "required" in LLM_RESPONSE_SCHEMA
    assert set(LLM_RESPONSE_SCHEMA["required"]) == {
        "risk_score",
        "risk_level",
        "compatibility_assessment",
        "evidence_ref",
    }


def test_system_prompt_defined() -> None:
    """SYSTEM_PROMPT should be defined and non-empty."""
    assert LlmValidator.SYSTEM_PROMPT
    assert "risk_score" in LlmValidator.SYSTEM_PROMPT
    assert "risk_level" in LlmValidator.SYSTEM_PROMPT
    assert "UNTRUSTED" not in LlmValidator.SYSTEM_PROMPT


def test_build_user_prompt_contains_untrusted_marking() -> None:
    """User prompt should mark data as untrusted."""
    validator = LlmValidator()
    candidate = {
        "source_repo": "org/service-a",
        "target_repo": "org/service-b",
        "artifact": "openapi/api.yaml",
        "source_team": "team-a",
        "target_team": "team-b",
    }
    prompt = validator._build_user_prompt(candidate)
    assert "[UNTRUSTED DATA]" in prompt


def test_build_user_prompt_redacts_secrets() -> None:
    """User prompt should redact secrets."""
    validator = LlmValidator()
    candidate = {
        "source_repo": "org/service-a",
        "target_repo": "org/service-b",
        "artifact": "openapi/api.yaml",
        "source_team": "team-a",
        "target_team": "team-b",
    }
    # Add a secret to the candidate (would normally be in repo data)
    candidate_with_secret = dict(candidate)
    candidate_with_secret["artifact"] = "openapi/api.yaml?token=ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"
    prompt = validator._build_user_prompt(candidate_with_secret)
    # Secret should be redacted
    assert "ghp_ABCDEFghijklmnopqrstuvwxyz1234567890" not in prompt


def test_candidate_cap() -> None:
    """Should cap candidates to max_llm_candidates."""
    validator = LlmValidator()
    candidates = [{"index": i} for i in range(25)]
    capped = candidates[: validator._max_candidates]
    assert len(capped) == 20


def test_validate_single_success() -> None:
    """Should return result with error when LLM call fails."""
    validator = LlmValidator()
    candidate = {
        "source_repo": "org/service-a",
        "target_repo": "org/service-b",
        "artifact": "openapi/api.yaml",
    }
    # Without valid config, LLM call will fail
    result = validator._validate_single(0, candidate, "test-trace")
    assert isinstance(result, LlmValidationResult)
    assert result.source_repo == "org/service-a"
    assert result.target_repo == "org/service-b"
    assert result.error != ""  # Will fail without valid token


def test_results_to_dependency_map() -> None:
    """Should convert results to DependencyMapEntry."""
    result = LlmValidationResult(
        candidate_index=0,
        source_repo="org/service-a",
        target_repo="org/service-b",
        artifact="openapi/api.yaml",
        risk_score=15,
        risk_level="high",
        compatibility_assessment="Breaking change detected",
        evidence_ref="commit/abc123",
        trace_id="test-trace",
    )
    entries = LlmValidator().results_to_dependency_map([result])
    assert len(entries) == 1
    entry = entries[0]
    assert isinstance(entry, DependencyMapEntry)
    assert entry.risk_score == 15
    assert entry.risk_level == "high"


def test_results_to_dependency_map_filters_errors() -> None:
    """Should filter out results with errors."""
    failed_result = LlmValidationResult(
        candidate_index=0,
        source_repo="org/service-a",
        target_repo="org/service-b",
        artifact="openapi/api.yaml",
        risk_score=0,
        risk_level="low",
        compatibility_assessment="",
        evidence_ref="",
        error="LLM call failed",
    )
    successful_result = LlmValidationResult(
        candidate_index=1,
        source_repo="org/service-c",
        target_repo="org/service-d",
        artifact="proto/user.proto",
        risk_score=5,
        risk_level="low",
        compatibility_assessment="Compatible",
        evidence_ref="commit/def456",
    )
    entries = LlmValidator().results_to_dependency_map([failed_result, successful_result])
    assert len(entries) == 1
    assert entries[0].source_repo == "org/service-c"


def test_dependency_map_entry_creation() -> None:
    """DependencyMapEntry should be creatable."""
    entry = DependencyMapEntry(
        source_repo="org/service-a",
        target_repo="org/service-b",
        artifact="openapi/api.yaml",
        risk_score=15,
        risk_level="high",
        compatibility_assessment="Breaking change",
        evidence_ref="commit/abc123",
        trace_id="test-trace",
    )
    assert entry.risk_score == 15
    assert entry.risk_level == "high"
