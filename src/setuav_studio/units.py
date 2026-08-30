"""Core Unit Management and Conversion System for Setuav Studio.

Provides centralized physical quantities, unit conversion mathematics,
preset profiles (SI, Aviation, Imperial), and QSettings persistence.
All models and files store data in standard base units, while the UI converts
to and from user-configured display units.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QSettings, Signal


@dataclass(frozen=True)
class UnitDefinition:
    """Definition of a single measurement unit."""

    id: str  # e.g., "mm", "in", "dm2", "kg"
    symbol: str  # e.g., "mm", "in", "dm²", "kg"
    name: str  # e.g., "Millimeter", "Inch"
    to_base: float | Callable[[float], float]  # factor to multiply or conversion func
    from_base: float | Callable[[float], float]  # factor to multiply or conversion func
    decimals: int = 2


@dataclass(frozen=True)
class QuantityDefinition:
    """Definition of a physical quantity / dimension (e.g. Length, Mass)."""

    id: str  # e.g., "length", "mass", "area"
    name: str  # e.g., "Length", "Mass", "Area"
    base_unit_id: str  # Storage unit in project files (e.g. "mm", "g", "dm2")
    units: dict[str, UnitDefinition]  # Map of unit ID to UnitDefinition
    default_decimals: int = 2


# ---------------------------------------------------------------------------
# Registry of Quantities and Units
# ---------------------------------------------------------------------------

QUANTITIES: dict[str, QuantityDefinition] = {
    "length": QuantityDefinition(
        id="length",
        name="Length / Dimensions",
        base_unit_id="mm",
        default_decimals=2,
        units={
            "mm": UnitDefinition("mm", "mm", "Millimeter (mm)", 1.0, 1.0, decimals=2),
            "cm": UnitDefinition("cm", "cm", "Centimeter (cm)", 10.0, 0.1, decimals=2),
            "m": UnitDefinition("m", "m", "Meter (m)", 1000.0, 0.001, decimals=3),
            "in": UnitDefinition("in", "in", "Inch (in)", 25.4, 1.0 / 25.4, decimals=2),
            "ft": UnitDefinition("ft", "ft", "Foot (ft)", 304.8, 1.0 / 304.8, decimals=2),
        },
    ),
    "area": QuantityDefinition(
        id="area",
        name="Area",
        base_unit_id="dm2",
        default_decimals=3,
        units={
            "dm2": UnitDefinition("dm2", "dm²", "Square Decimeter (dm²)", 1.0, 1.0, decimals=3),
            "m2": UnitDefinition("m2", "m²", "Square Meter (m²)", 100.0, 0.01, decimals=4),
            "cm2": UnitDefinition("cm2", "cm²", "Square Centimeter (cm²)", 0.01, 100.0, decimals=2),
            "mm2": UnitDefinition("mm2", "mm²", "Square Millimeter (mm²)", 0.0001, 10000.0, decimals=1),
            "in2": UnitDefinition("in2", "in²", "Square Inch (in²)", 0.064516, 1.0 / 0.064516, decimals=2),
            "ft2": UnitDefinition("ft2", "ft²", "Square Foot (ft²)", 9.290304, 1.0 / 9.290304, decimals=3),
        },
    ),
    "volume": QuantityDefinition(
        id="volume",
        name="Volume",
        base_unit_id="dm3",
        default_decimals=3,
        units={
            "dm3": UnitDefinition("dm3", "dm³", "Liter / dm³", 1.0, 1.0, decimals=3),
            "l": UnitDefinition("l", "L", "Liter (L)", 1.0, 1.0, decimals=3),
            "ml": UnitDefinition("ml", "mL", "Milliliter (mL)", 0.001, 1000.0, decimals=1),
            "cm3": UnitDefinition("cm3", "cm³", "Cubic Centimeter (cm³)", 0.001, 1000.0, decimals=1),
            "m3": UnitDefinition("m3", "m³", "Cubic Meter (m³)", 1000.0, 0.001, decimals=4),
            "in3": UnitDefinition("in3", "in³", "Cubic Inch (in³)", 0.016387064, 1.0 / 0.016387064, decimals=2),
            "gal": UnitDefinition("gal", "gal", "US Gallon", 3.785411784, 1.0 / 3.785411784, decimals=3),
        },
    ),
    "mass": QuantityDefinition(
        id="mass",
        name="Mass / Weight",
        base_unit_id="g",
        default_decimals=2,
        units={
            "g": UnitDefinition("g", "g", "Gram (g)", 1.0, 1.0, decimals=2),
            "kg": UnitDefinition("kg", "kg", "Kilogram (kg)", 1000.0, 0.001, decimals=3),
            "oz": UnitDefinition("oz", "oz", "Ounce (oz)", 28.349523125, 1.0 / 28.349523125, decimals=2),
            "lb": UnitDefinition("lb", "lb", "Pound (lb)", 453.59237, 1.0 / 453.59237, decimals=3),
        },
    ),
    "angle": QuantityDefinition(
        id="angle",
        name="Angle",
        base_unit_id="deg",
        default_decimals=2,
        units={
            "deg": UnitDefinition("deg", "°", "Degree (°)", 1.0, 1.0, decimals=2),
            "rad": UnitDefinition("rad", "rad", "Radian (rad)", 57.29577951308232, 1.0 / 57.29577951308232, decimals=4),
        },
    ),
    "velocity": QuantityDefinition(
        id="velocity",
        name="Speed / Velocity",
        base_unit_id="m/s",
        default_decimals=2,
        units={
            "m/s": UnitDefinition("m/s", "m/s", "Meter per second (m/s)", 1.0, 1.0, decimals=2),
            "km/h": UnitDefinition("km/h", "km/h", "Kilometer per hour (km/h)", 1.0 / 3.6, 3.6, decimals=1),
            "kts": UnitDefinition("kts", "kts", "Knots (kts)", 0.5144444444444445, 1.0 / 0.5144444444444445, decimals=1),
            "mph": UnitDefinition("mph", "mph", "Miles per hour (mph)", 0.44704, 1.0 / 0.44704, decimals=1),
            "ft/s": UnitDefinition("ft/s", "ft/s", "Feet per second (ft/s)", 0.3048, 1.0 / 0.3048, decimals=2),
        },
    ),
    "force": QuantityDefinition(
        id="force",
        name="Force / Thrust",
        base_unit_id="N",
        default_decimals=2,
        units={
            "N": UnitDefinition("N", "N", "Newton (N)", 1.0, 1.0, decimals=2),
            "kgf": UnitDefinition("kgf", "kgf", "Kilogram-force (kgf)", 9.80665, 1.0 / 9.80665, decimals=3),
            "gf": UnitDefinition("gf", "gf", "Gram-force (gf)", 0.00980665, 1.0 / 0.00980665, decimals=1),
            "lbf": UnitDefinition("lbf", "lbf", "Pound-force (lbf)", 4.4482216152605, 1.0 / 4.4482216152605, decimals=2),
        },
    ),
    "torque": QuantityDefinition(
        id="torque",
        name="Torque / Moment",
        base_unit_id="N*m",
        default_decimals=3,
        units={
            "N*m": UnitDefinition("N*m", "N·m", "Newton-meter (N·m)", 1.0, 1.0, decimals=3),
            "N*cm": UnitDefinition("N*cm", "N·cm", "Newton-centimeter (N·cm)", 0.01, 100.0, decimals=2),
            "kgf*cm": UnitDefinition("kgf*cm", "kgf·cm", "Kilogram-force centimeter (kgf·cm)", 0.0980665, 1.0 / 0.0980665, decimals=2),
            "lbf*in": UnitDefinition("lbf*in", "lbf·in", "Pound-force inch (lbf·in)", 0.1129848290276167, 1.0 / 0.1129848290276167, decimals=2),
            "oz*in": UnitDefinition("oz*in", "oz·in", "Ounce-force inch (oz·in)", 0.007061551814226, 1.0 / 0.007061551814226, decimals=2),
        },
    ),
    "pressure": QuantityDefinition(
        id="pressure",
        name="Pressure",
        base_unit_id="Pa",
        default_decimals=1,
        units={
            "Pa": UnitDefinition("Pa", "Pa", "Pascal (Pa)", 1.0, 1.0, decimals=1),
            "kPa": UnitDefinition("kPa", "kPa", "Kilopascal (kPa)", 1000.0, 0.001, decimals=3),
            "bar": UnitDefinition("bar", "bar", "Bar", 100000.0, 0.00001, decimals=4),
            "mbar": UnitDefinition("mbar", "mbar", "Millibar / hPa", 100.0, 0.01, decimals=2),
            "psi": UnitDefinition("psi", "psi", "Pounds per square inch (psi)", 6894.757293168361, 1.0 / 6894.757293168361, decimals=3),
            "atm": UnitDefinition("atm", "atm", "Standard Atmosphere (atm)", 101325.0, 1.0 / 101325.0, decimals=4),
        },
    ),
    "power": QuantityDefinition(
        id="power",
        name="Power",
        base_unit_id="W",
        default_decimals=1,
        units={
            "W": UnitDefinition("W", "W", "Watt (W)", 1.0, 1.0, decimals=1),
            "kW": UnitDefinition("kW", "kW", "Kilowatt (kW)", 1000.0, 0.001, decimals=3),
            "hp": UnitDefinition("hp", "hp", "Horsepower (hp)", 745.6998715822702, 1.0 / 745.6998715822702, decimals=2),
        },
    ),
    "voltage": QuantityDefinition(
        id="voltage",
        name="Voltage",
        base_unit_id="V",
        default_decimals=2,
        units={
            "V": UnitDefinition("V", "V", "Volt (V)", 1.0, 1.0, decimals=2),
            "mV": UnitDefinition("mV", "mV", "Millivolt (mV)", 0.001, 1000.0, decimals=1),
            "kV": UnitDefinition("kV", "kV", "Kilovolt (kV)", 1000.0, 0.001, decimals=3),
        },
    ),
    "current": QuantityDefinition(
        id="current",
        name="Current",
        base_unit_id="A",
        default_decimals=2,
        units={
            "A": UnitDefinition("A", "A", "Ampere (A)", 1.0, 1.0, decimals=2),
            "mA": UnitDefinition("mA", "mA", "Milliampere (mA)", 0.001, 1000.0, decimals=1),
        },
    ),
    "capacity": QuantityDefinition(
        id="capacity",
        name="Battery Capacity",
        base_unit_id="mAh",
        default_decimals=0,
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
        units={
            "ohm": UnitDefinition("ohm", "Ω", "Ohm (Ω)", 1.0, 1.0, decimals=4),
            "mohm": UnitDefinition("mohm", "mΩ", "Milliohm (mΩ)", 0.001, 1000.0, decimals=2),
            "kohm": UnitDefinition("kohm", "kΩ", "Kiloohm (kΩ)", 1000.0, 0.001, decimals=4),
        },
    ),
}

# Mapping schema unit strings (e.g. "deg", "mm", "dm2") to Quantity ID
SCHEMA_UNIT_TO_QUANTITY: dict[str, str] = {
    "mm": "length",
    "cm": "length",
    "m": "length",
    "in": "length",
    "ft": "length",
    "dm2": "area",
    "m2": "area",
    "cm2": "area",
    "mm2": "area",
    "in2": "area",
    "ft2": "area",
    "dm3": "volume",
    "l": "volume",
    "ml": "volume",
    "cm3": "volume",
    "m3": "volume",
    "g": "mass",
    "kg": "mass",
    "oz": "mass",
    "lb": "mass",
    "deg": "angle",
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
    "pa": "pressure",
    "kpa": "pressure",
    "bar": "pressure",
    "psi": "pressure",
    "w": "power",
    "kw": "power",
    "hp": "power",
    "v": "voltage",
    "mv": "voltage",
    "a": "current",
    "ma": "current",
    "mah": "capacity",
    "ah": "capacity",
    "ohm": "resistance",
    "mohm": "resistance",
}

# ---------------------------------------------------------------------------
# Unit System Presets
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict[str, str]] = {
    "si": {
        "name": "Metric (SI Standard)",
        "length": "mm",
        "area": "dm2",
        "volume": "dm3",
        "mass": "g",
        "angle": "deg",
        "velocity": "m/s",
        "force": "N",
        "torque": "N*m",
        "pressure": "Pa",
        "power": "W",
        "voltage": "V",
        "current": "A",
        "capacity": "mAh",
        "resistance": "ohm",
    },
    "aviation": {
        "name": "Aviation Standard",
        "length": "mm",
        "area": "dm2",
        "volume": "l",
        "mass": "g",
        "angle": "deg",
        "velocity": "kts",
        "force": "kgf",
        "torque": "kgf*cm",
        "pressure": "mbar",
        "power": "W",
        "voltage": "V",
        "current": "A",
        "capacity": "mAh",
        "resistance": "mohm",
    },
    "imperial": {
        "name": "Imperial (US Customary)",
        "length": "in",
        "area": "ft2",
        "volume": "in3",
        "mass": "lb",
        "angle": "deg",
        "velocity": "mph",
        "force": "lbf",
        "torque": "lbf*in",
        "pressure": "psi",
        "power": "hp",
        "voltage": "V",
        "current": "A",
        "capacity": "Ah",
        "resistance": "ohm",
    },
}


# ---------------------------------------------------------------------------
# Unit Conversion Utilities
# ---------------------------------------------------------------------------

def convert_value(
    value: float,
    quantity_id: str,
    from_unit_id: str,
    to_unit_id: str,
) -> float:
    """Convert a numeric value between two units of the same physical quantity."""
    if from_unit_id == to_unit_id:
        return value

    qty = QUANTITIES.get(quantity_id)
    if qty is None:
        return value

    from_u = qty.units.get(from_unit_id)
    to_u = qty.units.get(to_unit_id)
    if from_u is None or to_u is None:
        return value

    base_val = from_u.to_base(value) if callable(from_u.to_base) else value * from_u.to_base
    return to_u.from_base(base_val) if callable(to_u.from_base) else base_val * to_u.from_base


# ---------------------------------------------------------------------------
# Central Unit Manager with QSettings persistence
# ---------------------------------------------------------------------------

class UnitManager(QObject):
    """Central singleton managing application-wide display units and conversions."""

    units_changed = Signal()

    _SETTINGS_PREFIX = "units/"
    _PRESET_KEY = "units/active_preset"

    def __init__(self) -> None:
        super().__init__()
        self._display_units: dict[str, str] = {}
        self._active_preset: str = "si"
        self._load_from_settings()

    def _load_from_settings(self) -> None:
        settings = QSettings()
        self._active_preset = str(settings.value(self._PRESET_KEY, "si")).lower()

        # Load each quantity
        preset_defaults = PRESETS.get(self._active_preset, PRESETS["si"])
        for q_id, q_def in QUANTITIES.items():
            fallback = preset_defaults.get(q_id, q_def.base_unit_id)
            saved_unit = str(settings.value(f"{self._SETTINGS_PREFIX}{q_id}", fallback)).lower()
            if saved_unit in q_def.units:
                self._display_units[q_id] = saved_unit
            else:
                self._display_units[q_id] = fallback

    def save_to_settings(self) -> None:
        settings = QSettings()
        settings.setValue(self._PRESET_KEY, self._active_preset)
        for q_id, unit_id in self._display_units.items():
            settings.setValue(f"{self._SETTINGS_PREFIX}{q_id}", unit_id)
        settings.sync()
        self.units_changed.emit()

    def get_active_preset(self) -> str:
        return self._active_preset

    def set_active_preset(self, preset_id: str) -> None:
        preset_id = preset_id.lower()
        if preset_id in PRESETS:
            self._active_preset = preset_id
            preset_map = PRESETS[preset_id]
            for q_id in QUANTITIES:
                if q_id in preset_map:
                    self._display_units[q_id] = preset_map[q_id]
        else:
            self._active_preset = "custom"

    def get_display_unit(self, quantity_id: str) -> str:
        """Get the active display unit ID for a physical quantity (e.g. 'mm', 'in')."""
        if quantity_id in self._display_units:
            return self._display_units[quantity_id]
        qty = QUANTITIES.get(quantity_id)
        return qty.base_unit_id if qty else ""

    def set_display_unit(self, quantity_id: str, unit_id: str) -> None:
        """Set display unit for a quantity and switch preset to 'custom' if needed."""
        qty = QUANTITIES.get(quantity_id)
        if qty and unit_id in qty.units:
            self._display_units[quantity_id] = unit_id
            self._check_and_update_active_preset()

    def _check_and_update_active_preset(self) -> None:
        for preset_id, preset_map in PRESETS.items():
            matches = True
            for q_id, u_id in self._display_units.items():
                if q_id in preset_map and preset_map[q_id] != u_id:
                    matches = False
                    break
            if matches:
                self._active_preset = preset_id
                return
        self._active_preset = "custom"

    def get_unit_symbol(self, quantity_id: str, unit_id: str | None = None) -> str:
        """Get the human-readable display symbol (e.g. 'dm²', 'in', '°')."""
        qty = QUANTITIES.get(quantity_id)
        if not qty:
            return unit_id or ""
        u_id = unit_id or self.get_display_unit(quantity_id)
        u_def = qty.units.get(u_id)
        return u_def.symbol if u_def else u_id

    def to_display(self, base_value: float, quantity_or_schema_unit: str) -> float:
        """Convert a base storage value to the user's active display unit."""
        q_id = SCHEMA_UNIT_TO_QUANTITY.get(quantity_or_schema_unit.lower(), quantity_or_schema_unit)
        qty = QUANTITIES.get(q_id)
        if qty is None:
            return base_value

        target_unit = self.get_display_unit(q_id)
        return convert_value(base_value, q_id, qty.base_unit_id, target_unit)

    def to_base(self, display_value: float, quantity_or_schema_unit: str) -> float:
        """Convert a display unit value back to standard base storage unit."""
        q_id = SCHEMA_UNIT_TO_QUANTITY.get(quantity_or_schema_unit.lower(), quantity_or_schema_unit)
        qty = QUANTITIES.get(q_id)
        if qty is None:
            return display_value

        current_unit = self.get_display_unit(q_id)
        return convert_value(display_value, q_id, current_unit, qty.base_unit_id)


# Global singleton instance
_unit_manager_instance: UnitManager | None = None


def get_unit_manager() -> UnitManager:
    """Get the global UnitManager instance."""
    global _unit_manager_instance
    if _unit_manager_instance is None:
        _unit_manager_instance = UnitManager()
    return _unit_manager_instance
