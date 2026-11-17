"""Propulsor domain entity model: an electric motor with the propeller on its shaft."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from setuav_studio.api import ParameterField
from setuav_studio.model import Component

PROPULSOR_TYPE = "org.setuav.core:propulsor"

# Masses summed into the propulsor's component mass.
PROPULSOR_MASS_KEYS = ("motor_mass", "propeller_mass")


def propulsor_mass(parameters: Mapping[str, Any]) -> float:
    """Return the mass in grams of the propulsor's motor and propeller entered so far."""
    return sum(float(parameters[key]) for key in PROPULSOR_MASS_KEYS if parameters[key] is not None)


def has_motor(parameters: Mapping[str, Any]) -> bool:
    """Whether a motor has been picked from the catalog."""
    return parameters["motor_model"] is not None


def has_propeller(parameters: Mapping[str, Any]) -> bool:
    """Whether a propeller has been picked from the catalog."""
    return parameters["propeller_catalog_id"] is not None


class PropulsorModel(Component):
    """Domain model for Propulsor (org.setuav.core:propulsor).

    A propulsor is one electric motor and the propeller on its shaft, each picked
    from the PyThrust catalogs. A new propulsor has neither; until they are picked
    their parameters are empty. The component mass is stored and kept equal to the
    motor and propeller masses.
    """

    COMPONENT_TYPE = PROPULSOR_TYPE

    motor_manufacturer = ParameterField(
        key="motor_manufacturer", label="Manufacturer", field_type=str, default=None
    )
    motor_model = ParameterField(key="motor_model", label="Model", field_type=str, default=None)
    motor_kv = ParameterField(
        key="motor_kv",
        label="Velocity Constant (KV)",
        unit="RPM/V",
        field_type=float,
        default=None,
        min_value=10.0,
        max_value=20000.0,
        decimals=0,
        tooltip="Motor velocity constant in revolutions per minute per volt.",
    )
    motor_resistance = ParameterField(
        key="motor_resistance",
        label="Winding Resistance (Rm)",
        unit="Ω",
        quantity="resistance",
        field_type=float,
        default=None,
        min_value=0.0001,
        max_value=10.0,
        decimals=4,
        tooltip="Phase-to-phase winding resistance.",
    )
    motor_no_load_current = ParameterField(
        key="motor_no_load_current",
        label="No-Load Current (I0)",
        unit="A",
        quantity="current",
        field_type=float,
        default=None,
        min_value=0.0,
        max_value=50.0,
        decimals=2,
        tooltip="No-load current at the reference test voltage.",
    )
    motor_max_current = ParameterField(
        key="motor_max_current",
        label="Max Current",
        unit="A",
        quantity="current",
        field_type=float,
        default=None,
        min_value=0.1,
        max_value=1000.0,
        decimals=1,
        tooltip="Maximum continuous motor current.",
    )
    motor_mass = ParameterField(
        key="motor_mass",
        label="Mass",
        unit="g",
        quantity="mass",
        field_type=float,
        default=None,
        min_value=0.0,
        max_value=1e5,
        decimals=1,
    )
    propeller_catalog_id = ParameterField(
        key="propeller_catalog_id",
        label="Catalog Entry",
        field_type=str,
        default=None,
        tooltip="PyThrust catalog entry of the propeller's thrust and power data.",
    )
    propeller_diameter = ParameterField(
        key="propeller_diameter",
        label="Diameter",
        unit="mm",
        quantity="length",
        field_type=float,
        default=None,
        min_value=1.0,
        max_value=1e4,
        decimals=1,
    )
    propeller_pitch = ParameterField(
        key="propeller_pitch",
        label="Pitch",
        unit="mm",
        quantity="length",
        field_type=float,
        default=None,
        min_value=0.0,
        max_value=1e4,
        decimals=1,
    )
    propeller_blade_count = ParameterField(
        key="propeller_blade_count",
        label="Blades",
        field_type=int,
        default=None,
        min_value=1,
        max_value=12,
        decimals=0,
    )
    propeller_mass = ParameterField(
        key="propeller_mass",
        label="Mass",
        unit="g",
        quantity="mass",
        field_type=float,
        default=None,
        min_value=0.0,
        max_value=1e5,
        decimals=1,
        tooltip="The catalog has no propeller masses; enter the propeller's own.",
    )

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        """Parameter set of a new propulsor, with no motor or propeller picked."""
        return {field.key: field.default for field in cls.get_scalar_fields()}
