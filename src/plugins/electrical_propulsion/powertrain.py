"""Electrical powertrain resolved from a project's propulsion system components."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cached_property
from typing import Any

from pythrust.battery import BatteryState, RateMapBattery
from pythrust.propellers.database import PropellerEntry
from pythrust.propulsion.models import MotorSpec, PropellerSpec, SystemSpec
from pythrust.propulsion.solver import PropulsionSolver

from plugins.electrical_propulsion.database import get_propeller_entry
from plugins.electrical_propulsion.models.battery import battery_pack

PROPULSION_SYSTEM_TYPE = "org.setuav.core:propulsion-system"
MOTOR_TYPE = "org.setuav.core:motor"
BATTERY_TYPE = "org.setuav.core:battery"
ESC_TYPE = "org.setuav.core:esc"
PROPULSOR_TYPES = frozenset({"org.setuav.core:propeller", "org.setuav.core:rotor"})


class PowertrainError(RuntimeError):
    """Raised when the project's propulsion system cannot be analysed."""


@dataclass(frozen=True)
class PropulsionSystemMembers:
    """Components of one propulsion system.

    Batteries, ESCs and motors are children of the system; propulsors are children
    of a motor.
    """

    system: dict[str, Any]
    batteries: tuple[dict[str, Any], ...]
    escs: tuple[dict[str, Any], ...]
    motors: tuple[dict[str, Any], ...]
    propulsors: tuple[dict[str, Any], ...]


def propulsion_system_members(
    system: dict[str, Any], components: list[dict[str, Any]]
) -> PropulsionSystemMembers:
    """Return the components that belong to ``system``."""
    system_id = system.get("id")
    children = [c for c in components if c.get("parent") == system_id]
    motors = tuple(c for c in children if c.get("type") == MOTOR_TYPE)
    motor_ids = {m.get("id") for m in motors}
    return PropulsionSystemMembers(
        system=system,
        batteries=tuple(c for c in children if c.get("type") == BATTERY_TYPE),
        escs=tuple(c for c in children if c.get("type") == ESC_TYPE),
        motors=motors,
        propulsors=tuple(
            c
            for c in components
            if c.get("type") in PROPULSOR_TYPES and c.get("parent") in motor_ids
        ),
    )


def find_propulsion_system(components: list[dict[str, Any]]) -> PropulsionSystemMembers | None:
    """Return the project's propulsion system, or ``None`` when it has none."""
    systems = [c for c in components if c.get("type") == PROPULSION_SYSTEM_TYPE]
    if not systems:
        return None
    if len(systems) > 1:
        raise PowertrainError("Project has more than one propulsion system.")
    return propulsion_system_members(systems[0], components)


@dataclass(frozen=True)
class PowertrainPoint:
    """Operating point of the whole powertrain.

    Thrust, battery power and battery current are totals over all motor units;
    RPM, advance ratio and efficiencies are those of each (identical) unit.
    """

    rpm: float
    thrust_n: float
    battery_power_w: float
    battery_current_a: float
    battery_voltage_v: float
    advance_ratio: float
    propeller_efficiency: float
    motor_efficiency: float
    system_efficiency: float
    feasible: bool


@dataclass(frozen=True)
class Powertrain:
    """Battery pack feeding ``unit_count`` identical ESC-motor-propeller units in parallel.

    The pack is a rate-map battery at ``battery_state``: its terminal voltage sags
    with the total current of all units. Every unit draws the same current, so one
    unit sees the pack with its resistance and current limit scaled by the unit
    count, and the totals scale with the unit count.
    """

    motor: MotorSpec
    propeller: PropellerSpec
    propeller_data: PropellerEntry
    battery: RateMapBattery
    battery_state: BatteryState
    unit_system: SystemSpec
    unit_count: int

    @property
    def current_limit_a(self) -> float:
        """Total battery current allowed by the motors and the pack."""
        return min(
            self.motor.current_max_a * self.unit_count,
            self.battery.max_current_a * self.battery.parallel,
        )

    @cached_property
    def _unit_battery(self) -> RateMapBattery:
        n = self.unit_count
        return replace(
            self.battery,
            resistance_factor=self.battery.resistance_factor * n,
            max_current_a=self.battery.max_current_a / n,
        )

    def with_state_of_charge(self, soc: float) -> Powertrain:
        return replace(self, battery_state=BatteryState(soc=soc))

    def discharge_time_s(self, *, power_w: float, final_soc: float) -> float:
        """Time to discharge from ``battery_state`` to ``final_soc`` at constant pack power.

        The discharge ends earlier when the pack reaches its cut-off voltage or current
        limit.
        """
        if final_soc >= self.battery_state.soc:
            raise PowertrainError(
                f"Final state of charge {final_soc:.0%} is not below the initial "
                f"{self.battery_state.soc:.0%}."
            )
        result = self.battery.integrate_power_to_dod(
            state=self.battery_state,
            power_w=power_w,
            dod_final=1.0 - final_soc,
            max_step_s=60.0,
        )
        return result.time_s[-1]

    def solve(self, *, rho: float, airspeed_mps: float, throttle: float) -> PowertrainPoint:
        op = PropulsionSolver().solve_operating_point(
            motor=self.motor,
            battery=self._unit_battery,
            system=self.unit_system,
            propeller=self.propeller,
            prop_entry=self.propeller_data,
            rho=rho,
            airspeed_mps=airspeed_mps,
            throttle=min(max(throttle, 0.0), 1.0),
            battery_state=self.battery_state,
        )
        n = self.unit_count
        return PowertrainPoint(
            rpm=op.rpm,
            thrust_n=max(op.thrust_n, 0.0) * n,
            battery_power_w=max(op.battery_power_w, 0.0) * n,
            battery_current_a=max(op.battery_current_a, 0.0) * n,
            battery_voltage_v=op.battery_voltage_v,
            advance_ratio=max(op.advance_ratio, 0.0),
            propeller_efficiency=min(max(op.propeller_efficiency, 0.0), 1.0),
            motor_efficiency=min(max(op.motor_efficiency, 0.0), 1.0),
            system_efficiency=min(max(op.system_efficiency, 0.0), 1.0),
            feasible=op.is_feasible,
        )


def build_powertrain(members: PropulsionSystemMembers, *, state_of_charge: float) -> Powertrain:
    """Build the analysable powertrain of a propulsion system at ``state_of_charge``."""
    missing = [
        label
        for label, group in (("Battery", members.batteries), ("Electric Motor", members.motors))
        if not group
    ]
    if missing:
        raise PowertrainError(f"Propulsion analysis requires: {', '.join(missing)}.")
    if len(members.batteries) != 1:
        raise PowertrainError("Propulsion analysis supports a single battery.")
    (battery,) = members.batteries

    units = [(motor, _motor_propulsor(motor, members.propulsors)) for motor in members.motors]
    motor_specs = {_motor_spec(motor) for motor, _ in units}
    propeller_ids = {_catalog_id(propulsor) for _, propulsor in units}
    if len(motor_specs) > 1 or len(propeller_ids) > 1:
        raise PowertrainError("Propulsion analysis requires identical motor and propeller units.")

    esc_resistances = {_number(esc, "resistance", "ESC") for esc in members.escs}
    if len(esc_resistances) > 1:
        raise PowertrainError("Propulsion analysis requires identical ESCs.")

    propulsor = units[0][1]
    return Powertrain(
        motor=motor_specs.pop(),
        propeller=PropellerSpec(
            diameter_m=_number(propulsor, "diameter", "Propeller") / 1000.0,
            pitch_m=_number(propulsor, "pitch", "Propeller") / 1000.0,
            blade_count=int(_number(propulsor, "blade_count", "Propeller")),
        ),
        propeller_data=_propeller_data(propulsor),
        battery=battery_pack(battery["parameters"]).rate_map(),
        battery_state=BatteryState(soc=state_of_charge),
        unit_system=SystemSpec(resistance_ohm=esc_resistances.pop() if esc_resistances else 0.0),
        unit_count=len(units),
    )


def _motor_propulsor(
    motor: dict[str, Any], propulsors: tuple[dict[str, Any], ...]
) -> dict[str, Any]:
    mounted = [p for p in propulsors if p.get("parent") == motor.get("id")]
    if len(mounted) != 1:
        raise PowertrainError(f"Motor '{_label(motor)}' must carry exactly one propeller.")
    return mounted[0]


def _motor_spec(motor: dict[str, Any]) -> MotorSpec:
    return MotorSpec(
        kv_rpm_per_v=_number(motor, "kv", "Motor"),
        resistance_ohm=_number(motor, "resistance", "Motor"),
        no_load_current_a=_number(motor, "no_load_current", "Motor"),
        current_max_a=_number(motor, "max_current", "Motor"),
    )


def _catalog_id(propulsor: dict[str, Any]) -> str:
    catalog_id = str(propulsor.get("catalog_id") or "")
    if not catalog_id:
        raise PowertrainError(
            f"Propeller '{_label(propulsor)}' is not linked to catalog data; "
            "select it from the propeller catalog."
        )
    return catalog_id


def _propeller_data(propulsor: dict[str, Any]) -> PropellerEntry:
    catalog_id = _catalog_id(propulsor)
    entry = get_propeller_entry(catalog_id)
    if entry is None:
        raise PowertrainError(f"Propeller catalog has no data for '{catalog_id}'.")
    return entry


def _number(component: dict[str, Any], key: str, kind: str) -> float:
    parameters = component.get("parameters")
    value = parameters.get(key) if isinstance(parameters, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PowertrainError(f"{kind} '{_label(component)}' has no numeric '{key}' parameter.")
    return float(value)


def _label(component: dict[str, Any]) -> str:
    return str(component.get("name") or component.get("id") or "")


__all__ = [
    "Powertrain",
    "PowertrainError",
    "PowertrainPoint",
    "PropulsionSystemMembers",
    "build_powertrain",
    "find_propulsion_system",
    "propulsion_system_members",
]
