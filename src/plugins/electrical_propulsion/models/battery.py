"""Battery domain entity model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any

from plugins.electrical_propulsion.chemistry import (
    CHEMISTRIES,
    ChemistryProfile,
    UsableCurves,
    chemistry_profile,
)
from setuav_studio.api import ParameterField
from setuav_studio.model import Component

if TYPE_CHECKING:
    from pythrust.battery import RateMapBattery

# Cell properties derived from the chemistry profile; a value overrides the default.
BATTERY_OVERRIDES = ("charge_voltage", "cell_resistance", "c_rate", "pack_mass")


@dataclass(frozen=True)
class BatteryPack:
    """Battery pack of ``series`` x ``parallel`` cells of one chemistry."""

    profile: ChemistryProfile
    series: int
    parallel: int
    cell_capacity_ah: float
    charge_voltage_v: float
    """Cell charge voltage."""
    cell_resistance_ohm: float
    """Cell resistance at half the usable depth of discharge."""
    c_rate: float
    """Continuous discharge rate."""
    mass_g: float
    """Pack mass, cells, wiring and packaging."""

    @cached_property
    def curves(self) -> UsableCurves:
        return self.profile.usable_curves(self.charge_voltage_v)

    @property
    def capacity_mah(self) -> float:
        return self.cell_capacity_ah * 1000.0 * self.parallel

    @property
    def nominal_voltage_v(self) -> float:
        return self.profile.nominal_voltage_v * self.series

    @property
    def full_voltage_v(self) -> float:
        """Pack charge voltage."""
        return self.charge_voltage_v * self.series

    @property
    def cutoff_voltage_v(self) -> float:
        return self.profile.cutoff_voltage_v * self.series

    @property
    def internal_resistance_ohm(self) -> float:
        """Pack resistance at half the usable depth of discharge."""
        return self.cell_resistance_ohm * self.series / self.parallel

    @property
    def max_current_a(self) -> float:
        return self.c_rate * self.cell_capacity_ah * self.parallel

    @property
    def energy_wh(self) -> float:
        """Open-circuit energy from full charge to empty."""
        return self.curves.mean_ocv_v * self.capacity_mah / 1000.0 * self.series

    def rate_map(self) -> RateMapBattery:
        # pythrust.battery imports scipy, which slows Studio's start; load it when used.
        from pythrust.battery import RateMapBattery

        curves = self.curves
        return RateMapBattery(
            name=f"{self.profile.chemistry} {self.cell_capacity_ah * 1000.0:.0f} mAh cell",
            source=self.profile.source,
            capacity_ah=self.cell_capacity_ah,
            cutoff_voltage_v=self.profile.cutoff_voltage_v,
            charge_voltage_v=self.charge_voltage_v,
            max_current_a=self.c_rate * self.cell_capacity_ah,
            series=self.series,
            parallel=self.parallel,
            dod=curves.dod,
            ocv_v=curves.ocv_v,
            resistance_ohm=tuple(r * self.cell_resistance_ohm for r in curves.resistance_ratio),
        )


def battery_pack(parameters: Mapping[str, Any]) -> BatteryPack:
    """Return the pack described by a battery component's parameters.

    Raises ``ValueError`` when a count or the capacity lies outside its field's range,
    for example after a formula changed it.
    """
    profile = chemistry_profile(str(parameters["chemistry"]))
    for field in (BatteryModel.cell_count, BatteryModel.parallel_count, BatteryModel.cell_capacity):
        number = float(parameters[field.key])
        low, high = field.min_value, field.max_value
        assert low is not None and high is not None
        whole = field.field_type is not int or number == round(number)
        if not (whole and low <= number <= high):
            kind = "a whole number" if field.field_type is int else "a value"
            raise ValueError(
                f"{field.label} must be {kind} from {low:g} to {high:g}, got {number:g}."
            )
    series = int(parameters["cell_count"])
    parallel = int(parameters["parallel_count"])
    capacity_ah = float(parameters["cell_capacity"]) / 1000.0

    def value(key: str, default: float) -> float:
        override = parameters[key]
        return default if override is None else float(override)

    return BatteryPack(
        profile=profile,
        series=series,
        parallel=parallel,
        cell_capacity_ah=capacity_ah,
        charge_voltage_v=value("charge_voltage", profile.charge_voltage_v),
        cell_resistance_ohm=value("cell_resistance", profile.cell_resistance_ohm(capacity_ah)),
        c_rate=value("c_rate", profile.c_rate),
        mass_g=value("pack_mass", series * parallel * profile.pack_mass_per_cell_g(capacity_ah)),
    )


class BatteryModel(Component):
    """Domain model for Battery (org.setuav.core:battery).

    A battery is ``cell_count`` x ``parallel_count`` cells of one chemistry and
    capacity. The chemistry profile derives the charge voltage, cell resistance,
    C-rate and pack mass; a value in any of these parameters overrides the derived
    one. The component mass is stored and kept equal to the pack mass.
    """

    COMPONENT_TYPE = "org.setuav.core:battery"

    chemistry = ParameterField(
        key="chemistry",
        label="Chemistry",
        field_type=str,
        default=CHEMISTRIES[0],
        options=CHEMISTRIES,
        tooltip="Cell chemistry; selects the discharge curves and scaling rules.",
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
        max_value=64,
        tooltip="Number of cells connected in parallel determining capacity.",
    )
    cell_capacity = ParameterField(
        key="cell_capacity",
        label="Cell Capacity",
        unit="mAh",
        quantity="capacity",
        field_type=float,
        default=5000.0,
        min_value=100.0,
        max_value=200000.0,
        decimals=0,
        tooltip="Rated capacity of one cell.",
    )
    charge_voltage = ParameterField(
        key="charge_voltage",
        label="Charge Voltage",
        unit="V",
        quantity="voltage",
        field_type=float,
        default=None,
        decimals=2,
        tooltip="Cell charge voltage; empty uses the chemistry default.",
    )
    cell_resistance = ParameterField(
        key="cell_resistance",
        label="Cell Resistance (50% DoD)",
        unit="Ω",
        quantity="resistance",
        field_type=float,
        default=None,
        decimals=4,
        tooltip="Cell DC resistance at half depth of discharge; empty scales the "
        "chemistry's specific resistance with the capacity.",
    )
    c_rate = ParameterField(
        key="c_rate",
        label="Continuous C-Rate",
        unit="C",
        field_type=float,
        default=None,
        decimals=1,
        tooltip="Continuous discharge rate; empty uses the chemistry default.",
    )
    pack_mass = ParameterField(
        key="pack_mass",
        label="Pack Mass",
        unit="g",
        quantity="mass",
        field_type=float,
        default=None,
        decimals=1,
        tooltip="Pack mass with wiring and packaging; empty scales the chemistry's "
        "mass rule with the capacity.",
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
                "chemistry": pack.profile.chemistry,
                "cell_count": pack.series,
                "parallel_count": pack.parallel,
                "cell_capacity": pack.cell_capacity_ah * 1000.0,
                "charge_voltage": pack.charge_voltage_v,
                "cell_resistance": pack.cell_resistance_ohm,
                "c_rate": pack.c_rate,
                "pack_mass": pack.mass_g,
                "capacity": pack.capacity_mah,
                "nominal_voltage": pack.nominal_voltage_v,
                "full_voltage": pack.full_voltage_v,
                "cutoff_voltage": pack.cutoff_voltage_v,
                "internal_resistance": pack.internal_resistance_ohm,
                "max_current": pack.max_current_a,
                "energy_wh": pack.energy_wh,
            }
        )
        return props
