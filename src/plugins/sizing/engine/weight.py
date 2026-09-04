"""Weight estimation and iterative MTOW convergence loop for electric UAVs.

References:
- Noth, A., "Design of Solar Powered Airplanes for Continuous Flight", ETH Zurich PhD Thesis, 2008.
- Raymer, D.P., "Aircraft Design: A Conceptual Approach", 7th Ed., Ch. 3 & 15.
- Traub, L.W., "Range and Endurance Estimates for Battery-Powered Aircraft", 2011.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from setuav_studio.model.atmosphere import G0, Atmosphere

from .aerodynamics import AeroParameters
from .battery import BatteryParameters, BatterySizingResult, size_battery_pack


@dataclass(frozen=True)
class MissionProfile:
    """Design mission requirements for aircraft sizing."""

    payload_mass_kg: float = 0.5  # Useful payload mass (cameras, sensors, cargo)
    range_km: float = 40.0  # Required cruise range (km)
    endurance_min: float = 45.0  # Required flight endurance (minutes)
    v_cruise_mps: float = 18.0  # Nominal cruise airspeed (m/s)
    v_stall_mps: float = 11.0  # Maximum acceptable stall speed (m/s)
    v_climb_mps: float = 14.0  # Airspeed during climb phase (m/s)
    roc_mps: float = 3.5  # Required rate of climb (m/s)
    cruise_altitude_m: float = 500.0  # Design cruise altitude above sea level (m)
    ground_roll_takeoff_m: float = 25.0  # Max allowable takeoff ground roll distance (m)
    ground_roll_landing_m: float = 30.0  # Max allowable landing roll distance (m)
    turn_load_factor_n: float = 1.414  # Sustained turn load factor (45 deg bank = 1.414)
    avionics_mass_kg: float = 0.25  # Flight controller, GPS, receiver, telemetry


@dataclass(frozen=True)
class WeightBreakdown:
    """Detailed mass breakdown of the sized UAV."""

    mtow_kg: float  # Maximum Takeoff Weight (kg)
    empty_mass_kg: float  # Total empty mass excluding payload and battery (kg)
    payload_mass_kg: float  # Payload mass (kg)
    battery_mass_kg: float  # Battery pack mass (kg)
    airframe_mass_kg: float  # Structural wing, fuselage, and tail mass (kg)
    propulsion_dry_mass_kg: float  # Motor, ESC, propeller, wiring mass (kg)
    avionics_mass_kg: float  # Electronics mass (kg)

    # Fractions
    payload_fraction: float
    battery_fraction: float
    structural_fraction: float
    propulsion_fraction: float


@dataclass(frozen=True)
class SizingResult:
    """Complete preliminary sizing solution."""

    weights: WeightBreakdown
    battery: BatterySizingResult
    wing_area_m2: float
    wingspan_m: float
    mean_chord_m: float
    aspect_ratio: float
    wing_loading_pa: float
    power_loading_wn: float
    max_shaft_power_w: float
    cruise_shaft_power_w: float
    max_lift_to_drag: float
    cruise_lift_to_drag: float
    cruise_lift_coeff: float
    converged: bool
    iterations: int


def estimate_airframe_mass_noth(wing_area_m2: float, aspect_ratio: float) -> float:
    """Estimate structural airframe mass (kg) using Andre Noth's UAV correlation.

    W_af = 5.58 * S^1.59 * AR^0.71  [Newtons]
    m_af = W_af / g_0  [kg]

    Reference: Noth, A. (ETH Zurich, 2008), validated on >400 small UAVs.
    """
    s = max(float(wing_area_m2), 0.01)
    ar = max(float(aspect_ratio), 2.0)
    w_af_n = 5.58 * (s**1.59) * (ar**0.71)
    return max(w_af_n / G0, 0.05)


def estimate_propulsion_mass(max_power_watts: float) -> float:
    """Estimate dry powertrain mass (motor, ESC, propeller, wiring).

    Modern brushless UAV powertrains provide ~2000-2500 W/kg continuous.
    """
    p = max(float(max_power_watts), 1.0)
    return p / 2200.0


def converge_sizing(
    mission: MissionProfile,
    aero: AeroParameters,
    design_wing_loading_pa: float,
    design_power_loading_wn: float,
    atmosphere: Atmosphere | None = None,
    battery_params: BatteryParameters | None = None,
    propeller_efficiency_cruise: float = 0.80,
    max_iterations: int = 50,
    tolerance: float = 1e-4,
) -> SizingResult:
    """Iterative fixed-point mass convergence for preliminary UAV sizing.

    Couples aerodynamic drag at design W/S and P/W with mission energy consumption
    to converge MTOW, wing dimensions, battery pack, and powertrain.
    """
    atm = atmosphere or Atmosphere.isa(mission.cruise_altitude_m)
    bat_p = battery_params or BatteryParameters()
    eta_prop = max(float(propeller_efficiency_cruise), 0.1)

    ws = max(float(design_wing_loading_pa), 10.0)
    pw = max(float(design_power_loading_wn), 0.1)

    # Initial MTOW guess (assuming ~35% battery, ~35% airframe+avionics, ~30% payload)
    mtow = (mission.payload_mass_kg + mission.avionics_mass_kg) / 0.30

    converged = False
    s_ref = (mtow * G0) / ws
    p_max = pw * (mtow * G0)
    p_cruise = p_max * 0.4
    cl_cruise = 0.5
    ld_cruise = 12.0
    bat_res = size_battery_pack(50.0, p_max, bat_p)
    m_airframe = 0.5
    completed_iterations = 0

    for step in range(1, max_iterations + 1):
        completed_iterations = step
        # 1. Wing reference area from wing loading: S = W / (W/S)
        s_ref = (mtow * G0) / ws

        # 2. Cruise aerodynamics
        # Lift coefficient in cruise: CL = (W/S) / q_cruise
        q_cruise = atm.dynamic_pressure(mission.v_cruise_mps)
        cl_cruise = ws / max(q_cruise, 1.0)
        cd_cruise = aero.cd(cl_cruise)
        ld_cruise = cl_cruise / max(cd_cruise, 1e-4)

        # 3. Cruise thrust & mechanical shaft power
        # T_cruise = W / (L/D)
        thrust_cruise_n = (mtow * G0) / max(ld_cruise, 1.0)
        p_cruise = (thrust_cruise_n * mission.v_cruise_mps) / eta_prop

        # 4. Maximum power (from design P/W constraint point)
        p_max = pw * (mtow * G0)

        # 5. Mission flight duration and energy consumed
        # Time required to fulfill range or endurance (whichever is larger)
        time_from_range_s = (mission.range_km * 1000.0) / max(mission.v_cruise_mps, 1.0)
        time_from_endurance_s = mission.endurance_min * 60.0
        t_cruise_s = max(time_from_range_s, time_from_endurance_s)

        # Climb energy
        h_climb = max(mission.cruise_altitude_m, 100.0)
        t_climb_s = h_climb / max(mission.roc_mps, 0.5)
        # Power in climb is roughly 80-90% of max power
        p_climb = p_max * 0.85
        climb_energy_wh = (p_climb * (t_climb_s / 3600.0)) / bat_p.powertrain_efficiency

        cruise_energy_wh = (p_cruise * (t_cruise_s / 3600.0)) / bat_p.powertrain_efficiency
        total_mission_energy_wh = climb_energy_wh + cruise_energy_wh

        # 6. Battery sizing
        bat_res = size_battery_pack(
            required_mission_energy_wh=total_mission_energy_wh,
            max_power_watts=p_max,
            params=bat_p,
        )

        # 7. Structural and propulsion mass build-up
        m_airframe = estimate_airframe_mass_noth(s_ref, aero.aspect_ratio)
        m_prop = estimate_propulsion_mass(p_max)

        # 8. New MTOW sum
        mtow_new = (
            mission.payload_mass_kg
            + mission.avionics_mass_kg
            + m_airframe
            + m_prop
            + bat_res.mass_kg
        )

        # 9. Convergence check
        rel_diff = abs(mtow_new - mtow) / max(mtow, 0.01)
        if rel_diff < tolerance:
            mtow = mtow_new
            converged = True
            break

        # Under-relaxation for stable numerical convergence
        mtow = 0.5 * mtow + 0.5 * mtow_new

    # Geometry derived metrics
    wingspan_m = math.sqrt(aero.aspect_ratio * s_ref)
    mean_chord_m = s_ref / max(wingspan_m, 0.01)

    empty_mass_kg = m_airframe + m_prop + mission.avionics_mass_kg

    breakdown = WeightBreakdown(
        mtow_kg=mtow,
        empty_mass_kg=empty_mass_kg,
        payload_mass_kg=mission.payload_mass_kg,
        battery_mass_kg=bat_res.mass_kg,
        airframe_mass_kg=m_airframe,
        propulsion_dry_mass_kg=m_prop,
        avionics_mass_kg=mission.avionics_mass_kg,
        payload_fraction=mission.payload_mass_kg / mtow,
        battery_fraction=bat_res.mass_kg / mtow,
        structural_fraction=m_airframe / mtow,
        propulsion_fraction=m_prop / mtow,
    )

    return SizingResult(
        weights=breakdown,
        battery=bat_res,
        wing_area_m2=s_ref,
        wingspan_m=wingspan_m,
        mean_chord_m=mean_chord_m,
        aspect_ratio=aero.aspect_ratio,
        wing_loading_pa=ws,
        power_loading_wn=pw,
        max_shaft_power_w=p_max,
        cruise_shaft_power_w=p_cruise,
        max_lift_to_drag=aero.max_lift_to_drag_ratio,
        cruise_lift_to_drag=ld_cruise,
        cruise_lift_coeff=cl_cruise,
        converged=converged,
        iterations=completed_iterations,
    )


__all__ = [
    "MissionProfile",
    "SizingResult",
    "WeightBreakdown",
    "converge_sizing",
    "estimate_airframe_mass_noth",
    "estimate_propulsion_mass",
]
