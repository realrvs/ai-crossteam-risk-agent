"""Tests for observability components (TC-OBS-001)."""

import json
import os

from dep_agent.observability.alert_rules import (
    get_alert_rules,
    save_alert_rules,
)
from dep_agent.observability.grafana_dashboard import (
    get_dashboard_json,
    save_dashboard,
)
from dep_agent.observability.loki_queries import (
    get_loki_queries,
    save_loki_queries,
)


def test_get_dashboard_json() -> None:
    """Dashboard JSON should have required structure."""
    dashboard = get_dashboard_json()
    assert "panels" in dashboard
    assert "title" in dashboard
    assert "uid" in dashboard
    assert len(dashboard["panels"]) >= 5


def test_dashboard_has_required_panels() -> None:
    """Dashboard should have panels for all key metrics."""
    dashboard = get_dashboard_json()
    panel_titles = [p.get("title", "") for p in dashboard["panels"]]
    assert any("Request Rate" in t for t in panel_titles)
    assert any("Error Rate" in t for t in panel_titles)
    assert any("Duration" in t for t in panel_titles)
    assert any("Commits Filtered" in t for t in panel_titles)
    assert any("LLM Validation" in t for t in panel_titles)
    assert any("Blockers" in t for t in panel_titles)


def test_save_dashboard(tmp_path: str) -> None:
    """Should save dashboard JSON to file."""
    path = str(tmp_path / "test-dashboard.json")
    save_dashboard(path)
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert "panels" in data


def test_get_alert_rules() -> None:
    """Alert rules should have required groups."""
    rules = get_alert_rules()
    assert len(rules) >= 2
    group_names = [g["name"] for g in rules]
    assert "dep-agent-slo" in group_names
    assert "dep-agent-operational" in group_names


def test_alert_rules_have_slo_rules() -> None:
    """SLO group should have latency, error rate, and availability alerts."""
    rules = get_alert_rules()
    slo_group = next(g for g in rules if g["name"] == "dep-agent-slo")
    alert_names = [r["alert"] for r in slo_group["rules"]]
    assert "DepAgentHighLatency" in alert_names
    assert "DepAgentHighErrorRate" in alert_names
    assert "DepAgentLowAvailability" in alert_names


def test_alert_rules_have_operational_rules() -> None:
    """Operational group should have blocker count and LLM alerts."""
    rules = get_alert_rules()
    ops_group = next(g for g in rules if g["name"] == "dep-agent-operational")
    alert_names = [r["alert"] for r in ops_group["rules"]]
    assert "DepAgentHighBlockerCount" in alert_names
    assert "DepAgentLlmValidationSlow" in alert_names


def test_save_alert_rules(tmp_path: str) -> None:
    """Should save alert rules to YAML file."""
    path = str(tmp_path / "test-alert-rules.yml")
    save_alert_rules(path)
    assert os.path.exists(path)


def test_get_loki_queries() -> None:
    """Loki queries should have required templates."""
    queries = get_loki_queries()
    assert "all_dep_agent" in queries
    assert "blocker_detected" in queries
    assert "secret_redacted" in queries
    assert "errors" in queries
    assert "with_trace" in queries


def test_loki_query_with_trace() -> None:
    """Trace-based query should use trace_id placeholder."""
    queries = get_loki_queries()
    assert "{trace_id}" in queries["with_trace"]


def test_save_loki_queries(tmp_path: str) -> None:
    """Should save Loki queries to JSON file."""
    path = str(tmp_path / "test-loki-queries.json")
    save_loki_queries(path)
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert "blocker_detected" in data
