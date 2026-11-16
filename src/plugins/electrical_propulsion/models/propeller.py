"""Propeller and Rotor domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.api import ParameterField
from setuav_studio.model import Component


class PropellerModel(Component):
    """Domain model for Propeller and Rotor (org.setuav.core:propeller / rotor)."""

    COMPONENT_TYPE = "org.setuav.core:propeller"

    diameter = ParameterField(
        key="diameter",
        label="Diameter",
        unit="mm",
        field_type=float,
        default=330.0,
        min_value=10.0,
        max_value=3000.0,
        decimals=1,
        readonly=True,
        tooltip="Propeller overall tip-to-tip diameter in millimeters.",
    )
    pitch: Any = ParameterField(
        key="pitch",
        label="Pitch",
        unit="mm",
        field_type=float,
        default=165.0,
        min_value=5.0,
        max_value=2000.0,
        decimals=1,
        readonly=True,
        tooltip="Geometric pitch advance per revolution in millimeters.",
    )
    blade_count = ParameterField(
        key="blade_count",
        label="Blade Count",
        unit="",
        field_type=int,
        default=2,
        min_value=1,
        max_value=8,
        readonly=True,
        tooltip="Number of propeller blades.",
    )
    hub_diameter = ParameterField(
        key="hub_diameter",
        label="Hub Diameter",
        unit="mm",
        field_type=float,
        default=25.0,
        min_value=0.0,
        max_value=300.0,
        decimals=1,
        readonly=True,
        tooltip="Propeller central hub diameter.",
    )
    collective_pitch = ParameterField(
        key="collective_pitch",
        label="Collective Pitch",
        unit="deg",
        field_type=float,
        default=0.0,
        min_value=-45.0,
        max_value=45.0,
        decimals=1,
        readonly=True,
        tooltip="Collective blade pitch angle for variable-pitch propellers and rotors.",
    )

    @property
    def diameter_m(self) -> float:
        return float(self.diameter) / 1000.0

    @property
    def pitch_m(self) -> float:
        return float(self.pitch) / 1000.0

    @property
    def diameter_in(self) -> float:
        return self.diameter_m / 0.0254

    @property
    def pitch_in(self) -> float:
        return self.pitch_m / 0.0254

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "diameter": self.diameter,
                "pitch": self.pitch,
                "blade_count": self.blade_count,
                "hub_diameter": self.hub_diameter,
                "collective_pitch": self.collective_pitch,
                "diameter_m": self.diameter_m,
                "pitch_m": self.pitch_m,
                "diameter_in": self.diameter_in,
                "pitch_in": self.pitch_in,
            }
        )
        return props
