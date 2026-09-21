"""Core solver and analysis result infrastructure."""

from __future__ import annotations

from .base import AbstractSolver, SolverConfig, SolverStatus
from .results import SolverResult
from .runner import SolverRunner, execute_solver

__all__ = [
    "AbstractSolver",
    "SolverConfig",
    "SolverResult",
    "SolverRunner",
    "SolverStatus",
    "execute_solver",
]
