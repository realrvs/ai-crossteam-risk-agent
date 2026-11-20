"""Detector package for dep_agent."""

from dep_agent.detector.silence_detector import (
    SilenceDetector,
    BlockerCandidate,
    SILENCE_WINDOWS,
)

__all__ = ["SilenceDetector", "BlockerCandidate", "SILENCE_WINDOWS"]
