"""End-to-end tests for Native Plugin Component Models and Live Evaluation Scope."""

from __future__ import annotations

import sys
import unittest

from PySide6.QtWidgets import QApplication

from setuav_studio.plugin_system import PluginManager, StudioAPI
from setuav_studio.plugins.core.constraints import ConstraintChecker
from setuav_studio.plugins.core.expressions import ExpressionEvaluator
from setuav_studio.plugins.core.parameters import ParameterResolver
from setuav_studio.plugins.core.symbols import get_available_symbols_metadata
from setuav_studio.project import open_project


class TestNativePluginModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)
        cls.api = StudioAPI()
        cls.pm = PluginManager(api=cls.api)
        cls.pm.discover()

    def test_native_plugin_models_in_fixture(self):
        project = open_project("tests/fixtures/fixed-wing/project.json")
        scope = project.get_scope(api=self.api)

        # 1. Verify Geometry Models
        wing = scope.get("main_wing")
        self.assertIsNotNone(wing)
        self.assertEqual(wing.__class__.__name__, "LiftingSurfaceModel")
        self.assertGreater(wing.wingspan, 1000.0)
        self.assertGreater(wing.planform_area, 100000.0)
        self.assertGreater(wing.aspect_ratio, 0.0)
        self.assertGreater(wing.mac, 0.0)

        fuselage = scope.get("fuselage")
        self.assertIsNotNone(fuselage)
        self.assertEqual(fuselage.__class__.__name__, "FuselageModel")
        self.assertGreater(fuselage.length, 0.0)

        # 2. Verify Electrical Propulsion Models
        motor = scope.get("motor_cruise")
        self.assertIsNotNone(motor)
        self.assertEqual(motor.__class__.__name__, "MotorModel")
        self.assertEqual(motor.max_power, 570.0)
        self.assertEqual(motor.kv, 900.0)

        battery = scope.get("battery_main")
        self.assertIsNotNone(battery)
        self.assertEqual(battery.__class__.__name__, "BatteryModel")
        self.assertEqual(battery.capacity, 6000.0)
        self.assertAlmostEqual(battery.voltage, 11.1)

        # 3. Verify Weight & Balance Models
        pmass = scope.get("avionics_point_mass")
        self.assertIsNotNone(pmass)
        self.assertEqual(pmass.__class__.__name__, "PointMassModel")
        self.assertEqual(pmass.mass, 150.0)

        # 4. Verify AST Expression Evaluations
        evaluator = ExpressionEvaluator()
        self.assertTrue(evaluator.evaluate("main_wing.planform_area > 0", scope))
        self.assertTrue(evaluator.evaluate("main_wing.wingspan > 1000 and motor_cruise.max_power > 100", scope))
        self.assertTrue(evaluator.evaluate("round(battery_main.capacity * battery_main.voltage / 1000, 2) == 66.6", scope))
        self.assertTrue(evaluator.evaluate("battery_main.energy_wh > 60.0", scope))

    def test_constraint_checker_with_native_models(self):
        project = open_project("tests/fixtures/fixed-wing/project.json")
        self.api.current_project = project

        evaluator = ExpressionEvaluator()
        resolver = ParameterResolver(evaluator)
        checker = ConstraintChecker(evaluator, resolver)

        constraint = {
            "id": "wing_area_check",
            "name": "Wing Area Check",
            "expression": "main_wing.planform_area / 1e6 <= 1.0",
            "severity": "warning",
            "enabled": True,
        }

        result = checker.check_constraint(constraint, project.data, api=self.api)
        self.assertTrue(result.passed)

    def test_available_symbols_metadata(self):
        project = open_project("tests/fixtures/fixed-wing/project.json")

        meta = get_available_symbols_metadata(project.data, api=self.api)
        self.assertIn("constants", meta)
        self.assertIn("components", meta)
        self.assertGreater(len(meta["components"]), 0)

        main_wing_meta = next((c for c in meta["components"] if c["id"] == "main_wing"), None)
        self.assertIsNotNone(main_wing_meta)
        prop_keys = [p["key"] for p in main_wing_meta["properties"]]
        self.assertIn("planform_area", prop_keys)
        self.assertIn("wingspan", prop_keys)
        self.assertIn("aspect_ratio", prop_keys)


if __name__ == "__main__":
    unittest.main()
