"""Flight performance computation package."""

from .aerodynamics import aerobuildup_model
from .performance import (
    AerodynamicModel,
    DragPolar,
    PerformanceEnvelope,
    PropulsionSweep,
    aerobuildup_cl_max,
    feasible_throttle_range,
    fit_drag_polar,
    level_flight_envelope,
    max_level_speed,
    stall_speed,
    throttle_for_thrust,
    velocity_sweep,
)

__all__ = [
    "AerodynamicModel",
    "DragPolar",
    "PerformanceEnvelope",
    "PropulsionSweep",
    "aerobuildup_cl_max",
    "aerobuildup_model",
    "feasible_throttle_range",
    "fit_drag_polar",
    "level_flight_envelope",
    "max_level_speed",
    "stall_speed",
    "throttle_for_thrust",
    "velocity_sweep",
]
