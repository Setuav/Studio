"""Electric Motor domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.api import ParameterField
from setuav_studio.model import Component


class MotorModel(Component):
    """Domain model for Electric Motor (org.setuav.core:motor)."""

    COMPONENT_TYPE = "org.setuav.core:motor"

    kv = ParameterField(
        key="kv",
        label="Velocity Constant (KV)",
        unit="RPM/V",
        field_type=float,
        default=900.0,
        min_value=10.0,
        max_value=20000.0,
        decimals=0,
        readonly=True,
        tooltip="Motor velocity constant in revolutions per minute per volt.",
    )
    resistance = ParameterField(
        key="resistance",
        label="Internal Resistance (Rm)",
        unit="Ω",
        field_type=float,
        default=0.055,
        min_value=0.0001,
        max_value=10.0,
        decimals=4,
        readonly=True,
        tooltip="Phase-to-phase internal winding resistance.",
    )
    no_load_current = ParameterField(
        key="no_load_current",
        label="No-Load Current (I0)",
        unit="A",
        field_type=float,
        default=1.1,
        min_value=0.01,
        max_value=50.0,
        decimals=2,
        readonly=True,
        tooltip="Idle no-load current at reference test voltage.",
    )
    max_current = ParameterField(
        key="max_current",
        label="Max Current",
        unit="A",
        field_type=float,
        default=40.0,
        min_value=0.1,
        max_value=1000.0,
        decimals=1,
        readonly=True,
        tooltip="Maximum continuous/peak current rating.",
    )
    max_power = ParameterField(
        key="max_power",
        label="Max Power",
        unit="W",
        field_type=float,
        default=800.0,
        min_value=1.0,
        max_value=100000.0,
        decimals=0,
        readonly=True,
        tooltip="Maximum electrical power handling limit.",
    )

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "kv": self.kv,
                "resistance": self.resistance,
                "no_load_current": self.no_load_current,
                "max_current": self.max_current,
                "max_power": self.max_power,
            }
        )
        return props
