"""Base definitions for core solvers and configuration objects."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from setuav_studio.task.types import CancellationToken

    from .results import AnalysisResult


class SolverStatus(StrEnum):
    """Execution status of a solver task."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SolverConfig:
    """Input configuration for a solver execution.

    Holds solver parameters, options, and boundary conditions required for an analysis.
    """

    solver_id: str
    name: str = "Analysis Config"
    parameters: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    config_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a dictionary."""
        return {
            "config_id": self.config_id,
            "solver_id": self.solver_id,
            "name": self.name,
            "parameters": self.parameters,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SolverConfig:
        """Deserialize configuration from a dictionary."""
        return cls(
            config_id=str(data.get("config_id", uuid.uuid4())),
            solver_id=str(data.get("solver_id", "")),
            name=str(data.get("name", "Analysis Config")),
            parameters=dict(data.get("parameters", {})),
            options=dict(data.get("options", {})),
        )

    def to_analysis_config(self) -> Any:
        """Convert this SolverConfig into an AnalysisConfig."""
        from setuav_studio.model.analysis_config import AnalysisConfig

        return AnalysisConfig(
            config_id=self.config_id,
            solver_id=self.solver_id,
            name=self.name,
            parameters=dict(self.parameters),
            options=dict(self.options),
        )


class AbstractSolver(ABC):
    """Abstract base class for all engineering solvers in Setuav Studio.

    Solvers receive a immutable SolverConfig and produce an AnalysisResult.
    """

    def __init__(self, config: SolverConfig) -> None:
        self.config = config
        self.status = SolverStatus.QUEUED
        self.progress: float = 0.0
        self.error_message: str | None = None
        self._cancel_requested: bool = False
        self.token: CancellationToken | None = None

    @property
    def is_cancel_requested(self) -> bool:
        """Return whether cancellation was requested."""
        return self._cancel_requested

    def cancel(self) -> None:
        """Request cancellation of the solver run."""
        self._cancel_requested = True
        cancel_fn = getattr(self.token, "cancel", None)
        if callable(cancel_fn):
            cancel_fn()

    @abstractmethod
    def run(self) -> AnalysisResult:
        """Execute the solver algorithm and return the analysis result.

        Must be implemented by concrete solvers. Long-running solvers should
        periodically check self.is_cancel_requested and update self.progress.
        """
        ...
