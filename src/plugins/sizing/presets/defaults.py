"""Built-in aircraft design presets for typical UAV mission classes."""

from __future__ import annotations

from dataclasses import dataclass

from plugins.sizing.engine.aerodynamics import AeroParameters
from plugins.sizing.engine.battery import BatteryParameters
from plugins.sizing.engine.weight import MissionProfile


@dataclass(frozen=True)
class SizingPreset:
    """Predefined sizing configuration for a vehicle class."""

    id: str
    name: str
    description: str
    mission: MissionProfile
    aero: AeroParameters
    battery: BatteryParameters


SURVEILLANCE_PRESET = SizingPreset(
    id="surveillance",
    name="Surveillance / Mapping UAV",
    description="Long endurance, efficient high-aspect-ratio electric reconnaissance UAV.",
    mission=MissionProfile(
        payload_mass_kg=0.5,
        range_km=50.0,
        endurance_min=60.0,
        v_cruise_mps=18.0,
        v_stall_mps=10.5,
        v_climb_mps=14.0,
        roc_mps=3.0,
        cruise_altitude_m=600.0,
        ground_roll_takeoff_m=20.0,
        ground_roll_landing_m=25.0,
        turn_load_factor_n=1.414,
        avionics_mass_kg=0.25,
    ),
    aero=AeroParameters.create(
        cd0=0.024,
        aspect_ratio=12.0,
        cl_max_clean=1.40,
        cl_max_takeoff=1.60,
        cl_max_landing=1.80,
    ),
    battery=BatteryParameters(
        specific_energy_wh_kg=200.0,
        max_dod=0.80,
        powertrain_efficiency=0.86,
    ),
)

CARGO_PRESET = SizingPreset(
    id="cargo",
    name="Cargo / Delivery UAV",
    description="Medium-lift utility UAV focused on carrying payload over moderate ranges.",
    mission=MissionProfile(
        payload_mass_kg=2.0,
        range_km=35.0,
        endurance_min=35.0,
        v_cruise_mps=22.0,
        v_stall_mps=13.0,
        v_climb_mps=16.0,
        roc_mps=4.0,
        cruise_altitude_m=500.0,
        ground_roll_takeoff_m=35.0,
        ground_roll_landing_m=40.0,
        turn_load_factor_n=1.414,
        avionics_mass_kg=0.35,
    ),
    aero=AeroParameters.create(
        cd0=0.028,
        aspect_ratio=9.0,
        cl_max_clean=1.45,
        cl_max_takeoff=1.65,
        cl_max_landing=1.85,
    ),
    battery=BatteryParameters(
        specific_energy_wh_kg=185.0,
        max_dod=0.80,
        powertrain_efficiency=0.84,
    ),
)

HIGH_SPEED_PRESET = SizingPreset(
    id="high_speed",
    name="High-Speed / Dash UAV",
    description="Fast fixed-wing drone designed for rapid area coverage and high dash speeds.",
    mission=MissionProfile(
        payload_mass_kg=0.3,
        range_km=40.0,
        endurance_min=25.0,
        v_cruise_mps=30.0,
        v_stall_mps=15.0,
        v_climb_mps=20.0,
        roc_mps=6.0,
        cruise_altitude_m=800.0,
        ground_roll_takeoff_m=45.0,
        ground_roll_landing_m=50.0,
        turn_load_factor_n=2.0,
        avionics_mass_kg=0.20,
    ),
    aero=AeroParameters.create(
        cd0=0.022,
        aspect_ratio=7.0,
        cl_max_clean=1.25,
        cl_max_takeoff=1.45,
        cl_max_landing=1.60,
    ),
    battery=BatteryParameters(
        specific_energy_wh_kg=170.0,
        max_dod=0.80,
        powertrain_efficiency=0.85,
    ),
)

PRESETS: dict[str, SizingPreset] = {
    SURVEILLANCE_PRESET.id: SURVEILLANCE_PRESET,
    CARGO_PRESET.id: CARGO_PRESET,
    HIGH_SPEED_PRESET.id: HIGH_SPEED_PRESET,
}

__all__ = [
    "CARGO_PRESET",
    "HIGH_SPEED_PRESET",
    "PRESETS",
    "SURVEILLANCE_PRESET",
    "SizingPreset",
]
