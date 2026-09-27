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
    with patch("setuav_studio.units.manager.QSettings", lambda: _FakeSettings(values)):
        manager = UnitManager()
        manager.set_display_unit("force", "kgf")
        manager.save_to_settings()
        reloaded = UnitManager()
    assert reloaded.get_display_unit("force") == "kgf"
