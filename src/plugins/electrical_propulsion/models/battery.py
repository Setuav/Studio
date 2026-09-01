"""Battery domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.model import Component


class BatteryModel(Component):
    """Domain model for Battery (LiPo, Li-Ion, etc.)."""

    @property
    def capacity(self) -> float:
        return float(self.parameters.get("capacity", 0.0))

    @property
    def voltage(self) -> float:
        return float(self.parameters.get("voltage", self.parameters.get("nominal_voltage", 0.0)))

    @property
    def nominal_voltage(self) -> float:
        return self.voltage

    @property
    def cell_count(self) -> int:
        return int(self.parameters.get("cell_count", 1))

    @property
    def internal_resistance(self) -> float:
        return float(self.parameters.get("internal_resistance", 0.0))

    @property
    def max_discharge(self) -> float:
        return float(self.parameters.get("max_discharge", 0.0))

    @property
    def energy_wh(self) -> float:
        """Calculated energy capacity in Watt-hours."""
        return (self.capacity * self.nominal_voltage) / 1000.0

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "capacity": self.capacity,
                "voltage": self.voltage,
                "nominal_voltage": self.nominal_voltage,
                "cell_count": self.cell_count,
                "internal_resistance": self.internal_resistance,
                "max_discharge": self.max_discharge,
                "energy_wh": self.energy_wh,
            }
        )
        return props
