"""Battery domain entity model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from setuav_studio.api import ParameterField
from setuav_studio.model import Component


def battery_pack_mass(parameters: Mapping[str, Any]) -> float:
    """Pack mass in grams: series x parallel cells plus packaging and wiring."""
    cells = int(parameters["cell_count"]) * int(parameters["parallel_count"])
    return cells * float(parameters["cell_mass"]) + float(parameters["packaging_mass"])


class BatteryModel(Component):
    """Domain model for Battery (org.setuav.core:battery).

    Pack values (capacity, nominal voltage, internal resistance) and the component
    mass are stored next to the cell specifications they are derived from, so
    analyses read them directly.
    """

    COMPONENT_TYPE = "org.setuav.core:battery"

    chemistry = ParameterField(
        key="chemistry",
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
    nominal_voltage = ParameterField(
        key="nominal_voltage",
        label="Pack Nominal Voltage",
        unit="V",
        field_type=float,
        default=22.2,
        min_value=1.0,
        max_value=1000.0,
        decimals=1,
        tooltip="Nominal pack voltage: series count times the cell nominal voltage.",
    )
    internal_resistance = ParameterField(
        key="internal_resistance",
        label="Pack Internal Resistance",
        unit="Ω",
        field_type=float,
        default=0.015,
        min_value=0.0001,
        max_value=100.0,
        decimals=4,
        tooltip="Internal resistance of the whole pack.",
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
    max_discharge = ParameterField(
        key="max_discharge",
        label="Discharge Rating",
        unit="C",
        field_type=float,
        default=35.0,
        min_value=1.0,
        max_value=150.0,
        decimals=1,
        tooltip="Continuous safe discharge rate in C-multiples of capacity.",
    )
    burst_discharge = ParameterField(
        key="burst_discharge",
        label="Burst Discharge Rating",
        unit="C",
        field_type=float,
        default=70.0,
        min_value=1.0,
        max_value=300.0,
        decimals=1,
        tooltip="Short-duration burst discharge rate in C-multiples of capacity.",
    )
    cell_capacity = ParameterField(
        key="cell_capacity",
        label="Cell Capacity",
        unit="mAh",
        field_type=float,
        default=5000.0,
        min_value=50.0,
        max_value=100000.0,
        decimals=0,
        tooltip="Capacity of a single cell in milliampere-hours.",
    )
    cell_nominal_voltage = ParameterField(
        key="cell_nominal_voltage",
        label="Cell Nominal Voltage",
        unit="V",
        field_type=float,
        default=3.7,
        min_value=1.0,
        max_value=5.0,
        decimals=2,
        tooltip="Nominal cell working voltage.",
    )
    cell_max_voltage = ParameterField(
        key="cell_max_voltage",
        label="Cell Max Voltage",
        unit="V",
        field_type=float,
        default=4.2,
        min_value=1.0,
        max_value=5.0,
        decimals=2,
        tooltip="Fully charged cell voltage.",
    )
    cell_min_voltage = ParameterField(
        key="cell_min_voltage",
        label="Cell Cut-Off Voltage",
        unit="V",
        field_type=float,
        default=3.0,
        min_value=0.5,
        max_value=5.0,
        decimals=2,
        tooltip="Cell voltage at which discharge must stop.",
    )
    cell_resistance = ParameterField(
        key="cell_resistance",
        label="Cell Resistance",
        unit="Ω",
        field_type=float,
        default=0.0025,
        min_value=0.0001,
        max_value=0.5,
        decimals=4,
        tooltip="Internal resistance per cell.",
    )
    cell_mass = ParameterField(
        key="cell_mass",
        label="Cell Mass",
        unit="g",
        field_type=float,
        default=130.0,
        min_value=1.0,
        max_value=2000.0,
        decimals=1,
        tooltip="Mass of a single raw cell in grams.",
    )

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        """Complete, mutually consistent parameter set of a new battery pack."""
        return {field.key: field.default for field in cls.get_scalar_fields()}

    @property
    def derived_mass(self) -> float:
        """Pack mass derived from the cell count, cell mass and packaging mass."""
        return battery_pack_mass(self.parameters)

    @property
    def energy_wh(self) -> float:
        """Calculated energy capacity in Watt-hours."""
        return (self.capacity * self.nominal_voltage) / 1000.0

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "chemistry": self.chemistry,
                "cell_count": self.cell_count,
                "parallel_count": self.parallel_count,
                "capacity": self.capacity,
                "nominal_voltage": self.nominal_voltage,
                "internal_resistance": self.internal_resistance,
                "packaging_mass": self.packaging_mass,
                "max_discharge": self.max_discharge,
                "burst_discharge": self.burst_discharge,
                "cell_capacity": self.cell_capacity,
                "cell_nominal_voltage": self.cell_nominal_voltage,
                "cell_max_voltage": self.cell_max_voltage,
                "cell_min_voltage": self.cell_min_voltage,
                "cell_resistance": self.cell_resistance,
                "cell_mass": self.cell_mass,
                "derived_mass": self.derived_mass,
                "energy_wh": self.energy_wh,
            }
        )
        return props
