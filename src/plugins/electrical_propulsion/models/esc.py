"""ESC domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.component_model import BaseComponentModel


class ESCModel(BaseComponentModel):
    """Domain model for Electronic Speed Controller (ESC)."""

    @property
    def max_current(self) -> float:
        return float(self.parameters.get("max_current", 0.0))

    @property
    def continuous_current(self) -> float:
        return float(self.parameters.get("continuous_current", self.max_current))

    @property
    def max_voltage(self) -> float:
        return float(self.parameters.get("max_voltage", 0.0))

    @property
    def resistance(self) -> float:
        return float(self.parameters.get("resistance", 0.0))

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "max_current": self.max_current,
                "continuous_current": self.continuous_current,
                "max_voltage": self.max_voltage,
                "resistance": self.resistance,
            }
        )
        return props
