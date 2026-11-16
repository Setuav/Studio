"""Electrical powertrain resolved from a project's propulsion system components."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from pythrust.battery import FixedVoltageBattery
from pythrust.propellers.database import PropellerEntry
from pythrust.propulsion.models import MotorSpec, PropellerSpec, SystemSpec
from pythrust.propulsion.solver import PropulsionSolver

from plugins.electrical_propulsion.database import get_propeller_database

PROPULSION_SYSTEM_TYPE = "org.setuav.core:propulsion-system"
MOTOR_TYPE = "org.setuav.core:motor"
BATTERY_TYPE = "org.setuav.core:battery"
ESC_TYPE = "org.setuav.core:esc"
PROPULSOR_TYPES = frozenset({"org.setuav.core:propeller", "org.setuav.core:rotor"})

BATTERY_DISCHARGE_EFFICIENCY = 0.98


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
    """Battery feeding ``unit_count`` identical ESC-motor-propeller units in parallel.

    The battery is an ideal voltage source, so every unit operates at the same
    point and the totals scale with the unit count.
    """

    motor: MotorSpec
    propeller: PropellerSpec
    propeller_data: PropellerEntry
    battery: FixedVoltageBattery
    unit_system: SystemSpec
    capacity_mah: float
    unit_count: int

    @property
    def current_limit_a(self) -> float:
        """Total battery current at which every motor reaches its current limit."""
        return self.motor.current_max_a * self.unit_count

    def with_battery_voltage(self, voltage_v: float) -> Powertrain:
        return replace(self, battery=replace(self.battery, voltage_v=voltage_v))

    def solve(self, *, rho: float, airspeed_mps: float, throttle: float) -> PowertrainPoint:
        op = PropulsionSolver().solve_operating_point(
            motor=self.motor,
            battery=self.battery,
            system=self.unit_system,
            propeller=self.propeller,
            prop_entry=self.propeller_data,
            rho=rho,
            airspeed_mps=airspeed_mps,
            throttle=min(max(throttle, 0.0), 1.0),
            battery_state=None,
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


def build_powertrain(members: PropulsionSystemMembers) -> Powertrain:
    """Build the analysable powertrain of a propulsion system."""
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
        battery=FixedVoltageBattery(
            voltage_v=_number(battery, "nominal_voltage", "Battery"),
            discharge_efficiency=BATTERY_DISCHARGE_EFFICIENCY,
        ),
        unit_system=SystemSpec(resistance_ohm=esc_resistances.pop() if esc_resistances else 0.0),
        capacity_mah=_number(battery, "capacity", "Battery"),
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
    entry = get_propeller_database().get(catalog_id)
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
