"""Immutable analysis result model."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any

from .base import SolverConfig, SolverStatus


@dataclass
class AnalysisResult:
    """Standardized output result produced by a solver execution.

    Holds scalar metrics, data tables, file/artifact references, and execution metadata.
    """

    solver_id: str
    config: SolverConfig
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Analysis Result"
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    status: SolverStatus = SolverStatus.COMPLETED
    execution_time_ms: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "solver_id": self.solver_id,
            "name": self.name,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "execution_time_ms": self.execution_time_ms,
            "config": self.config.to_dict(),
            "metrics": self.metrics,
            "tables": self.tables,
            "artifacts": self.artifacts,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisResult:
        """Deserialize result from a dictionary."""
        raw_status = data.get("status", "completed")
        try:
            status = SolverStatus(raw_status)
        except ValueError:
            status = SolverStatus.COMPLETED

        config_data = data.get("config", {})
        config = (
            SolverConfig.from_dict(config_data)
            if isinstance(config_data, dict)
            else SolverConfig(solver_id=str(data.get("solver_id", "")))
        )

        return cls(
            id=str(data.get("id", uuid.uuid4())),
            solver_id=str(data.get("solver_id", config.solver_id)),
            name=str(data.get("name", "Analysis Result")),
            timestamp=str(data.get("timestamp", datetime.datetime.now(datetime.UTC).isoformat())),
            status=status,
            execution_time_ms=float(data.get("execution_time_ms", 0.0)),
            config=config,
            metrics={str(k): float(v) for k, v in data.get("metrics", {}).items()},
            tables=dict(data.get("tables", {})),
            artifacts={str(k): str(v) for k, v in data.get("artifacts", {}).items()},
            error_message=data.get("error_message"),
        )
