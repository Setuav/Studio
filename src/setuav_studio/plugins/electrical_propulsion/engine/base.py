"""Data structures and types for Electrical Propulsion Solver Engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PropulsionPoint:
    """Calculated aerodynamic/electrical performance at a single operating point."""

    x_val: float
    rpm: float
    thrust: float
    power: float
    current: float
    eta_p: float
    eta_m: float
    eta_sys: float
    j: float
    feasible: bool


@dataclass
class PropulsionResult:
    """Complete result of a propulsion analysis run (sweep or operating point)."""

    mode: str
    points: list[PropulsionPoint] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    feasibility_status: str = "feasible"
    feasibility_message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
