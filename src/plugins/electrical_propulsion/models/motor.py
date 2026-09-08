"""Electric Motor domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.model import Component


class MotorModel(Component):
    """Domain model for Electric Motor."""

    @property
    def kv(self) -> float:
        return float(self.parameters.get("kv", 0.0))

    @property
    def max_power(self) -> float:
        return float(self.parameters.get("max_power", 0.0))

    @property
    def max_thrust(self) -> float:
        return float(self.parameters.get("max_thrust", 0.0))

    @property
    def max_current(self) -> float:
        return float(self.parameters.get("max_current", 0.0))

    @property
    def no_load_current(self) -> float:
        return float(self.parameters.get("no_load_current", 0.0))

    @property
    def resistance(self) -> float:
        return float(self.parameters.get("resistance", 0.0))

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "kv": self.kv,
                "max_power": self.max_power,
                "max_thrust": self.max_thrust,
                "max_current": self.max_current,
                "no_load_current": self.no_load_current,
                "resistance": self.resistance,
            }
        )
        return props
