"""Tests for universal hierarchical expression scope and ScopeProxy."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from setuav_studio.model.expression import ExpressionEvaluator
from setuav_studio.model.scope import ScopeProxy
from setuav_studio.model.symbol import get_available_symbols_metadata
from setuav_studio.project.document import create_project


class TestUniversalScope(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = ExpressionEvaluator()

    def test_scope_proxy_primitives_and_wrappers(self) -> None:
        self.assertEqual(ScopeProxy.wrap(42), 42)
        self.assertEqual(ScopeProxy.wrap(3.14), 3.14)
        self.assertEqual(ScopeProxy.wrap("hello"), "hello")
        self.assertEqual(ScopeProxy.wrap(None), None)

        proxy = ScopeProxy.wrap({"foo": {"bar": 100}})
        self.assertIsInstance(proxy, ScopeProxy)
        self.assertEqual(proxy.foo.bar, 100)
        self.assertEqual(proxy["foo"]["bar"], 100)

    def test_hierarchical_json_dotted_paths_and_shortcuts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = create_project(Path(tmpdir) / "test.suav")
            proj.data["parameters"] = {
                "b_ref": 2000.0,
                "c_ref": 200.0,
            }
            proj.data["components"] = [
                {
                    "id": "main-wing",
                    "name": "Main Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "transform": {
                        "position": {"x": 300.0, "y": 0.0, "z": 50.0},
                        "rotation": {"roll": 0.0, "pitch": 2.0, "yaw": 0.0},
                    },
                    "parameters": {
                        "mass": 350.0,
                        "geometry": {
                            "span": 2000.0,
                            "root_chord": 250.0,
                            "tip_chord": 150.0,
                            "profiles": [
                                {"chord": 250.0, "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
                                {"chord": 150.0, "position": {"x": 60.0, "y": 1000.0, "z": 30.0}},
                            ],
                        },
                    },
                },
                {
                    "id": "main-wing-aileron",
                    "name": "Aileron",
                    "type": "org.setuav.core:control-surface",
                    "parent": "main-wing",
                    "attach_to": "main-wing",
                    "parameters": {
                        "type": "aileron",
                        "geometry": {
                            "chord": 40.0,
                            "span_start": 500.0,
                            "span_end": 950.0,
                        },
                    },
                },
                {
                    "id": "front-motor",
                    "name": "T-Motor",
                    "type": "org.setuav.core:motor",
                    "parameters": {
                        "kv": 850.0,
                        "mass": 80.0,
                        "max_power": 450.0,
                    },
                },
            ]
            proj.data["extensions"] = {
                "manufacturing": {
                    "features": {
                        "spar-1": {
                            "id": "spar-1",
                            "name": "Main Spar",
                            "width": 15.0,
                            "height": 22.0,
                            "_expressions": {
                                "height": "=main_wing.section_1.chord * 0.12",
                            },
                        },
                    },
                },
            }

            scope = proj.get_scope()

            # 1. Full JSON dotted paths
            self.assertEqual(self.evaluator.evaluate("main_wing.parameters.geometry.span", scope), 2000.0)
            self.assertEqual(self.evaluator.evaluate("main_wing.transform.position.x", scope), 300.0)
            self.assertEqual(
                self.evaluator.evaluate("main_wing.parameters.geometry.profiles[1].position.x", scope),
                60.0,
            )

            # 2. Shortcuts (1-A)
            self.assertEqual(self.evaluator.evaluate("main_wing.span", scope), 2000.0)
            self.assertEqual(self.evaluator.evaluate("main_wing.x", scope), 300.0)
            self.assertEqual(self.evaluator.evaluate("main_wing.position.x", scope), 300.0)
            self.assertEqual(self.evaluator.evaluate("main_wing.section_0.chord", scope), 250.0)
            self.assertEqual(self.evaluator.evaluate("main_wing.section_1.x", scope), 60.0)
            self.assertEqual(self.evaluator.evaluate("main_wing.sections[1].chord", scope), 150.0)

            # 3. Child component (aileron attached to main wing)
            self.assertEqual(self.evaluator.evaluate("main_wing.aileron.chord", scope), 40.0)
            self.assertEqual(self.evaluator.evaluate("aileron.chord", scope), 40.0)

            # 4. Propulsion component (motor)
            self.assertEqual(self.evaluator.evaluate("front_motor.kv", scope), 850.0)
            self.assertEqual(self.evaluator.evaluate("front_motor.parameters.kv", scope), 850.0)

            # 5. Extension features (manufacturing spar)
            self.assertEqual(self.evaluator.evaluate("spar_1.width", scope), 15.0)
            self.assertEqual(self.evaluator.evaluate("manufacturing.spar_1.width", scope), 15.0)

            # 6. Mixed multi-domain mathematical expression
            expr = "main_wing.span / 10 + front_motor.kv / 100 + spar_1.width * 2 + aileron.chord"
            expected = 200.0 + 8.5 + 30.0 + 40.0
            self.assertAlmostEqual(self.evaluator.evaluate(expr, scope), expected)

            # 7. Recompute expressions updates values
            updated = proj.recompute_expressions()
            self.assertTrue(updated)
            self.assertEqual(
                proj.data["extensions"]["manufacturing"]["features"]["spar-1"]["height"],
                18.0,
            )

    def test_symbols_metadata_includes_parameters_and_extensions(self) -> None:
        project_data = {
            "parameters": {"aspect_ratio": 9.5},
            "components": [
                {
                    "id": "motor-1",
                    "name": "Main Motor",
                    "type": "org.setuav.core:motor",
                    "transform": {"position": {"x": 100.0, "y": 0.0, "z": 0.0}},
                    "parameters": {"kv": 1200.0, "mass": 55.0},
                },
            ],
            "extensions": {
                "manufacturing": {
                    "features": {
                        "rib-1": {
                            "id": "rib-1",
                            "name": "Root Rib",
                            "thickness": 3.0,
                        },
                    },
                },
            },
        }

        metadata = get_available_symbols_metadata(project_data)
        constants = {c["key"]: c["value"] for c in metadata["constants"]}
        self.assertEqual(constants.get("aspect_ratio"), 9.5)

        comp_ids = {c["id"]: c for c in metadata["components"]}
        self.assertIn("motor_1", comp_ids)
        motor_props = {p["key"]: p["value"] for p in comp_ids["motor_1"]["properties"]}
        self.assertEqual(motor_props.get("kv"), 1200.0)
        self.assertEqual(motor_props.get("x"), 100.0)

        self.assertIn("rib_1", comp_ids)
        rib_props = {p["key"]: p["value"] for p in comp_ids["rib_1"]["properties"]}
        self.assertEqual(rib_props.get("thickness"), 3.0)


if __name__ == "__main__":
    unittest.main()
