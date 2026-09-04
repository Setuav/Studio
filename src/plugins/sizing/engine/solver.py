"""Integrated matching chart solver combining constraints and design point selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from setuav_studio.model.atmosphere import Atmosphere

from .aerodynamics import AeroParameters
from .constraints import (
    ConstraintCurve,
    climb_thrust_to_weight,
    cruise_thrust_to_weight,
    max_wing_loading_landing,
    max_wing_loading_stall,
    service_ceiling_thrust_to_weight,
    takeoff_thrust_to_weight,
    turn_thrust_to_weight,
)
from .converters import tw_to_pw
from .weight import MissionProfile, SizingResult, converge_sizing


@dataclass(frozen=True)
class MatchingChartAnalysis:
    """Full constraint analysis results containing all curves and boundaries."""

    mission: MissionProfile
    aero: AeroParameters
    atmosphere: Atmosphere
    ws_grid_pa: np.ndarray  # Grid of wing loadings for continuous curves
    curves: list[ConstraintCurve]  # List of all individual constraint curves
    ws_max_stall_pa: float  # Stall cutoff boundary
    ws_max_landing_pa: float  # Landing cutoff boundary
    combined_min_pw_wn: np.ndarray  # Envelope boundary: max(pw) across all flight phases
    optimum_design_point: tuple[float, float]  # (W/S_opt, P/W_opt)


def compute_matching_chart(
    mission: MissionProfile,
    aero: AeroParameters,
    atmosphere: Atmosphere | None = None,
    grid_points: int = 150,
) -> MatchingChartAnalysis:
    """Compute all matching chart constraints across an adaptive wing loading grid."""
    atm = atmosphere or Atmosphere.isa(mission.cruise_altitude_m)

    # 1. Vertical limits (Stall & Landing)
    ws_stall = max_wing_loading_stall(
        v_stall_mps=mission.v_stall_mps,
        atmosphere=atm,
        cl_max=aero.cl_max_clean,
    )
    ws_landing = max_wing_loading_landing(
        landing_ground_roll_m=mission.ground_roll_landing_m,
        atmosphere=atm,
        cl_max_landing=aero.cl_max_landing,
    )

    # Upper bound for W/S grid
    max_limit = min(ws_stall, ws_landing)
    ws_max_grid = max(max_limit * 1.25, 50.0)
    ws_grid = np.linspace(10.0, ws_max_grid, grid_points)

    # 2. Individual Flight Phase Constraints
    # (a) Takeoff
    tw_to = takeoff_thrust_to_weight(
        ws_pa=ws_grid,
        ground_roll_m=mission.ground_roll_takeoff_m,
        atmosphere=atm,
        aero=aero,
    )
    # Average speed during ground roll is ~0.7 * V_LO
    v_to_avg = 0.7 * 1.1 * mission.v_stall_mps
    pw_to = tw_to_pw(tw_to, speed_mps=v_to_avg, propeller_efficiency=0.50)

    # (b) Climb
    tw_clm = climb_thrust_to_weight(
        ws_pa=ws_grid,
        climb_rate_mps=mission.roc_mps,
        v_climb_mps=mission.v_climb_mps,
        atmosphere=atm,
        aero=aero,
    )
    pw_clm = tw_to_pw(tw_clm, speed_mps=mission.v_climb_mps, propeller_efficiency=0.72)

    # (c) Cruise
    tw_crs = cruise_thrust_to_weight(
        ws_pa=ws_grid,
        v_cruise_mps=mission.v_cruise_mps,
        atmosphere=atm,
        aero=aero,
    )
    pw_crs = tw_to_pw(tw_crs, speed_mps=mission.v_cruise_mps, propeller_efficiency=0.82)

    # (d) Turn
    tw_trn, ws_turn_limit = turn_thrust_to_weight(
        ws_pa=ws_grid,
        load_factor_n=mission.turn_load_factor_n,
        v_turn_mps=mission.v_cruise_mps,
        atmosphere=atm,
        aero=aero,
    )
    pw_trn = tw_to_pw(tw_trn, speed_mps=mission.v_cruise_mps, propeller_efficiency=0.78)

    # (e) Service Ceiling (estimated at cruise altitude + 1500m or at least 2500m)
    ceil_alt = max(mission.cruise_altitude_m + 1500.0, 2500.0)
    tw_ceil = service_ceiling_thrust_to_weight(
        ws_pa=ws_grid,
        ceiling_altitude_m=ceil_alt,
        v_ceiling_mps=mission.v_cruise_mps * 0.9,
        aero=aero,
    )
    pw_ceil = tw_to_pw(tw_ceil, speed_mps=mission.v_cruise_mps * 0.9, propeller_efficiency=0.68)

    # Build Curve objects
    curves: list[ConstraintCurve] = [
        ConstraintCurve(
            id="takeoff",
            label="Takeoff Run",
            is_vertical=False,
            ws_limit_pa=None,
            ws_pa=ws_grid,
            tw=tw_to,
            pw=pw_to,
            color="#E53935",  # Red
        ),
        ConstraintCurve(
            id="climb",
            label="Rate of Climb",
            is_vertical=False,
            ws_limit_pa=None,
            ws_pa=ws_grid,
            tw=tw_clm,
            pw=pw_clm,
            color="#43A047",  # Green
        ),
        ConstraintCurve(
            id="cruise",
            label="Cruise Speed",
            is_vertical=False,
            ws_limit_pa=None,
            ws_pa=ws_grid,
            tw=tw_crs,
            pw=pw_crs,
            color="#1E88E5",  # Blue
        ),
        ConstraintCurve(
            id="turn",
            label="Sustained Turn",
            is_vertical=False,
            ws_limit_pa=ws_turn_limit,
            ws_pa=ws_grid,
            tw=tw_trn,
            pw=pw_trn,
            color="#FB8C00",  # Orange
        ),
        ConstraintCurve(
            id="ceiling",
            label="Service Ceiling",
            is_vertical=False,
            ws_limit_pa=None,
            ws_pa=ws_grid,
            tw=tw_ceil,
            pw=pw_ceil,
            color="#8E24AA",  # Purple
        ),
        ConstraintCurve(
            id="stall",
            label="Stall Limit",
            is_vertical=True,
            ws_limit_pa=ws_stall,
            ws_pa=np.array([ws_stall, ws_stall]),
            tw=np.array([0.0, 2.0]),
            pw=np.array([0.0, 50.0]),
            color="#D81B60",  # Magenta
            line_style="dash",
        ),
        ConstraintCurve(
            id="landing",
            label="Landing Limit",
            is_vertical=True,
            ws_limit_pa=ws_landing,
            ws_pa=np.array([ws_landing, ws_landing]),
            tw=np.array([0.0, 2.0]),
            pw=np.array([0.0, 50.0]),
            color="#00897B",  # Teal
            line_style="dash",
        ),
    ]

    # Combined lower power loading boundary: max(P/W) across all active constraints
    combined_pw = np.maximum.reduce([pw_to, pw_clm, pw_crs, pw_trn, pw_ceil])

    # 3. Automatic Optimum Design Point
    # Aircraft design best practice:
    # Choose highest feasible W/S (minimizes wing area and structural weight)
    # with a 5% margin below the stall or landing limit
    active_limit = min(ws_stall, ws_landing)
    ws_opt = active_limit * 0.95

    # Interpolate required P/W at ws_opt
    pw_opt = float(np.interp(ws_opt, ws_grid, combined_pw))

    return MatchingChartAnalysis(
        mission=mission,
        aero=aero,
        atmosphere=atm,
        ws_grid_pa=ws_grid,
        curves=curves,
        ws_max_stall_pa=ws_stall,
        ws_max_landing_pa=ws_landing,
        combined_min_pw_wn=combined_pw,
        optimum_design_point=(ws_opt, pw_opt),
    )


def solve_sizing_for_mission(
    mission: MissionProfile,
    aero: AeroParameters,
    design_ws_pa: float | None = None,
    design_pw_wn: float | None = None,
) -> tuple[MatchingChartAnalysis, SizingResult]:
    """Perform full matching chart analysis and iterative mass sizing."""
    chart = compute_matching_chart(mission=mission, aero=aero)

    ws_selected = design_ws_pa if design_ws_pa is not None else chart.optimum_design_point[0]
    pw_selected = design_pw_wn if design_pw_wn is not None else chart.optimum_design_point[1]

    sizing = converge_sizing(
        mission=mission,
        aero=aero,
        design_wing_loading_pa=ws_selected,
        design_power_loading_wn=pw_selected,
        atmosphere=chart.atmosphere,
    )

    return chart, sizing


__all__ = [
    "MatchingChartAnalysis",
    "compute_matching_chart",
    "solve_sizing_for_mission",
]
