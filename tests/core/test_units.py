"""Unit tests for Physical Dimensions, Quantities, and Unit Management System."""

from __future__ import annotations

import unittest
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


class _FakeSettings:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def value(self, key: str, fallback: object = None) -> object:
        return self.values.get(key, fallback)

    def setValue(self, key: str, value: object) -> None:
        self.values[key] = value

    def sync(self) -> None:
        pass


class TestPhysicalUnitsAndDimensions(unittest.TestCase):
    def test_dimension_algebra(self) -> None:
        self.assertEqual(LENGTH * LENGTH, AREA)
        self.assertEqual(LENGTH / TIME, VELOCITY)
        self.assertEqual(MASS * (LENGTH / (TIME**2)), FORCE)
        self.assertTrue(DIMENSIONLESS.is_dimensionless())

        # Dimension representation
        self.assertIn("L", repr(LENGTH))
        self.assertIn("L^2", repr(AREA))

    def test_quantity_conversions(self) -> None:
        # Length: 1000 mm -> 1 m
        self.assertAlmostEqual(convert_value(1000.0, "length", "mm", "m"), 1.0)
        # Length: 1 in -> 25.4 mm
        self.assertAlmostEqual(convert_value(1.0, "length", "in", "mm"), 25.4)

        # Velocity: 10 m/s -> 36 km/h
        self.assertAlmostEqual(convert_value(10.0, "velocity", "m/s", "km/h"), 36.0)

        # Speed of sound in knots
        self.assertAlmostEqual(convert_value(340.29, "velocity", "m/s", "kts"), 661.47, places=1)

        # Force: 1 kgf -> 9.80665 N
        self.assertAlmostEqual(convert_value(1.0, "force", "kgf", "N"), 9.80665)

    def test_unit_manager_signals_and_presets(self) -> None:
        manager = get_unit_manager()
        manager.set_active_preset("si")
        self.assertEqual(manager.get_display_unit("velocity"), "m/s")

        manager.set_active_preset("aviation")
        self.assertEqual(manager.get_display_unit("velocity"), "kts")
        self.assertEqual(manager.get_unit_symbol("velocity"), "kts")

        # Conversion to display
        # 10 m/s in aviation preset (kts)
        disp_val = manager.to_display(10.0, "velocity")
        self.assertAlmostEqual(disp_val, 19.4384, places=2)

        # Convert back from display
        base_val = manager.to_base(disp_val, "velocity")
        self.assertAlmostEqual(base_val, 10.0, places=3)

    def test_schema_unit_lookup(self) -> None:
        self.assertEqual(get_quantity_for_unit("mm"), "length")
        self.assertEqual(get_quantity_for_unit("kts"), "velocity")
        self.assertEqual(get_quantity_for_unit("dm²"), "area")
        self.assertEqual(get_quantity_for_unit("N*m"), "torque")

    def test_schema_unit_lookup_extended(self) -> None:
        self.assertEqual(get_quantity_for_unit("atm"), "pressure")
        self.assertEqual(get_quantity_for_unit("rad/s"), "frequency")
        self.assertEqual(get_quantity_for_unit("oz·in"), "torque")
        self.assertEqual(get_quantity_for_unit("Ω"), "resistance")

    def test_unit_manager_loads_case_sensitive_units(self) -> None:
        from setuav_studio.units.manager import UnitManager

        values: dict[str, object] = {
            "units/force": "N",
            "units/pressure": "Pa",
            "units/length": "MM",
        }
        with patch("setuav_studio.units.manager.QSettings", lambda: _FakeSettings(values)):
            manager = UnitManager()
        self.assertEqual(manager.get_display_unit("force"), "N")
        self.assertEqual(manager.get_display_unit("pressure"), "Pa")
        self.assertEqual(manager.get_display_unit("length"), "mm")

    def test_unit_manager_save_load_roundtrip(self) -> None:
        from setuav_studio.units.manager import UnitManager

        values: dict[str, object] = {}
        with patch("setuav_studio.units.manager.QSettings", lambda: _FakeSettings(values)):
            manager = UnitManager()
            manager.set_display_unit("force", "kgf")
            manager.save_to_settings()
            reloaded = UnitManager()
        self.assertEqual(reloaded.get_display_unit("force"), "kgf")


if __name__ == "__main__":
    unittest.main()
