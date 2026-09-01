"""Physical Quantities and registry with associated Dimensions and Units."""

from __future__ import annotations

from dataclasses import dataclass

from setuav_studio.units.dimension import (
    ANGLE,
    AREA,
    CURRENT,
    DENSITY,
    DIMENSIONLESS,
    FORCE,
    FREQUENCY,
    LENGTH,
    MASS,
    MOMENT,
    POWER,
    PRESSURE,
    TIME,
    VELOCITY,
    VOLTAGE,
    VOLUME,
    WING_LOADING,
    Dimension,
)
from setuav_studio.units.unit import UnitDefinition


@dataclass(frozen=True)
class QuantityDefinition:
    """Definition of a physical quantity with dimensional basis and measurement units."""

    id: str
    name: str
    base_unit_id: str
    units: dict[str, UnitDefinition]
    default_decimals: int = 2
    dimension: Dimension = DIMENSIONLESS

    def convert(self, value: float, from_unit_id: str, to_unit_id: str) -> float:
        """Convert a value between two units of this physical quantity."""
        if from_unit_id == to_unit_id:
            return float(value)
        u_from = self.units.get(from_unit_id)
        u_to = self.units.get(to_unit_id)
        if u_from is None or u_to is None:
            return float(value)
        base = u_from.to_base_value(value)
        return u_to.from_base_value(base)


QUANTITIES: dict[str, QuantityDefinition] = {
    "length": QuantityDefinition(
        id="length",
        name="Length / Dimensions",
        base_unit_id="mm",
        default_decimals=2,
        dimension=LENGTH,
        units={
            "mm": UnitDefinition(
                "mm", "mm", "Millimeter (mm)", 1.0, 1.0, decimals=2, dimension=LENGTH
            ),
            "cm": UnitDefinition(
                "cm", "cm", "Centimeter (cm)", 10.0, 0.1, decimals=2, dimension=LENGTH
            ),
            "m": UnitDefinition("m", "m", "Meter (m)", 1000.0, 0.001, decimals=3, dimension=LENGTH),
            "in": UnitDefinition(
                "in", "in", "Inch (in)", 25.4, 1.0 / 25.4, decimals=2, dimension=LENGTH
            ),
            "ft": UnitDefinition(
                "ft", "ft", "Foot (ft)", 304.8, 1.0 / 304.8, decimals=2, dimension=LENGTH
            ),
        },
    ),
    "area": QuantityDefinition(
        id="area",
        name="Area",
        base_unit_id="dm2",
        default_decimals=3,
        dimension=AREA,
        units={
            "dm2": UnitDefinition(
                "dm2", "dm²", "Square Decimeter (dm²)", 1.0, 1.0, decimals=3, dimension=AREA
            ),
            "m2": UnitDefinition(
                "m2", "m²", "Square Meter (m²)", 100.0, 0.01, decimals=4, dimension=AREA
            ),
            "cm2": UnitDefinition(
                "cm2", "cm²", "Square Centimeter (cm²)", 0.01, 100.0, decimals=2, dimension=AREA
            ),
            "mm2": UnitDefinition(
                "mm2", "mm²", "Square Millimeter (mm²)", 0.0001, 10000.0, decimals=1, dimension=AREA
            ),
            "in2": UnitDefinition(
                "in2",
                "in²",
                "Square Inch (in²)",
                0.064516,
                1.0 / 0.064516,
                decimals=2,
                dimension=AREA,
            ),
            "ft2": UnitDefinition(
                "ft2",
                "ft²",
                "Square Foot (ft²)",
                9.290304,
                1.0 / 9.290304,
                decimals=3,
                dimension=AREA,
            ),
        },
    ),
    "volume": QuantityDefinition(
        id="volume",
        name="Volume",
        base_unit_id="dm3",
        default_decimals=3,
        dimension=VOLUME,
        units={
            "dm3": UnitDefinition(
                "dm3", "dm³", "Liter / dm³", 1.0, 1.0, decimals=3, dimension=VOLUME
            ),
            "l": UnitDefinition("l", "L", "Liter (L)", 1.0, 1.0, decimals=3, dimension=VOLUME),
            "ml": UnitDefinition(
                "ml", "mL", "Milliliter (mL)", 0.001, 1000.0, decimals=1, dimension=VOLUME
            ),
            "cm3": UnitDefinition(
                "cm3", "cm³", "Cubic Centimeter (cm³)", 0.001, 1000.0, decimals=1, dimension=VOLUME
            ),
            "m3": UnitDefinition(
                "m3", "m³", "Cubic Meter (m³)", 1000.0, 0.001, decimals=4, dimension=VOLUME
            ),
            "in3": UnitDefinition(
                "in3",
                "in³",
                "Cubic Inch (in³)",
                0.016387064,
                1.0 / 0.016387064,
                decimals=2,
                dimension=VOLUME,
            ),
            "gal": UnitDefinition(
                "gal",
                "gal",
                "US Gallon",
                3.785411784,
                1.0 / 3.785411784,
                decimals=3,
                dimension=VOLUME,
            ),
        },
    ),
    "mass": QuantityDefinition(
        id="mass",
        name="Mass / Weight",
        base_unit_id="g",
        default_decimals=2,
        dimension=MASS,
        units={
            "g": UnitDefinition("g", "g", "Gram (g)", 1.0, 1.0, decimals=2, dimension=MASS),
            "kg": UnitDefinition(
                "kg", "kg", "Kilogram (kg)", 1000.0, 0.001, decimals=3, dimension=MASS
            ),
            "oz": UnitDefinition(
                "oz",
                "oz",
                "Ounce (oz)",
                28.349523125,
                1.0 / 28.349523125,
                decimals=2,
                dimension=MASS,
            ),
            "lb": UnitDefinition(
                "lb", "lb", "Pound (lb)", 453.59237, 1.0 / 453.59237, decimals=3, dimension=MASS
            ),
        },
    ),
    "angle": QuantityDefinition(
        id="angle",
        name="Angle",
        base_unit_id="deg",
        default_decimals=2,
        dimension=ANGLE,
        units={
            "deg": UnitDefinition("deg", "°", "Degree (°)", 1.0, 1.0, decimals=2, dimension=ANGLE),
            "rad": UnitDefinition(
                "rad",
                "rad",
                "Radian (rad)",
                57.29577951308232,
                1.0 / 57.29577951308232,
                decimals=4,
                dimension=ANGLE,
            ),
        },
    ),
    "velocity": QuantityDefinition(
        id="velocity",
        name="Speed / Velocity",
        base_unit_id="m/s",
        default_decimals=2,
        dimension=VELOCITY,
        units={
            "m/s": UnitDefinition(
                "m/s", "m/s", "Meter per second (m/s)", 1.0, 1.0, decimals=2, dimension=VELOCITY
            ),
            "km/h": UnitDefinition(
                "km/h",
                "km/h",
                "Kilometer per hour (km/h)",
                1.0 / 3.6,
                3.6,
                decimals=1,
                dimension=VELOCITY,
            ),
            "kts": UnitDefinition(
                "kts",
                "kts",
                "Knots (kts)",
                0.5144444444444445,
                1.0 / 0.5144444444444445,
                decimals=1,
                dimension=VELOCITY,
            ),
            "mph": UnitDefinition(
                "mph",
                "mph",
                "Miles per hour (mph)",
                0.44704,
                1.0 / 0.44704,
                decimals=1,
                dimension=VELOCITY,
            ),
            "ft/s": UnitDefinition(
                "ft/s",
                "ft/s",
                "Feet per second (ft/s)",
                0.3048,
                1.0 / 0.3048,
                decimals=2,
                dimension=VELOCITY,
            ),
        },
    ),
    "force": QuantityDefinition(
        id="force",
        name="Force / Thrust",
        base_unit_id="N",
        default_decimals=2,
        dimension=FORCE,
        units={
            "N": UnitDefinition("N", "N", "Newton (N)", 1.0, 1.0, decimals=2, dimension=FORCE),
            "kgf": UnitDefinition(
                "kgf",
                "kgf",
                "Kilogram-force (kgf)",
                9.80665,
                1.0 / 9.80665,
                decimals=3,
                dimension=FORCE,
            ),
            "gf": UnitDefinition(
                "gf",
                "gf",
                "Gram-force (gf)",
                0.00980665,
                1.0 / 0.00980665,
                decimals=1,
                dimension=FORCE,
            ),
            "lbf": UnitDefinition(
                "lbf",
                "lbf",
                "Pound-force (lbf)",
                4.4482216152605,
                1.0 / 4.4482216152605,
                decimals=2,
                dimension=FORCE,
            ),
        },
    ),
    "torque": QuantityDefinition(
        id="torque",
        name="Torque / Moment",
        base_unit_id="N*m",
        default_decimals=3,
        dimension=MOMENT,
        units={
            "N*m": UnitDefinition(
                "N*m", "N·m", "Newton-meter (N·m)", 1.0, 1.0, decimals=3, dimension=MOMENT
            ),
            "N*cm": UnitDefinition(
                "N*cm",
                "N·cm",
                "Newton-centimeter (N·cm)",
                0.01,
                100.0,
                decimals=2,
                dimension=MOMENT,
            ),
            "kgf*cm": UnitDefinition(
                "kgf*cm",
                "kgf·cm",
                "Kilogram-force centimeter (kgf·cm)",
                0.0980665,
                1.0 / 0.0980665,
                decimals=2,
                dimension=MOMENT,
            ),
            "lbf*in": UnitDefinition(
                "lbf*in",
                "lbf·in",
                "Pound-force inch (lbf·in)",
                0.1129848290276167,
                1.0 / 0.1129848290276167,
                decimals=2,
                dimension=MOMENT,
            ),
            "oz*in": UnitDefinition(
                "oz*in",
                "oz·in",
                "Ounce-force inch (oz·in)",
                0.007061551814226,
                1.0 / 0.007061551814226,
                decimals=2,
                dimension=MOMENT,
            ),
        },
    ),
    "pressure": QuantityDefinition(
        id="pressure",
        name="Pressure",
        base_unit_id="Pa",
        default_decimals=1,
        dimension=PRESSURE,
        units={
            "Pa": UnitDefinition(
                "Pa", "Pa", "Pascal (Pa)", 1.0, 1.0, decimals=1, dimension=PRESSURE
            ),
            "kPa": UnitDefinition(
                "kPa", "kPa", "Kilopascal (kPa)", 1000.0, 0.001, decimals=3, dimension=PRESSURE
            ),
            "bar": UnitDefinition(
                "bar", "bar", "Bar", 100000.0, 0.00001, decimals=4, dimension=PRESSURE
            ),
            "mbar": UnitDefinition(
                "mbar", "mbar", "Millibar / hPa", 100.0, 0.01, decimals=2, dimension=PRESSURE
            ),
            "psi": UnitDefinition(
                "psi",
                "psi",
                "Pounds per square inch (psi)",
                6894.757293168361,
                1.0 / 6894.757293168361,
                decimals=3,
                dimension=PRESSURE,
            ),
            "atm": UnitDefinition(
                "atm",
                "atm",
                "Standard Atmosphere (atm)",
                101325.0,
                1.0 / 101325.0,
                decimals=4,
                dimension=PRESSURE,
            ),
        },
    ),
    "power": QuantityDefinition(
        id="power",
        name="Power",
        base_unit_id="W",
        default_decimals=1,
        dimension=POWER,
        units={
            "W": UnitDefinition("W", "W", "Watt (W)", 1.0, 1.0, decimals=1, dimension=POWER),
            "kW": UnitDefinition(
                "kW", "kW", "Kilowatt (kW)", 1000.0, 0.001, decimals=3, dimension=POWER
            ),
            "hp": UnitDefinition(
                "hp",
                "hp",
                "Horsepower (hp)",
                745.6998715822702,
                1.0 / 745.6998715822702,
                decimals=2,
                dimension=POWER,
            ),
        },
    ),
    "voltage": QuantityDefinition(
        id="voltage",
        name="Voltage",
        base_unit_id="V",
        default_decimals=2,
        dimension=VOLTAGE,
        units={
            "V": UnitDefinition("V", "V", "Volt (V)", 1.0, 1.0, decimals=2, dimension=VOLTAGE),
            "mV": UnitDefinition(
                "mV", "mV", "Millivolt (mV)", 0.001, 1000.0, decimals=1, dimension=VOLTAGE
            ),
            "kV": UnitDefinition(
                "kV", "kV", "Kilovolt (kV)", 1000.0, 0.001, decimals=3, dimension=VOLTAGE
            ),
        },
    ),
    "current": QuantityDefinition(
        id="current",
        name="Current",
        base_unit_id="A",
        default_decimals=2,
        dimension=CURRENT,
        units={
            "A": UnitDefinition("A", "A", "Ampere (A)", 1.0, 1.0, decimals=2, dimension=CURRENT),
            "mA": UnitDefinition(
                "mA", "mA", "Milliampere (mA)", 0.001, 1000.0, decimals=1, dimension=CURRENT
            ),
        },
    ),
    "capacity": QuantityDefinition(
        id="capacity",
        name="Battery Capacity",
        base_unit_id="mAh",
        default_decimals=0,
        dimension=CURRENT * TIME,
        units={
            "mAh": UnitDefinition("mAh", "mAh", "Milliampere-hour (mAh)", 1.0, 1.0, decimals=0),
            "Ah": UnitDefinition("Ah", "Ah", "Ampere-hour (Ah)", 1000.0, 0.001, decimals=2),
            "Wh": UnitDefinition("Wh", "Wh", "Watt-hour (Wh)", 1.0, 1.0, decimals=1),
        },
    ),
    "resistance": QuantityDefinition(
        id="resistance",
        name="Electrical Resistance",
        base_unit_id="ohm",
        default_decimals=4,
        dimension=VOLTAGE / CURRENT,
        units={
            "ohm": UnitDefinition("ohm", "Ω", "Ohm (Ω)", 1.0, 1.0, decimals=4),
            "mohm": UnitDefinition("mohm", "mΩ", "Milliohm (mΩ)", 0.001, 1000.0, decimals=2),
            "kohm": UnitDefinition("kohm", "kΩ", "Kiloohm (kΩ)", 1000.0, 0.001, decimals=4),
        },
    ),
    "inertia": QuantityDefinition(
        id="inertia",
        name="Mass Moment of Inertia",
        base_unit_id="kg*m2",
        default_decimals=6,
        dimension=MASS * AREA,
        units={
            "kg*m2": UnitDefinition(
                "kg*m2", "kg·m²", "Kilogram square meter (kg·m²)", 1.0, 1.0, decimals=6
            ),
            "g*mm2": UnitDefinition(
                "g*mm2", "g·mm²", "Gram square millimeter (g·mm²)", 1e-9, 1e9, decimals=1
            ),
            "lb*in2": UnitDefinition(
                "lb*in2",
                "lb·in²",
                "Pound square inch (lb·in²)",
                0.0002926396534292,
                1.0 / 0.0002926396534292,
                decimals=4,
            ),
            "slug*ft2": UnitDefinition(
                "slug*ft2",
                "slug·ft²",
                "Slug square foot (slug·ft²)",
                1.3558179483314,
                1.0 / 1.3558179483314,
                decimals=6,
            ),
        },
    ),
    "wing_loading": QuantityDefinition(
        id="wing_loading",
        name="Wing Loading",
        base_unit_id="g/dm2",
        default_decimals=2,
        dimension=WING_LOADING,
        units={
            "g/dm2": UnitDefinition(
                "g/dm2", "g/dm²", "Gram per sq. decimeter (g/dm²)", 1.0, 1.0, decimals=2
            ),
            "kg/m2": UnitDefinition(
                "kg/m2", "kg/m²", "Kilogram per sq. meter (kg/m²)", 10.0, 0.1, decimals=2
            ),
            "oz/ft2": UnitDefinition(
                "oz/ft2", "oz/ft²", "Ounce per sq. foot (oz/ft²)", 3.0515, 1.0 / 3.0515, decimals=2
            ),
            "lb/ft2": UnitDefinition(
                "lb/ft2", "lb/ft²", "Pound per sq. foot (lb/ft²)", 48.824, 1.0 / 48.824, decimals=2
            ),
        },
    ),
    "frequency": QuantityDefinition(
        id="frequency",
        name="Frequency / Rotational Speed",
        base_unit_id="rpm",
        default_decimals=0,
        dimension=FREQUENCY,
        units={
            "rpm": UnitDefinition(
                "rpm", "RPM", "Revolutions per minute (RPM)", 1.0, 1.0, decimals=0
            ),
            "hz": UnitDefinition("hz", "Hz", "Hertz (Hz)", 60.0, 1.0 / 60.0, decimals=1),
            "rad/s": UnitDefinition(
                "rad/s",
                "rad/s",
                "Radians per second (rad/s)",
                60.0 / 6.2831853,
                6.2831853 / 60.0,
                decimals=2,
            ),
        },
    ),
    "density": QuantityDefinition(
        id="density",
        name="Density",
        base_unit_id="kg/m3",
        default_decimals=3,
        dimension=DENSITY,
        units={
            "kg/m3": UnitDefinition(
                "kg/m3", "kg/m³", "Kilogram per cubic meter (kg/m³)", 1.0, 1.0, decimals=3
            ),
            "g/cm3": UnitDefinition(
                "g/cm3", "g/cm³", "Gram per cubic centimeter (g/cm³)", 1000.0, 0.001, decimals=3
            ),
            "lb/ft3": UnitDefinition(
                "lb/ft3",
                "lb/ft³",
                "Pound per cubic foot (lb/ft³)",
                16.018463,
                1.0 / 16.018463,
                decimals=3,
            ),
        },
    ),
}

SCHEMA_UNIT_TO_QUANTITY: dict[str, str] = {
    "mm": "length",
    "cm": "length",
    "m": "length",
    "in": "length",
    "ft": "length",
    "dm2": "area",
    "dm²": "area",
    "m2": "area",
    "m²": "area",
    "cm2": "area",
    "cm²": "area",
    "mm2": "area",
    "mm²": "area",
    "in2": "area",
    "in²": "area",
    "ft2": "area",
    "ft²": "area",
    "dm3": "volume",
    "dm³": "volume",
    "l": "volume",
    "ml": "volume",
    "cm3": "volume",
    "cm³": "volume",
    "m3": "volume",
    "m³": "volume",
    "in3": "volume",
    "in³": "volume",
    "gal": "volume",
    "g": "mass",
    "kg": "mass",
    "oz": "mass",
    "lb": "mass",
    "deg": "angle",
    "°": "angle",
    "rad": "angle",
    "m/s": "velocity",
    "km/h": "velocity",
    "kts": "velocity",
    "mph": "velocity",
    "ft/s": "velocity",
    "n": "force",
    "kgf": "force",
    "gf": "force",
    "lbf": "force",
    "n*m": "torque",
    "n*cm": "torque",
    "kgf*cm": "torque",
    "lbf*in": "torque",
    "pa": "pressure",
    "kpa": "pressure",
    "bar": "pressure",
    "mbar": "pressure",
    "psi": "pressure",
    "w": "power",
    "kw": "power",
    "hp": "power",
    "v": "voltage",
    "mv": "voltage",
    "kv": "voltage",
    "a": "current",
    "ma": "current",
    "mah": "capacity",
    "ah": "capacity",
    "wh": "capacity",
    "ohm": "resistance",
    "mohm": "resistance",
    "kohm": "resistance",
    "kg*m2": "inertia",
    "kg·m²": "inertia",
    "g*mm2": "inertia",
    "g·mm²": "inertia",
    "lb*in2": "inertia",
    "lb·in²": "inertia",
    "slug*ft2": "inertia",
    "slug·ft²": "inertia",
    "g/dm2": "wing_loading",
    "g/dm²": "wing_loading",
    "kg/m2": "wing_loading",
    "kg/m²": "wing_loading",
    "rpm": "frequency",
    "hz": "frequency",
    "kg/m3": "density",
    "kg/m³": "density",
}


def get_quantity_for_unit(unit_str: str | None) -> str | None:
    """Resolve a unit string or quantity name to a recognized Quantity ID."""
    if not unit_str:
        return None
    clean = unit_str.strip().lower()
    if clean in QUANTITIES:
        return clean
    return SCHEMA_UNIT_TO_QUANTITY.get(clean)


def get_quantity_choices() -> list[tuple[str, str]]:
    """Return list of (quantity_id, display_label) for UI dropdowns."""
    choices = [("", "Dimensionless (None)")]
    for q_id, q in QUANTITIES.items():
        choices.append((q_id, f"{q.name} ({q_id})"))
    return choices


__all__ = [
    "QUANTITIES",
    "SCHEMA_UNIT_TO_QUANTITY",
    "QuantityDefinition",
    "get_quantity_choices",
    "get_quantity_for_unit",
]
