"""Aircraft aerodynamic model for flight performance, from an AeroBuildup polar."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from plugins.aerodynamics.engine.aerosandbox_engine import (
    AeroSandboxEngine,
    AnalysisMethod,
    FlightCondition,
)
from plugins.aerodynamics.engine.base import AeroAnalysisError

from .performance import AerodynamicModel, aerobuildup_cl_max, fit_drag_polar


def aerobuildup_model(
    components: list[dict[str, Any]],
    *,
    velocity: float,
    altitude: float,
    alpha_min: float,
    alpha_max: float,
    alpha_step: float,
    progress_callback: Callable[[int, int, str], None] | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> AerodynamicModel:
    """Return the aircraft's aerodynamic model from an AeroBuildup alpha sweep.

    The sweep must reach stall: CLmax is taken from the polar peak, and only the
    converged points up to that peak form the drag polar.
    """
    result = AeroSandboxEngine().analyze(
        components=components,
        condition=FlightCondition(
            velocity=velocity,
            altitude=altitude,
            sweep_variable="alpha",
            sweep_min=alpha_min,
            sweep_max=alpha_max,
            sweep_steps=round((alpha_max - alpha_min) / alpha_step) + 1,
        ),
        method=AnalysisMethod.AERO_BUILDUP,
        progress_callback=progress_callback,
        include_stability=False,
        check_cancelled=check_cancelled,
    )
    area_m2 = result.reference.s_ref
    if area_m2 <= 0.0:
        raise AeroAnalysisError("Aircraft has no reference wing area.")

    cl_max, alpha_at_cl_max, confirmed = aerobuildup_cl_max(result.polar_points)
    if not confirmed:
        raise AeroAnalysisError(
            f"The AeroBuildup polar does not reach stall up to α = {alpha_max:g}°; "
            "increase the polar AoA maximum."
        )
    pre_stall = sorted(
        (point for point in result.polar_points if point.converged),
        key=lambda point: point.cl,
    )
    pre_stall = [point for point in pre_stall if point.alpha <= alpha_at_cl_max]
    polar_cl = np.array([point.cl for point in pre_stall], dtype=float)
    polar_cd = np.array([point.cd for point in pre_stall], dtype=float)
    return AerodynamicModel(
        area_m2=area_m2,
        cl_max=cl_max,
        polar_cl=polar_cl,
        polar_cd=polar_cd,
        drag_polar=fit_drag_polar(polar_cl, polar_cd),
        notes=tuple(result.notes),
    )


__all__ = ["aerobuildup_model"]
