"""Base definitions for core solvers and configuration objects."""

from __future__ import annotations

import math
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from setuav_studio.api.contributions import ParameterField
    from setuav_studio.task.types import CancellationToken

    from .results import SolverResult


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

    Holds the solver parameters required for an analysis.
    """

    solver_id: str
    name: str = "Analysis Config"
    parameters: dict[str, Any] = field(default_factory=dict)
    config_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a dictionary."""
        return {
            "config_id": self.config_id,
            "solver_id": self.solver_id,
            "name": self.name,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SolverConfig:
        """Deserialize configuration from a dictionary."""
        return cls(
            config_id=str(data["config_id"]),
            solver_id=str(data["solver_id"]),
            name=str(data["name"]),
            parameters=dict(data["parameters"]),
        )


class AbstractSolver(ABC):
    """Abstract base class for all engineering solvers in Setuav Studio.

    Solvers receive an immutable SolverConfig and produce a SolverResult.
    ``PARAMETER_FIELDS`` declares the editable schema of ``SolverConfig.parameters``.
    """

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = []

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        """Return the default value of every declared parameter."""
        return {field.key: field.default for field in cls.PARAMETER_FIELDS}

    def check_parameter_ranges(self) -> None:
        """Raise ValueError for a numeric parameter outside its declared range."""
        for spec in self.PARAMETER_FIELDS:
            value = self.config.parameters[spec.key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            low = -math.inf if spec.min_value is None else spec.min_value
            high = math.inf if spec.max_value is None else spec.max_value
            if not low <= value <= high:
                raise ValueError(
                    f"Parameter '{spec.key}' = {value:g} is outside [{low:g}, {high:g}]."
                )

    def __init__(self, config: SolverConfig, project: Any | None = None) -> None:
        self.config = config
        self.project = project
        self.api: Any | None = None
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
        if self.token is not None:
            self.token.cancel()

    @abstractmethod
    def run(self) -> SolverResult:
        """Execute the solver algorithm and return the solver result.

        Must be implemented by concrete solvers. Long-running solvers should
        periodically check self.is_cancel_requested and update self.progress.
        """
        ...
