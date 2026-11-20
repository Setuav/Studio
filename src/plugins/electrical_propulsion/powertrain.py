"""Electrical powertrain resolved from a vehicle's propulsors and battery packs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from plugins.electrical_propulsion.database import get_propeller_entry
from plugins.electrical_propulsion.models.battery import battery_pack
from plugins.electrical_propulsion.models.propulsor import (
    PROPULSOR_TYPE,
    has_motor,
    has_propeller,
)

# pythrust's battery and propulsion solvers import scipy, which slows Studio's
# start; the functions below import them when a powertrain is built or solved.
if TYPE_CHECKING:
    from pythrust.battery import BatteryNetwork, NetworkState
    from pythrust.propulsion import PropulsionUnit
    from pythrust.propulsion.models import OperatingPoint

BATTERY_TYPE = "org.setuav.core:battery"


class PowertrainError(RuntimeError):
    """Raised when the vehicle's powertrain cannot be analysed."""


@dataclass(frozen=True)
class PowertrainMembers:
    """The vehicle's propulsors and the battery packs that feed them."""

    propulsors: tuple[dict[str, Any], ...]
    batteries: tuple[dict[str, Any], ...]


def find_powertrain_members(components: list[dict[str, Any]]) -> PowertrainMembers | None:
    """Return the vehicle's propulsors and batteries, or ``None`` when it has neither."""
    propulsors = tuple(c for c in components if c.get("type") == PROPULSOR_TYPE)
    batteries = tuple(c for c in components if c.get("type") == BATTERY_TYPE)
    if not propulsors and not batteries:
        return None
    return PowertrainMembers(propulsors=propulsors, batteries=batteries)


@dataclass(frozen=True)
class PowertrainPoint:
    """Operating point of every propulsor and of the battery network feeding them.

    Thrust and the battery values are totals; RPM and advance ratio are the mean
    over the propulsors, and the efficiencies are ratios of the summed powers.
    """

    units: tuple[OperatingPoint, ...]
    thrust_n: float
    battery_power_w: float
    battery_current_a: float
    battery_voltage_v: float
    rpm: float
    advance_ratio: float
    propeller_efficiency: float
    motor_efficiency: float
    system_efficiency: float
    feasible: bool


@dataclass(frozen=True)
class Powertrain:
    """Propulsors sharing one bus fed by battery packs connected in parallel.

    Every propulsor runs at the same throttle. The bus voltage sags with the total
    current, and each pack drains with its own share of it.
    """

    network: BatteryNetwork
    network_state: NetworkState
    units: tuple[PropulsionUnit, ...]

    @property
    def state_of_charge(self) -> float:
        """State of charge of the emptiest pack."""
        return min(pack.soc for pack in self.network_state.packs)

    @property
    def open_circuit_voltage_v(self) -> float:
        return self.network.thevenin(self.network_state)[0]

    def discharge_time_s(self, *, power_w: float, final_soc: float) -> float:
        """Time to discharge to ``final_soc`` at constant bus power.

        The discharge ends when the first pack reaches ``final_soc``, or earlier when
        a pack reaches its cut-off voltage or current limit.
        """
        if final_soc >= self.state_of_charge:
            raise PowertrainError(
                f"Final state of charge {final_soc:.0%} is not below the initial "
                f"{self.state_of_charge:.0%}."
            )
        result = self.network.integrate_power_to_soc(
            self.network_state, power_w, final_soc, max_step_s=60.0
        )
        return result.time_s[-1]

    def solve(self, *, rho: float, airspeed_mps: float, throttle: float) -> PowertrainPoint:
        if not 0.0 <= throttle <= 1.0:
            raise ValueError(f"Throttle {throttle:g} is outside 0 to 1.")
        from pythrust.propulsion import BusSolver

        bus = BusSolver().solve(
            self.network,
            self.network_state,
            self.units,
            [throttle] * len(self.units),
            rho=rho,
            airspeed_mps=airspeed_mps,
        )
        units = bus.units
        thrust_power_w = bus.thrust_n * airspeed_mps
        shaft_power_w = sum(unit.shaft_power_w for unit in units)
        motor_power_w = sum(unit.motor_power_w for unit in units)
        return PowertrainPoint(
            units=units,
            thrust_n=bus.thrust_n,
            battery_power_w=bus.power_w,
            battery_current_a=bus.current_a,
            battery_voltage_v=bus.voltage_v,
            rpm=sum(unit.rpm for unit in units) / len(units),
            advance_ratio=sum(unit.advance_ratio for unit in units) / len(units),
            propeller_efficiency=thrust_power_w / shaft_power_w if shaft_power_w > 0.0 else 0.0,
            motor_efficiency=shaft_power_w / motor_power_w if motor_power_w > 0.0 else 0.0,
            system_efficiency=thrust_power_w / bus.power_w if bus.power_w > 0.0 else 0.0,
            # Zero throttle draws nothing but is no operating point.
            feasible=bus.is_feasible and throttle > 0.0,
        )


def build_powertrain(members: PowertrainMembers, *, state_of_charge: float) -> Powertrain:
    """Build the analysable powertrain of the vehicle at ``state_of_charge``."""
    missing = [
        label
        for label, group in (("Battery", members.batteries), ("Propulsor", members.propulsors))
        if not group
    ]
    if missing:
        raise PowertrainError(f"Propulsion analysis requires: {', '.join(missing)}.")
    from pythrust.battery import BatteryNetwork, NetworkState

    try:
        network = BatteryNetwork.parallel(
            *(battery_pack(battery["parameters"]).rate_map() for battery in members.batteries)
        )
    except ValueError as err:
        raise PowertrainError(f"The battery packs cannot share one bus: {err}.") from err
    return Powertrain(
        network=network,
        network_state=NetworkState.uniform(len(network.packs), soc=state_of_charge),
        units=tuple(_unit(propulsor) for propulsor in members.propulsors),
    )


def propulsion_unit(parameters: Mapping[str, Any], label: str) -> PropulsionUnit:
    """Return the PyThrust unit of a propulsor's parameters."""
    if not has_motor(parameters):
        raise PowertrainError(f"Propulsor '{label}' has no motor; pick one from the catalog.")
    if not has_propeller(parameters):
        raise PowertrainError(f"Propulsor '{label}' has no propeller; pick one from the catalog.")
    catalog_id = str(parameters["propeller_catalog_id"])
    entry = get_propeller_entry(catalog_id)
    if entry is None:
        raise PowertrainError(f"Propeller catalog has no data for '{catalog_id}'.")
    from pythrust.propulsion import PropulsionUnit
    from pythrust.propulsion.models import MotorSpec, PropellerSpec

    return PropulsionUnit(
        motor=MotorSpec(
            kv_rpm_per_v=float(parameters["motor_kv"]),
            resistance_ohm=float(parameters["motor_resistance"]),
            no_load_current_a=float(parameters["motor_no_load_current"]),
            current_max_a=float(parameters["motor_max_current"]),
        ),
        propeller=PropellerSpec(
            diameter_m=float(parameters["propeller_diameter"]) / 1000.0,
            pitch_m=float(parameters["propeller_pitch"]) / 1000.0,
            blade_count=int(parameters["propeller_blade_count"]),
        ),
        prop_entry=entry,
    )


def _unit(propulsor: dict[str, Any]) -> PropulsionUnit:
    label = str(propulsor.get("name") or propulsor["id"])
    return propulsion_unit(propulsor["parameters"], label)


__all__ = [
    "BATTERY_TYPE",
    "Powertrain",
    "PowertrainError",
    "PowertrainMembers",
    "PowertrainPoint",
    "build_powertrain",
    "find_powertrain_members",
    "propulsion_unit",
]
