"""Physical Dimensions, Quantities, Units, and Conversion Management System."""

from __future__ import annotations

from setuav_studio.units.dimension import (
    ACCELERATION,
    ANGLE,
    AREA,
    CURRENT,
    DENSITY,
    DIMENSIONLESS,
    ENERGY,
    FORCE,
    FREQUENCY,
    LENGTH,
    MASS,
    MOMENT,
    POWER,
    PRESSURE,
    TEMPERATURE,
    TIME,
    VELOCITY,
    VOLTAGE,
    VOLUME,
    WING_LOADING,
    Dimension,
)
from setuav_studio.units.manager import (
    UnitManager,
    convert_value,
    get_unit_manager,
)
from setuav_studio.units.presets import PRESETS
from setuav_studio.units.quantities import (
    QUANTITIES,
    SCHEMA_UNIT_TO_QUANTITY,
    QuantityDefinition,
    get_quantity_choices,
    get_quantity_for_unit,
)
from setuav_studio.units.unit import UnitDefinition

__all__ = [
    "ACCELERATION",
    "ANGLE",
    "AREA",
    "CURRENT",
    "DENSITY",
    "DIMENSIONLESS",
    "ENERGY",
    "FORCE",
    "FREQUENCY",
    "LENGTH",
    "MASS",
    "MOMENT",
    "POWER",
    "PRESETS",
    "PRESSURE",
    "QUANTITIES",
    "SCHEMA_UNIT_TO_QUANTITY",
    "TEMPERATURE",
    "TIME",
    "VELOCITY",
    "VOLTAGE",
    "VOLUME",
    "WING_LOADING",
    "Dimension",
    "QuantityDefinition",
    "UnitDefinition",
    "UnitManager",
    "convert_value",
    "get_quantity_choices",
    "get_quantity_for_unit",
    "get_unit_manager",
]
