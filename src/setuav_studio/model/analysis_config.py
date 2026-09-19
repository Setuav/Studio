"""Core analysis configuration domain model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from setuav_studio.solver.base import SolverConfig


@dataclass
class AnalysisConfig:
    """Project-level persistent configuration for a solver run.

    Stored inside ProjectDocument.data["analysis_configs"] and bound to Properties Panel.
    """

    solver_id: str
    name: str = "New Analysis"
    config_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parameters: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    def to_solver_config(self) -> SolverConfig:
        """Convert this AnalysisConfig into a SolverConfig for solver execution."""
        return SolverConfig(
            config_id=self.config_id,
            solver_id=self.solver_id,
            name=self.name,
            parameters=dict(self.parameters),
            options=dict(self.options),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a JSON-compatible dictionary."""
        return {
            "config_id": self.config_id,
            "solver_id": self.solver_id,
            "name": self.name,
            "parameters": self.parameters,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisConfig:
        """Deserialize configuration from a dictionary."""
        return cls(
            config_id=str(data.get("config_id", uuid.uuid4())),
            solver_id=str(data.get("solver_id", "")),
            name=str(data.get("name", "New Analysis")),
            parameters=dict(data.get("parameters", {})),
            options=dict(data.get("options", {})),
        )
