"""Battery domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.api import ParameterField
from setuav_studio.model import Component


class BatteryModel(Component):
    """Domain model for Battery (org.setuav.core:battery)."""

    COMPONENT_TYPE = "org.setuav.core:battery"

    cell_chemistry = ParameterField(
        key="cell_chemistry",
        label="Cell Chemistry",
        unit="",
        field_type=str,
        default="LiPo",
        options=("LiPo", "Li-Ion (18650/21700)", "LiFePO4", "Solid-State", "NiMH"),
        tooltip="Battery cell chemical composition.",
    )
    cell_count = ParameterField(
        key="cell_count",
        label="Series Count (S)",
        unit="S",
        field_type=int,
        default=6,
        min_value=1,
        max_value=32,
        tooltip="Number of cells connected in series determining voltage.",
    )
    parallel_count = ParameterField(
        key="parallel_count",
        label="Parallel Count (P)",
        unit="P",
        field_type=int,
        default=1,
        min_value=1,
        max_value=16,
        tooltip="Number of cells connected in parallel determining capacity.",
    )
    capacity = ParameterField(
        key="capacity",
        label="Pack Capacity",
        unit="mAh",
        field_type=float,
        default=5000.0,
        min_value=50.0,
        max_value=500000.0,
        decimals=0,
        tooltip="Total nominal energy storage capacity in milliampere-hours.",
    )
    cell_voltage = ParameterField(
        key="cell_voltage",
        label="Cell Nominal Voltage",
        unit="V",
        field_type=float,
        default=3.7,
        min_value=1.0,
        max_value=5.0,
        decimals=2,
        tooltip="Nominal cell working voltage.",
    )
    cell_mass = ParameterField(
        key="cell_mass",
        label="Cell Mass",
        unit="g",
        field_type=float,
        default=65.0,
        min_value=1.0,
        max_value=2000.0,
        decimals=1,
        tooltip="Mass of a single raw cell in grams.",
    )
    packaging_mass = ParameterField(
        key="packaging_mass",
        label="Packaging & Lead Mass",
        unit="g",
        field_type=float,
        default=40.0,
        min_value=0.0,
        max_value=500.0,
        decimals=1,
        tooltip="Wiring, heatshrink, casing, and connector overhead mass in grams.",
    )
    internal_resistance = ParameterField(
        key="internal_resistance",
        label="Cell Resistance",
        unit="Ω",
        field_type=float,
        default=0.003,
        min_value=0.0001,
        max_value=0.5,
        decimals=4,
        tooltip="Internal resistance per cell.",
    )
    max_discharge = ParameterField(
        key="max_discharge",
        label="Discharge Rating",
        unit="C",
        field_type=float,
        default=30.0,
        min_value=1.0,
        max_value=150.0,
        decimals=1,
        tooltip="Continuous safe discharge rate in C-multiples of capacity.",
    )

    @property
    def voltage(self) -> float:
        explicit_v = self.parameters.get("voltage") or self.parameters.get("nominal_voltage")
        if explicit_v is not None:
            return float(explicit_v)
        return float(self.cell_count * self.cell_voltage)

    @property
    def nominal_voltage(self) -> float:
        return self.voltage

    @property
    def derived_mass(self) -> float:
        """Derived pack mass based on cell count and packaging."""
        return float(self.cell_count * self.parallel_count * self.cell_mass + self.packaging_mass)

    @property
    def energy_wh(self) -> float:
        """Calculated energy capacity in Watt-hours."""
        return (self.capacity * self.voltage) / 1000.0

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "cell_chemistry": self.cell_chemistry,
                "cell_count": self.cell_count,
                "parallel_count": self.parallel_count,
                "capacity": self.capacity,
                "cell_voltage": self.cell_voltage,
                "voltage": self.voltage,
                "nominal_voltage": self.nominal_voltage,
                "cell_mass": self.cell_mass,
                "packaging_mass": self.packaging_mass,
                "derived_mass": self.derived_mass,
                "internal_resistance": self.internal_resistance,
                "max_discharge": self.max_discharge,
                "energy_wh": self.energy_wh,
            }
        )
        return props
