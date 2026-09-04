"""Battery pack sizing and energy estimation for electric UAVs.

References:
- Traub, L.W., "Range and Endurance Estimates for Battery-Powered Aircraft",
  Journal of Aircraft, Vol. 48, No. 2, 2011.
- Budinger, M. et al., "Scaling laws and similarity models for the preliminary
  design of multirotor drones", Aerospace Science and Technology, 2020.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatteryParameters:
    """Technological parameters of the battery pack."""

    specific_energy_wh_kg: float = 180.0  # Wh/kg (Typical LiPo ~150-190, Li-Ion ~220-260)
    max_dod: float = 0.80  # Maximum depth of discharge (80% usable)
    powertrain_efficiency: float = 0.85  # Combined ESC & motor electrical efficiency (eta_esc * eta_motor)
    nominal_cell_voltage_v: float = 3.7  # LiPo nominal cell voltage (V)
    max_c_rating: float = 25.0  # Continuous discharge C-rate rating


@dataclass(frozen=True)
class BatterySizingResult:
    """Estimated battery pack dimensions, mass, and discharge characteristics."""

    energy_wh: float  # Total pack nominal energy capacity (Wh)
    usable_energy_wh: float  # Usable energy within max DoD limit (Wh)
    mass_kg: float  # Total battery pack mass (kg)
    nominal_voltage_v: float  # Pack nominal voltage (V)
    cell_count_s: int  # Series cell count (e.g., 4S, 6S)
    capacity_mah: float  # Pack capacity in milliampere-hours (mAh)
    max_continuous_current_a: float  # Max current during peak power draw (A)
    discharge_c_rate: float  # Effective C-rate during peak power
    is_c_rate_feasible: bool  # True if discharge C-rate is within max_c_rating


def size_battery_pack(
    required_mission_energy_wh: float,
    max_power_watts: float,
    params: BatteryParameters | None = None,
    target_voltage_v: float | None = None,
) -> BatterySizingResult:
    """Size a battery pack given mission energy consumption and peak power requirement.

    Parameters:
    - required_mission_energy_wh: Net electrical energy required for mission (Wh).
    - max_power_watts: Maximum mechanical shaft power required (W).
    - params: BatteryParameters specification.
    - target_voltage_v: Optional fixed voltage; if None, automatically estimated from power.
    """
    p = params or BatteryParameters()

    # Total nominal energy needed accounting for max DoD
    usable_energy = max(float(required_mission_energy_wh), 0.1)
    total_energy_wh = usable_energy / max(p.max_dod, 0.1)

    # Battery mass from specific energy
    mass_kg = total_energy_wh / max(p.specific_energy_wh_kg, 10.0)

    # Automatic voltage selection if not specified
    # Rule of thumb for electric UAVs:
    # < 200W: 3S (11.1V), 200-500W: 4S (14.8V), 500-1200W: 6S (22.2V), >1200W: 12S (44.4V)
    if target_voltage_v is not None and target_voltage_v > 0.0:
        volts = float(target_voltage_v)
        s_count = max(1, round(volts / p.nominal_cell_voltage_v))
    else:
        if max_power_watts < 250.0:
            s_count = 3
        elif max_power_watts < 600.0:
            s_count = 4
        elif max_power_watts < 1500.0:
            s_count = 6
        elif max_power_watts < 3000.0:
            s_count = 8
        else:
            s_count = 12
        volts = s_count * p.nominal_cell_voltage_v

    # Capacity calculation: C = E / V
    capacity_ah = total_energy_wh / volts
    capacity_mah = capacity_ah * 1000.0

    # Max current during peak power: I = P_elec / V = (P_mech / eta) / V
    p_elec_max = max(float(max_power_watts), 1.0) / max(p.powertrain_efficiency, 0.1)
    i_max = p_elec_max / volts

    # Discharge C-rate: C = I_max / C_ah
    c_rate = i_max / max(capacity_ah, 1e-4)
    c_feasible = c_rate <= p.max_c_rating

    # If C-rate exceeds limit, the pack must be upsized for power (C-rate bound)
    if not c_feasible:
        # Re-size capacity to meet C-rate: C_min = I_max / C_max
        capacity_ah = i_max / p.max_c_rating
        capacity_mah = capacity_ah * 1000.0
        total_energy_wh = capacity_ah * volts
        usable_energy = total_energy_wh * p.max_dod
        mass_kg = total_energy_wh / p.specific_energy_wh_kg
        c_rate = p.max_c_rating
        c_feasible = True

    return BatterySizingResult(
        energy_wh=total_energy_wh,
        usable_energy_wh=usable_energy,
        mass_kg=mass_kg,
        nominal_voltage_v=volts,
        cell_count_s=s_count,
        capacity_mah=capacity_mah,
        max_continuous_current_a=i_max,
        discharge_c_rate=c_rate,
        is_c_rate_feasible=c_feasible,
    )


__all__ = [
    "BatteryParameters",
    "BatterySizingResult",
    "size_battery_pack",
]
