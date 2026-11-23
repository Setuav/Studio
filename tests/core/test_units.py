"""Unit tests for Physical Dimensions, Quantities, and Unit Management System."""

from __future__ import annotations

import math
from unittest.mock import patch

from setuav_studio.units import (
    AREA,
    DIMENSIONLESS,
    FORCE,
    LENGTH,
    MASS,
    PRESETS,
    QUANTITIES,
    TIME,
    VELOCITY,
    convert_value,
    get_quantity_for_unit,
    get_unit_manager,
)
from setuav_studio.units.manager import UnitManager


class _FakeSettings:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.values = values if values is not None else {}

    def value(self, key: str, fallback: object = None) -> object:
        return self.values.get(key, fallback)

    def setValue(self, key: str, value: object) -> None:
        self.values[key] = value

    def sync(self) -> None:
        pass


def test_dimension_algebra() -> None:
    assert LENGTH * LENGTH == AREA
    assert LENGTH / TIME == VELOCITY
    assert MASS * (LENGTH / (TIME**2)) == FORCE
    assert DIMENSIONLESS.is_dimensionless()

    assert "L" in repr(LENGTH)
    assert "L^2" in repr(AREA)


def test_quantity_conversions() -> None:
    # Length: 1000 mm -> 1 m
    assert math.isclose(convert_value(1000.0, "length", "mm", "m"), 1.0)
    # Length: 1 in -> 25.4 mm
    assert math.isclose(convert_value(1.0, "length", "in", "mm"), 25.4)

    # Velocity: 10 m/s -> 36 km/h
    assert math.isclose(convert_value(10.0, "velocity", "m/s", "km/h"), 36.0)

    # Speed of sound in knots
    assert math.isclose(convert_value(340.29, "velocity", "m/s", "kts"), 661.47, abs_tol=0.1)

    # Force: 1 kgf -> 9.80665 N
    assert math.isclose(convert_value(1.0, "force", "kgf", "N"), 9.80665)


def test_unit_manager_signals_and_presets() -> None:
    manager = get_unit_manager()
    manager.set_active_preset("si")
    assert manager.get_display_unit("velocity") == "m/s"

    manager.set_active_preset("aviation")
    assert manager.get_display_unit("velocity") == "kts"
    assert manager.get_unit_symbol("velocity") == "kts"

    # Conversion to display (10 m/s in knots)
    disp_val = manager.to_display(10.0, "velocity")
    assert math.isclose(disp_val, 19.4384, abs_tol=0.01)

    # Convert back from display
    base_val = manager.to_base(disp_val, "velocity")
    assert math.isclose(base_val, 10.0, abs_tol=0.01)


def test_schema_unit_lookup() -> None:
    assert get_quantity_for_unit("mm") == "length"
    assert get_quantity_for_unit("kts") == "velocity"
    assert get_quantity_for_unit("dm²") == "area"
    assert get_quantity_for_unit("N*m") == "torque"
    assert get_quantity_for_unit("atm") == "pressure"
    assert get_quantity_for_unit("rad/s") == "frequency"
    assert get_quantity_for_unit("oz·in") == "torque"
    assert get_quantity_for_unit("Ω") == "resistance"
    assert get_quantity_for_unit("Wh") == "energy"
    assert get_quantity_for_unit("kWh") == "energy"
    assert get_quantity_for_unit("J") == "energy"
    assert get_quantity_for_unit("Wh/kg") == "specific_energy"
    assert get_quantity_for_unit("kJ/kg") == "specific_energy"


def test_energy_conversions() -> None:
    assert math.isclose(convert_value(100.0, "energy", "Wh", "J"), 360000.0)
    assert math.isclose(convert_value(360000.0, "energy", "J", "Wh"), 100.0)
    assert math.isclose(convert_value(1000.0, "energy", "Wh", "kWh"), 1.0)
    assert math.isclose(convert_value(180.0, "specific_energy", "Wh/kg", "kJ/kg"), 648.0)


def test_unit_manager_loads_case_sensitive_units() -> None:
    values: dict[str, object] = {
        "units/force": "N",
        "units/pressure": "Pa",
        "units/length": "MM",
    }
    with patch("setuav_studio.units.manager.QSettings", lambda: _FakeSettings(values)):
        manager = UnitManager()
    assert manager.get_display_unit("force") == "N"
    assert manager.get_display_unit("pressure") == "Pa"
    assert manager.get_display_unit("length") == "mm"


def test_unit_manager_save_load_roundtrip() -> None:
    values: dict[str, object] = {}
    emitted: list[bool] = []
    with patch("setuav_studio.units.manager.QSettings", lambda: _FakeSettings(values)):
        manager = UnitManager()
        manager.units_changed.connect(lambda: emitted.append(True))
        manager.set_display_unit("force", "kgf")
        manager.save_to_settings()
        reloaded = UnitManager()
    assert reloaded.get_display_unit("force") == "kgf"
    assert emitted == [True]


def test_convert_accepts_unit_symbols_and_case_variants() -> None:
    assert math.isclose(convert_value(180.0, "angle", "°", "rad"), math.pi, rel_tol=1e-12)
    assert math.isclose(convert_value(6000.0, "frequency", "RPM", "hz"), 100.0, rel_tol=1e-12)
    assert math.isclose(convert_value(2.5, "area", "m²", "dm2"), 250.0, rel_tol=1e-12)
    assert math.isclose(convert_value(1.0, "resistance", "Ω", "mohm"), 1000.0, rel_tol=1e-12)
    assert math.isclose(
        convert_value(16.018463373960142, "density", "kg/m³", "lb/ft3"), 1.0, rel_tol=1e-9
    )


def test_quantities_registry_consistency_and_precision() -> None:
    for q_id, qty in QUANTITIES.items():
        assert qty.base_unit_id in qty.units, f"{q_id} missing base unit"
        for u_id, u_def in qty.units.items():
            assert u_def.dimension == qty.dimension, f"{q_id}.{u_id} dimension mismatch"
            # Roundtrip every unit through base unit
            back = u_def.from_base_value(u_def.to_base_value(12.345))
            assert math.isclose(back, 12.345, rel_tol=1e-12), f"{q_id}.{u_id} roundtrip failed"
            # Altitude reuses the length units; its fields name the quantity.
            owner = "length" if q_id == "altitude" else q_id
            assert get_quantity_for_unit(u_id) == owner, f"missing lookup for id {u_id}"
            assert get_quantity_for_unit(u_def.symbol) == owner, (
                f"missing lookup for symbol {u_def.symbol}"
            )

    # Hand-verified exact conversion factors
    # 1 oz/ft² = 28.349523125 g / (3.048 dm)² = 3.051517273148435 g/dm²
    assert math.isclose(
        convert_value(1.0, "wing_loading", "oz/ft2", "g/dm2"),
        28.349523125 / (3.048**2),
        rel_tol=1e-12,
    )
    # 1 lb/ft² = 453.59237 g / (3.048 dm)² = 48.82427637037496 g/dm²
    assert math.isclose(
        convert_value(1.0, "wing_loading", "lb/ft2", "g/dm2"),
        453.59237 / (3.048**2),
        rel_tol=1e-12,
    )
    # 2*pi rad/s = 60 RPM
    assert math.isclose(
        convert_value(2.0 * math.pi, "frequency", "rad/s", "rpm"),
        60.0,
        rel_tol=1e-12,
    )
    # 1 lb/ft³ = 0.45359237 kg / (0.3048 m)³
    assert math.isclose(
        convert_value(1.0, "density", "lb/ft3", "kg/m3"),
        0.45359237 / (0.3048**3),
        rel_tol=1e-12,
    )


def test_presets_cover_all_quantities_with_valid_units() -> None:
    for preset_id, preset_map in PRESETS.items():
        for q_id, qty in QUANTITIES.items():
            assert q_id in preset_map, f"preset {preset_id} missing {q_id}"
            assert preset_map[q_id] in qty.units, (
                f"preset {preset_id} invalid unit {preset_map[q_id]} for {q_id}"
            )


def test_unit_manager_loads_case_insensitive_uppercase_unit_ids() -> None:
    values: dict[str, object] = {
        "units/active_preset": "imperial",
        "units/force": "n",
        "units/pressure": "kpa",
        "units/capacity": "mah",
    }
    with patch("setuav_studio.units.manager.QSettings", lambda: _FakeSettings(values)):
        manager = UnitManager()
    assert manager.get_display_unit("force") == "N"
    assert manager.get_display_unit("pressure") == "kPa"
    assert manager.get_display_unit("capacity") == "mAh"


def test_display_decimals_carry_the_field_precision_into_the_display_unit() -> None:
    manager = get_unit_manager()
    manager.set_active_preset("si")
    cases = (
        # quantity, display unit, base decimals, base value, expected text
        ("mass", "g", 1, 136.0, "136.0 g"),
        ("mass", "kg", 1, 136.0, "0.136 kg"),
        ("mass", "oz", 1, 136.0, "4.797 oz"),
        ("mass", "lb", 1, 136.0, "0.2998 lb"),
        ("length", "mm", 1, 150.0, "150.0 mm"),
        ("length", "m", 1, 150.0, "0.15 m"),
        ("length", "in", 1, 150.0, "5.906 in"),
        ("angle", "deg", 1, 12.5, "12.5 °"),
        ("angle", "rad", 1, 12.5, "0.218 rad"),
        ("volume", "cm3", 3, 0.189, "189 cm³"),
        ("altitude", "ft", 0, 1000.0, "3281 ft"),
    )
    try:
        for quantity, unit, decimals, base_value, expected in cases:
            manager.set_display_unit(quantity, unit)
            assert manager.format_value(base_value, quantity, decimals) == expected, unit
    finally:
        manager.set_active_preset("si")

    assert manager.display_decimals("mass", 1) == 1
    assert manager.format_value(0.75, None, 2) == "0.75"
