"""Loki log query templates for dep_agent.

Provides structured log query templates for Loki:
- All dep_agent logs with trace_id
- Blocker detection logs
- Secret redaction audit logs
- Error logs

Covers NFR-OBS-001.
"""

from __future__ import annotations

# Loki log query templates
LOG_QUERIES: dict[str, str] = {
    "all_dep_agent": '{app="dep-agent"}',
    "blocker_detected": '{app="dep-agent"} |= "dep_agent.blocker.detected"',
    "secret_redacted": '{app="dep-agent"} |= "security.secret.redacted"',
    "errors": '{app="dep-agent"} |= "ERROR"',
    "with_trace": '{app="dep-agent"} | trace_id="{trace_id}"',
    "by_team": '{app="dep-agent"} | team="{team}"',
}


def get_loki_queries() -> dict[str, str]:
    """Return Loki query templates."""
    return LOG_QUERIES


def save_loki_queries(path: str = "config/loki-queries.json") -> None:
    """Save Loki queries to JSON file."""
    import json

    queries = get_loki_queries()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(queries, fh, indent=2, ensure_ascii=False)
    print(f"Loki queries saved to {path}")
