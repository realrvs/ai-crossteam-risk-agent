"""Pytest configuration for dep_agent tests."""

import pytest

from dep_agent.telemetry.otel_setup import setup_otel


@pytest.fixture(autouse=True, scope="session")
def otel_setup() -> None:
    """Initialize OTel once for all tests."""
    setup_otel(service_name="test-agent", exporter="console", sampling_rate=1.0)
