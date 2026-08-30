"""Propeller and Rotor domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.component_model import BaseComponentModel


class PropellerModel(BaseComponentModel):
    """Domain model for Propeller / Rotor."""

    @property
    def diameter(self) -> float:
        return float(self.parameters.get("diameter", 0.0))

    @property
    def pitch(self) -> float:
        return float(self.parameters.get("pitch", 0.0))

    @property
    def blade_count(self) -> int:
        return int(self.parameters.get("blade_count", 2))

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update({
            "diameter": self.diameter,
            "pitch": self.pitch,
            "blade_count": self.blade_count,
        })
        return props
