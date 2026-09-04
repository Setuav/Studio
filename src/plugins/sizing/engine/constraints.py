"""Constraint analysis equations for aircraft matching chart.

Calculates thrust-to-weight (T/W) and power-to-weight (P/W) boundaries as functions
of wing loading (W/S).

References:
- Raymer, D.P., "Aircraft Design: A Conceptual Approach", 7th Ed., Ch. 5.
- Roskam, J., "Airplane Design Part I: Preliminary Sizing", Ch. 3.
- Mattingly, J.D., "Aircraft Engine Design", 3rd Ed., Ch. 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from setuav_studio.model.atmosphere import G0, Atmosphere

from .aerodynamics import AeroParameters


@dataclass(frozen=True)
class ConstraintCurve:
    """Represents an individual performance boundary on the matching chart."""

    id: str
    label: str
    is_vertical: bool  # True for stall / landing limits (W/S <= limit)
    ws_limit_pa: float | None  # Max permissible W/S for vertical limits
    ws_pa: np.ndarray  # Wing loading grid (Pa = N/m^2)
    tw: np.ndarray  # Sea-level static thrust-to-weight ratio (T/W)
    pw: np.ndarray  # Sea-level static power-to-weight ratio (P/W in W/N)
    color: str = "#2196F3"
    line_style: str = "solid"
    meta: dict[str, Any] | None = None


# -----------------------------------------------------------------------------
# 1. Stall Speed Constraint
# -----------------------------------------------------------------------------

def max_wing_loading_stall(
    v_stall_mps: float,
    atmosphere: Atmosphere,
    cl_max: float = 1.35,
) -> float:
    """Compute maximum allowable wing loading based on stall speed limit.

    (W/S)_max = 0.5 * rho * V_s^2 * CL_max  (Pa)
    """
    v_s = max(float(v_stall_mps), 1.0)
    cl = max(float(cl_max), 0.1)
    return 0.5 * atmosphere.density_kg_m3 * (v_s**2) * cl


# -----------------------------------------------------------------------------
# 2. Landing Ground Roll Constraint
# -----------------------------------------------------------------------------

def max_wing_loading_landing(
    landing_ground_roll_m: float,
    atmosphere: Atmosphere,
    cl_max_landing: float = 1.75,
    braking_friction_coeff: float = 0.35,
) -> float:
    """Compute maximum wing loading to stop within landing distance.

    Based on constant deceleration ground roll:
    V_touchdown = 1.15 * V_stall_land
    d_L = V_TD^2 / (2 * g * mu_b)
    => (W/S)_max = (rho * CL_max_L * g * d_L * mu_b) / 1.3225
    """
    d_l = max(float(landing_ground_roll_m), 5.0)
    cl = max(float(cl_max_landing), 0.1)
    mu_b = max(float(braking_friction_coeff), 0.05)
    # 1.15^2 = 1.3225
    return (atmosphere.density_kg_m3 * cl * G0 * d_l * mu_b) / 1.3225


# -----------------------------------------------------------------------------
# 3. Takeoff Ground Roll Constraint
# -----------------------------------------------------------------------------

def takeoff_thrust_to_weight(
    ws_pa: np.ndarray,
    ground_roll_m: float,
    atmosphere: Atmosphere,
    aero: AeroParameters,
    rolling_friction_coeff: float = 0.035,
) -> np.ndarray:
    """Compute required takeoff thrust-to-weight ratio as function of W/S.

    Based on average acceleration to liftoff speed V_LO = 1.1 * V_stall:
    T/W = 1.21 * (W/S) / (rho * g * d_G * CL_max_TO) + CD_TO / (2 * CL_TO) + mu_R / 2

    References: Raymer Eq. 5.8, Roskam Part I Eq. 3.4.
    """
    d_g = max(float(ground_roll_m), 5.0)
    rho = atmosphere.density_kg_m3
    cl_max_to = aero.cl_max_takeoff
    cl_to = cl_max_to / 1.21  # Average lift coefficient during ground run
    cd_to = aero.cd(cl_to)
    mu_r = float(rolling_friction_coeff)

    term_accel = 1.21 * ws_pa / (rho * G0 * d_g * cl_max_to)
    term_aero = cd_to / (2.0 * max(cl_to, 0.01))
    term_friction = mu_r / 2.0

    tw_takeoff = term_accel + term_aero + term_friction
    # Correct back to sea level static (SLS) if altitude > 0
    sigma = max(atmosphere.density_ratio_sigma, 0.1)
    return tw_takeoff / sigma


# -----------------------------------------------------------------------------
# 4. Rate of Climb Constraint
# -----------------------------------------------------------------------------

def climb_thrust_to_weight(
    ws_pa: np.ndarray,
    climb_rate_mps: float,
    v_climb_mps: float,
    atmosphere: Atmosphere,
    aero: AeroParameters,
) -> np.ndarray:
    """Compute required thrust-to-weight ratio for steady climb.

    T/W = (ROC / V) + q * CD0 / (W/S) + k / q * (W/S)

    References: Mattingly Eq. 2.32, Raymer Eq. 5.6.
    """
    roc = max(float(climb_rate_mps), 0.1)
    v_clm = max(float(v_climb_mps), 1.0)
    q = atmosphere.dynamic_pressure(v_clm)
    cd0 = aero.cd0
    k = aero.k

    tw_climb = (roc / v_clm) + (q * cd0) / np.maximum(ws_pa, 1e-3) + (k / q) * ws_pa
    sigma = max(atmosphere.density_ratio_sigma, 0.1)
    return tw_climb / sigma


# -----------------------------------------------------------------------------
# 5. Cruise Speed Constraint
# -----------------------------------------------------------------------------

def cruise_thrust_to_weight(
    ws_pa: np.ndarray,
    v_cruise_mps: float,
    atmosphere: Atmosphere,
    aero: AeroParameters,
) -> np.ndarray:
    """Compute required thrust-to-weight ratio for steady unaccelerated cruise.

    T/W = q * CD0 / (W/S) + k / q * (W/S)

    References: Mattingly Eq. 2.27.
    """
    v_crs = max(float(v_cruise_mps), 1.0)
    q = atmosphere.dynamic_pressure(v_crs)
    cd0 = aero.cd0
    k = aero.k

    tw_cruise = (q * cd0) / np.maximum(ws_pa, 1e-3) + (k / q) * ws_pa
    sigma = max(atmosphere.density_ratio_sigma, 0.1)
    return tw_cruise / sigma


# -----------------------------------------------------------------------------
# 6. Sustained Coordinated Turn Constraint
# -----------------------------------------------------------------------------

def turn_thrust_to_weight(
    ws_pa: np.ndarray,
    load_factor_n: float,
    v_turn_mps: float,
    atmosphere: Atmosphere,
    aero: AeroParameters,
) -> tuple[np.ndarray, float]:
    """Compute required thrust-to-weight ratio for sustained level turn.

    n = 1 / cos(phi)
    T/W = q * CD0 / (W/S) + k * n^2 / q * (W/S)

    Also returns the stall cutoff limit ws_max_turn: (W/S)_max = q * CL_max / n.

    References: Mattingly Eq. 2.33.
    """
    n = max(float(load_factor_n), 1.0)
    v_trn = max(float(v_turn_mps), 1.0)
    q = atmosphere.dynamic_pressure(v_trn)
    cd0 = aero.cd0
    k = aero.k

    tw_turn = (q * cd0) / np.maximum(ws_pa, 1e-3) + (k * (n**2) / q) * ws_pa
    ws_max_turn = (q * aero.cl_max_clean) / n

    sigma = max(atmosphere.density_ratio_sigma, 0.1)
    return tw_turn / sigma, ws_max_turn


# -----------------------------------------------------------------------------
# 7. Service Ceiling Constraint
# -----------------------------------------------------------------------------

def service_ceiling_thrust_to_weight(
    ws_pa: np.ndarray,
    ceiling_altitude_m: float,
    v_ceiling_mps: float,
    aero: AeroParameters,
    min_roc_mps: float = 0.508,  # 100 ft/min standard definition
) -> np.ndarray:
    """Compute required sea-level thrust-to-weight to achieve service ceiling.

    At ceiling altitude, minimum climb rate ROC_min = 100 ft/min (0.508 m/s).
    """
    atm_ceil = Atmosphere.isa(max(float(ceiling_altitude_m), 100.0))
    v_ceil = max(float(v_ceiling_mps), 1.0)
    q_ceil = atm_ceil.dynamic_pressure(v_ceil)
    cd0 = aero.cd0
    k = aero.k

    tw_ceil = (min_roc_mps / v_ceil) + (q_ceil * cd0) / np.maximum(ws_pa, 1e-3) + (k / q_ceil) * ws_pa
    sigma_ceil = max(atm_ceil.density_ratio_sigma, 0.05)
    return tw_ceil / sigma_ceil


__all__ = [
    "ConstraintCurve",
    "climb_thrust_to_weight",
    "cruise_thrust_to_weight",
    "max_wing_loading_landing",
    "max_wing_loading_stall",
    "service_ceiling_thrust_to_weight",
    "takeoff_thrust_to_weight",
    "turn_thrust_to_weight",
]
