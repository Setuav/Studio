"""Data structures and types for Electrical Propulsion Solver Engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PropulsionPoint:
    """Calculated aerodynamic and electrical performance at a single operating point."""

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
