"""Grafana dashboard provisioning for dep_agent.

Provides JSON dashboard definitions for:
- RED metrics (Rate, Errors, Duration)
- Funnel metrics (commits filtered, blockers detected)
- LLM validation metrics
- System health

Covers NFR-001, NFR-OBS-001.
"""

from __future__ import annotations

import json
from typing import Any

DASHBOARD_TITLE = "Dep Agent — Cross-Team Risk Monitoring"


def get_dashboard_json() -> dict[str, Any]:
    """Return the Grafana dashboard JSON definition.

    Panels:
    1. Request Rate (dep_agent_request_total)
    2. Error Rate (dep_agent_request_errors_total)
    3. Request Duration p50/p95/p99 (dep_agent_request_duration_seconds)
    4. Commits Filtered (dep_agent_commits_filtered_total)
    5. LLM Validation Duration (dep_agent_llm_validation_duration_seconds)
    6. Blockers Detected (dep_agent_blockers_detected_total)
    7. Active Candidates (dep_agent_blocker_candidates_active)
    8. System Uptime
    """
    return {
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "hide": True,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations & Alerts",
                    "type": "dashboard",
                }
            ]
        },
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "panels": [
            {
                "title": "Request Rate",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 8, "x": 0, "y": 0},
                "targets": [
                    {
                        "expr": "sum(rate(dep_agent_request_total[5m]))",
                        "legendFormat": "req/s",
                    }
                ],
            },
            {
                "title": "Error Rate",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 8, "x": 8, "y": 0},
                "targets": [
                    {
                        "expr": "sum(rate(dep_agent_request_total{status=~\"5..\"}[5m]))",
                        "legendFormat": "5xx/s",
                    },
                    {
                        "expr": "sum(rate(dep_agent_request_total{status=~\"4..\"}[5m]))",
                        "legendFormat": "4xx/s",
                    },
                ],
            },
            {
                "title": "Request Duration (p50/p95/p99)",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 8, "x": 16, "y": 0},
                "targets": [
                    {
                        "expr": "histogram_quantile(0.50, sum(rate(dep_agent_request_duration_seconds_bucket[5m])) by (le))",
                        "legendFormat": "p50",
                    },
                    {
                        "expr": "histogram_quantile(0.95, sum(rate(dep_agent_request_duration_seconds_bucket[5m])) by (le))",
                        "legendFormat": "p95",
                    },
                    {
                        "expr": "histogram_quantile(0.99, sum(rate(dep_agent_request_duration_seconds_bucket[5m])) by (le))",
                        "legendFormat": "p99",
                    },
                ],
            },
            {
                "title": "Commits Filtered",
                "type": "stat",
                "gridPos": {"h": 8, "w": 6, "x": 0, "y": 8},
                "targets": [
                    {
                        "expr": "sum(dep_agent_commits_filtered_total{outcome=\"kept\"})",
                        "legendFormat": "Kept",
                    },
                    {
                        "expr": "sum(dep_agent_commits_filtered_total{outcome=\"dropped\"})",
                        "legendFormat": "Dropped",
                    },
                ],
            },
            {
                "title": "LLM Validation Duration",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 6, "x": 6, "y": 8},
                "targets": [
                    {
                        "expr": "histogram_quantile(0.95, sum(rate(dep_agent_llm_validation_duration_seconds_bucket[5m])) by (le))",
                        "legendFormat": "p95",
                    },
                ],
            },
            {
                "title": "Blockers Detected",
                "type": "stat",
                "gridPos": {"h": 8, "w": 6, "x": 12, "y": 8},
                "targets": [
                    {
                        "expr": "sum(dep_agent_blockers_detected_total)",
                        "legendFormat": "Total",
                    },
                ],
            },
            {
                "title": "Active Candidates",
                "type": "stat",
                "gridPos": {"h": 8, "w": 6, "x": 18, "y": 8},
                "targets": [
                    {
                        "expr": "sum(dep_agent_blocker_candidates_active)",
                        "legendFormat": "Active",
                    },
                ],
            },
            {
                "title": "System Uptime",
                "type": "stat",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
                "targets": [
                    {
                        "expr": "time() - process_start_time_seconds{job=\"dep-agent\"}",
                        "legendFormat": "Seconds",
                    },
                ],
            },
        ],
        "schemaVersion": 39,
        "tags": ["dep-agent", "risk"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "title": DASHBOARD_TITLE,
        "uid": "dep-agent-main",
        "version": 1,
    }


def save_dashboard(path: str = "config/grafana-dashboard.json") -> None:
    """Save dashboard JSON to file."""
    dashboard = get_dashboard_json()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dashboard, fh, indent=2, ensure_ascii=False)
    print(f"Dashboard saved to {path}")
