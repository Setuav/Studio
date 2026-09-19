"""Core solver and analysis result infrastructure."""

from __future__ import annotations

from .base import AbstractSolver, SolverConfig, SolverStatus
from .results import AnalysisResult

__all__ = [
    "AbstractSolver",
    "AnalysisResult",
    "SolverConfig",
    "SolverStatus",
]
