"""Prometheus alert rules for dep_agent.

Defines alerting rules for:
- SLO degradation (latency p95 > 2000ms)
- Error rate > 1%
- Availability < 99.5%
- High blocker count

Covers NFR-001, NFR-OBS-001.
"""

from __future__ import annotations

import json
from typing import Any

ALERT_RULES_FILE = "config/prometheus-alert-rules.yml"


def get_alert_rules() -> list[dict[str, Any]]:
    """Return Prometheus alert rules as a list of rule groups."""
    return [
        {
            "name": "dep-agent-slo",
            "rules": [
                {
                    "alert": "DepAgentHighLatency",
                    "expr": "histogram_quantile(0.95, sum(rate(dep_agent_request_duration_seconds_bucket[5m])) by (le)) > 2",
                    "for": "5m",
                    "labels": {"severity": "warning"},
                    "annotations": {
                        "summary": "Dep Agent p95 latency > 2s",
                        "description": "p95 latency is {{ $value }}s (threshold: 2s). SLO: p95 <= 2000ms.",
                    },
                },
                {
                    "alert": "DepAgentHighErrorRate",
                    "expr": "sum(rate(dep_agent_request_total{status=~\"5..\"}[5m])) / sum(rate(dep_agent_request_total[5m])) > 0.01",
                    "for": "5m",
                    "labels": {"severity": "critical"},
                    "annotations": {
                        "summary": "Dep Agent error rate > 1%",
                        "description": "Error rate is {{ $value | humanizePercentage }} (threshold: 1%). SLO: error rate <= 1%.",
                    },
                },
                {
                    "alert": "DepAgentLowAvailability",
                    "expr": "1 - (sum(rate(dep_agent_request_total{status=~\"2..\"}[5m])) / sum(rate(dep_agent_request_total[5m]))) < 0.995",
                    "for": "10m",
                    "labels": {"severity": "critical"},
                    "annotations": {
                        "summary": "Dep Agent availability < 99.5%",
                        "description": "Availability is {{ $value | humanizePercentage }} (threshold: 99.5%). SLO: availability >= 99.5%.",
                    },
                },
            ],
        },
        {
            "name": "dep-agent-operational",
            "rules": [
                {
                    "alert": "DepAgentHighBlockerCount",
                    "expr": "sum(dep_agent_blockers_detected_total) > 50",
                    "for": "15m",
                    "labels": {"severity": "warning"},
                    "annotations": {
                        "summary": "High blocker count detected",
                        "description": "{{ $value }} blockers detected in the last 15 minutes.",
                    },
                },
                {
                    "alert": "DepAgentLlmValidationSlow",
                    "expr": "histogram_quantile(0.95, sum(rate(dep_agent_llm_validation_duration_seconds_bucket[5m])) by (le)) > 30",
                    "for": "10m",
                    "labels": {"severity": "warning"},
                    "annotations": {
                        "summary": "LLM validation p95 > 30s",
                        "description": "p95 LLM validation duration is {{ $value }}s. Consider increasing max_llm_candidates or switching model.",
                    },
                },
                {
                    "alert": "DepAgentNoTraffic",
                    "expr": "sum(rate(dep_agent_request_total[15m])) == 0",
                    "for": "30m",
                    "labels": {"severity": "info"},
                    "annotations": {
                        "summary": "No traffic to Dep Agent",
                        "description": "No requests received in the last 30 minutes. Check if the service is running.",
                    },
                },
            ],
        },
    ]


def save_alert_rules(path: str = ALERT_RULES_FILE) -> None:
    """Save alert rules to YAML file."""
    import yaml

    rules = get_alert_rules()
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(
            {"groups": rules},
            fh,
            default_flow_style=False,
            sort_keys=False,
        )
    print(f"Alert rules saved to {path}")
