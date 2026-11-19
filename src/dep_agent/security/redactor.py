"""Secret redactor for dep_agent.

Masks known token/secret formats before logging, LLM prompts, and telemetry export.
Emits audit log `security.secret.redacted` with secret_type, component, trace_id.

Covers TM-02 (Information Disclosure) and NFR-SEC-002.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class SecretRedactor:
    """Regex-based secret redactor.

    Masks:
    - GitHub tokens: ghp_[A-Za-z0-9_]{36,}
    - GitLab tokens: glpat-[A-Za-z0-9\-_]{20,}
    - Yandex OAuth tokens: ya2_[A-Za-z0-9_\-]{30,}
    - Generic API keys: api[_-]?key[_=:\s]+[A-Za-z0-9_\-]{20,}
    - AWS access keys: AKIA[0-9A-Z]{16}
    - Generic bearer tokens: Bearer [A-Za-z0-9_\-\.]{20,}
    """

    # Patterns: (regex, secret_type_label)
    PATTERNS: list[tuple[str, str]] = [
        (r"ghp_[A-Za-z0-9_]{36,}", "github_token"),
        (r"glpat-[A-Za-z0-9\-_]{20,}", "gitlab_token"),
        (r"ya2_[A-Za-z0-9_\-]{30,}", "yandex_oauth"),
        (r"AKIA[0-9A-Z]{16}", "aws_access_key"),
        (r"(?i)api[_\-]?key[_=:]\s*[A-Za-z0-9_\-]{20,}", "api_key"),
        (r"(?i)Bearer\s+[A-Za-z0-9_\-\.]{20,}", "bearer_token"),
    ]

    def __init__(self, enabled: bool = True, strict: bool = False) -> None:
        self._enabled = enabled
        self._strict = strict  # If True, redact even partial matches
        self._compiled: list[tuple[re.Pattern[str], str]] = []
        for pattern, secret_type in self.PATTERNS:
            self._compiled.append((re.compile(pattern), secret_type))

    def redact(self, text: str, component: str = "unknown", trace_id: str | None = None) -> str:
        """Redact secrets from text.

        Args:
            text: Input text that may contain secrets.
            component: Component name for audit log.
            trace_id: Trace ID for correlation.

        Returns:
            Text with secrets replaced by [REDACTED:<type>] markers.
        """
        if not self._enabled:
            return text

        redacted = text
        for pattern, secret_type in self._compiled:
            matches = pattern.findall(redacted)
            if matches:
                # Log audit event
                self._emit_audit(secret_type, component, trace_id, len(matches))
                # Replace all matches
                redacted = pattern.sub(f"[REDACTED:{secret_type}]", redacted)

        return redacted

    def redact_dict(
        self, data: dict[str, Any], component: str = "unknown", trace_id: str | None = None
    ) -> dict[str, Any]:
        """Recursively redact secrets in a nested dict.

        Args:
            data: Input dict that may contain secret values.
            component: Component name for audit log.
            trace_id: Trace ID for correlation.

        Returns:
            Dict with all string values redacted.
        """
        if not self._enabled:
            return data

        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.redact(value, component, trace_id)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value, component, trace_id)
            elif isinstance(value, list):
                result[key] = [
                    self.redact(item, component, trace_id) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def redact_list(
        self, items: list[str], component: str = "unknown", trace_id: str | None = None
    ) -> list[str]:
        """Redact secrets in a list of strings.

        Args:
            items: List of strings that may contain secrets.
            component: Component name for audit log.
            trace_id: Trace ID for correlation.

        Returns:
            List with all strings redacted.
        """
        if not self._enabled:
            return items
        return [self.redact(item, component, trace_id) for item in items]

    def _emit_audit(
        self, secret_type: str, component: str, trace_id: str | None, count: int
    ) -> None:
        """Emit audit log for redacted secret."""
        audit_logger = logging.getLogger("dep_agent.security")
        extra: dict[str, Any] = {
            "secret_type": secret_type,
            "component": component,
            "count": count,
        }
        if trace_id:
            extra["trace_id"] = trace_id
        audit_logger.warning(
            "security.secret.redacted",
            extra=extra,
        )

    def is_enabled(self) -> bool:
        """Check if redaction is enabled."""
        return self._enabled
