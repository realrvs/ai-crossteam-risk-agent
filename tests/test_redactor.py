"""Tests for SecretRedactor (TC-SEC-002)."""

import io
import logging

from dep_agent.security.redactor import SecretRedactor

GHP_TOKEN = "ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"


def test_redact_github_token() -> None:
    redactor = SecretRedactor()
    text = f"token={GHP_TOKEN}"
    result = redactor.redact(text)
    assert GHP_TOKEN not in result
    assert "[REDACTED:github_token]" in result


def test_redact_gitlab_token() -> None:
    redactor = SecretRedactor()
    text = "GL_TOKEN=glpat-ABCDEFghijklmnopqrstuv"
    result = redactor.redact(text)
    assert "glpat-ABCDEFghijklmnopqrstuv" not in result
    assert "[REDACTED:gitlab_token]" in result


def test_redact_yandex_oauth() -> None:
    redactor = SecretRedactor()
    text = "oauth=ya2_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    result = redactor.redact(text)
    assert "ya2_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in result
    assert "[REDACTED:yandex_oauth]" in result


def test_redact_aws_key() -> None:
    redactor = SecretRedactor()
    text = "AKIAIOSFODNN7EXAMPLE"
    result = redactor.redact(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "[REDACTED:aws_access_key]" in result


def test_redact_bearer_token() -> None:
    redactor = SecretRedactor()
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
    result = redactor.redact(text)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test" not in result
    assert "[REDACTED:bearer_token]" in result


def test_redact_no_secrets_unchanged() -> None:
    redactor = SecretRedactor()
    text = "This is a normal message without secrets"
    result = redactor.redact(text)
    assert result == text


def test_redact_disabled() -> None:
    redactor = SecretRedactor(enabled=False)
    text = f"token={GHP_TOKEN}"
    result = redactor.redact(text)
    assert result == text


def test_redact_dict() -> None:
    redactor = SecretRedactor()
    data = {
        "token": GHP_TOKEN,
        "message": "normal text",
        "nested": {"key": "ya2_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"},
    }
    result = redactor.redact_dict(data)
    assert GHP_TOKEN not in result["token"]
    assert result["message"] == "normal text"
    assert "ya2_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in result["nested"]["key"]


def test_redact_list() -> None:
    redactor = SecretRedactor()
    items = [GHP_TOKEN, "normal text"]
    result = redactor.redact_list(items)
    assert GHP_TOKEN not in result[0]
    assert result[1] == "normal text"


def test_redact_audit_log_emitted() -> None:
    """Verify audit log is emitted when secrets are found."""
    redactor = SecretRedactor()
    text = f"token={GHP_TOKEN}"

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.WARNING)
    logger = logging.getLogger("dep_agent.security")
    logger.addHandler(handler)
    redactor.redact(text, component="test", trace_id="test-trace-123")
    logger.removeHandler(handler)
