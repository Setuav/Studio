"""Electronic Speed Controller (ESC) domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.api import ParameterField
from setuav_studio.model import Component


class ESCModel(Component):
    """Domain model for Electronic Speed Controller (org.setuav.core:esc)."""

    COMPONENT_TYPE = "org.setuav.core:esc"

    continuous_current = ParameterField(
        key="continuous_current",
        label="Continuous Current",
        unit="A",
        field_type=float,
        default=50.0,
        min_value=1.0,
        max_value=500.0,
        decimals=1,
        tooltip="Rated continuous electrical current limit.",
    )
    max_current = ParameterField(
        key="max_current",
        label="Peak / Burst Current",
        unit="A",
        field_type=float,
        default=60.0,
        min_value=1.0,
        max_value=800.0,
        decimals=1,
        tooltip="Short duration peak/burst current rating.",
    )
    max_voltage = ParameterField(
        key="max_voltage",
        label="Max Input Voltage",
        unit="V",
        field_type=float,
        default=25.2,
        min_value=3.0,
        max_value=120.0,
        decimals=1,
        tooltip="Maximum allowable battery input voltage.",
    )
    resistance = ParameterField(
        key="resistance",
        label="Internal Resistance",
        unit="Ω",
        field_type=float,
        default=0.004,
        min_value=0.0001,
        max_value=1.0,
        decimals=4,
        tooltip="Lumped MOSFET and lead wire electrical resistance.",
    )

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "continuous_current": self.continuous_current,
                "max_current": self.max_current,
                "max_voltage": self.max_voltage,
                "resistance": self.resistance,
            }
        )
        return props
