"""Detector package for dep_agent."""

from dep_agent.detector.silence_detector import (
    SILENCE_WINDOWS,
    BlockerCandidate,
    SilenceDetector,
)

__all__ = ["SilenceDetector", "BlockerCandidate", "SILENCE_WINDOWS"]
