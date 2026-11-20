"""Observability package for dep_agent."""

from dep_agent.observability.grafana_dashboard import (
    get_dashboard_json,
    save_dashboard,
)
from dep_agent.observability.alert_rules import (
    get_alert_rules,
    save_alert_rules,
)
from dep_agent.observability.loki_queries import (
    get_loki_queries,
    save_loki_queries,
)

__all__ = [
    "get_dashboard_json",
    "save_dashboard",
    "get_alert_rules",
    "save_alert_rules",
    "get_loki_queries",
    "save_loki_queries",
]
