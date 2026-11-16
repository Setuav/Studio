"""Battery domain entity model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pythrust.battery import RateMapBattery

from plugins.electrical_propulsion.cells import DEFAULT_CELLS, CellSpec, cell_spec
from setuav_studio.api import ParameterField
from setuav_studio.model import Component


@dataclass(frozen=True)
class BatteryPack:
    """Battery pack of ``series`` x ``parallel`` catalogue cells."""

    cell: CellSpec
    series: int
    parallel: int
    packaging_mass_g: float

    @property
    def capacity_mah(self) -> float:
        return self.cell.capacity_ah * 1000.0 * self.parallel

    @property
    def nominal_voltage_v(self) -> float:
        return self.cell.nominal_voltage_v * self.series

    @property
    def charge_voltage_v(self) -> float:
        return self.cell.charge_voltage_v * self.series

    @property
    def cutoff_voltage_v(self) -> float:
        return self.cell.cutoff_voltage_v * self.series

    @property
    def internal_resistance_ohm(self) -> float:
        """Pack resistance at half depth of discharge."""
        return self.cell.mid_discharge_resistance_ohm * self.series / self.parallel

    @property
    def max_current_a(self) -> float:
        return self.cell.max_current_a * self.parallel

    @property
    def energy_wh(self) -> float:
        return self.capacity_mah / 1000.0 * self.nominal_voltage_v

    @property
    def mass_g(self) -> float:
        """Cells plus packaging and wiring."""
        return self.series * self.parallel * self.cell.mass_g + self.packaging_mass_g

    def rate_map(self) -> RateMapBattery:
        return self.cell.rate_map(series=self.series, parallel=self.parallel)


def battery_pack(parameters: Mapping[str, Any]) -> BatteryPack:
    """Return the pack described by a battery component's parameters."""
    return BatteryPack(
        cell=cell_spec(str(parameters["cell_id"])),
        series=int(parameters["cell_count"]),
        parallel=int(parameters["parallel_count"]),
        packaging_mass_g=float(parameters["packaging_mass"]),
    )


class BatteryModel(Component):
    """Domain model for Battery (org.setuav.core:battery).

    A battery is ``cell_count`` x ``parallel_count`` cells of one catalogue cell; the
    pack values are derived from that cell. The component mass is stored and kept
    equal to the pack mass.
    """

    COMPONENT_TYPE = "org.setuav.core:battery"

    cell_id = ParameterField(
        key="cell_id",
        label="Cell",
        field_type=str,
        default=DEFAULT_CELLS["LiPo"],
        tooltip="Catalogue cell the pack is built from.",
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

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        """Parameter set of a new battery pack."""
        return {field.key: field.default for field in cls.get_scalar_fields()}

    @property
    def pack(self) -> BatteryPack:
        return battery_pack(self.parameters)

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        pack = self.pack
        props.update(
            {
                "cell_id": self.cell_id,
                "chemistry": pack.cell.chemistry,
                "cell_count": self.cell_count,
                "parallel_count": self.parallel_count,
                "packaging_mass": self.packaging_mass,
                "capacity": pack.capacity_mah,
                "nominal_voltage": pack.nominal_voltage_v,
                "charge_voltage": pack.charge_voltage_v,
                "cutoff_voltage": pack.cutoff_voltage_v,
                "internal_resistance": pack.internal_resistance_ohm,
                "max_current": pack.max_current_a,
                "energy_wh": pack.energy_wh,
                "derived_mass": pack.mass_g,
            }
        )
        return props
