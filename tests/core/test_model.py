"""Unit tests for the core Vehicle, System, Component, State, Environment, and Data models."""

from __future__ import annotations

import unittest

from setuav_studio.model import (
    Component,
    Environment,
    GenericComponent,
)


class TestModelHierarchy(unittest.TestCase):
    def test_isa_environment(self) -> None:
        # Sea level standard
        env_sl = Environment.isa(0.0)
        self.assertAlmostEqual(env_sl.temperature_k, 288.15, places=1)
        self.assertAlmostEqual(env_sl.pressure_pa, 101325.0, places=0)
        self.assertAlmostEqual(env_sl.density_kg_m3, 1.225, places=2)
        self.assertAlmostEqual(env_sl.speed_of_sound_mps, 340.29, places=1)

        # 1000m altitude
        env_1k = Environment.isa(1000.0)
        self.assertLess(env_1k.temperature_k, env_sl.temperature_k)
        self.assertLess(env_1k.pressure_pa, env_sl.pressure_pa)
        self.assertLess(env_1k.density_kg_m3, env_sl.density_kg_m3)

        # Serialization
        serialized = env_1k.to_dict()
        restored = Environment.from_dict(serialized)
        self.assertAlmostEqual(restored.density_kg_m3, env_1k.density_kg_m3, places=3)

    def test_component_model(self) -> None:
        comp = Component(
            {
                "id": "motor-1",
                "name": "Front Motor",
                "type": "org.setuav.core:motor",
                "mass": 0.25,
                "attach_to": "fuselage-main",
                "transform": {
                    "position": {"x": 1.2, "y": 0.0, "z": -0.1},
                    "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                },
                "parameters": {"kv": 920.0, "resistance": 0.045},
            }
        )
        self.assertEqual(comp.id, "motor-1")
        self.assertEqual(comp.parent_id, "fuselage-main")
        self.assertEqual(comp.mass, 0.25)
        self.assertEqual(comp.x, 1.2)
        self.assertEqual(comp.kv, 920.0)

        # Modifying position
        comp.y = 0.4
        self.assertEqual(comp.position["y"], 0.4)

        # Parameter getter and setter
        self.assertEqual(comp.get_parameter("kv"), 920.0)
        self.assertEqual(comp.get_parameter("non_existent", 42), 42)
        comp.set_parameter("kv", 1000.0)
        self.assertEqual(comp.kv, 1000.0)
        self.assertEqual(comp.parameters["kv"], 1000.0)

        # Arbitrary attribute assignment does not pollute parameters
        comp.temp_attr = "hello"
        self.assertNotIn("temp_attr", comp.parameters)

        # Component is a typed model, not a subscriptable dict
        with self.assertRaises(TypeError):
            _ = comp["id"]

    def test_generic_component_fallback(self) -> None:
        generic = GenericComponent({"id": "custom-part", "name": "Custom", "type": "custom"})
        self.assertEqual(generic.id, "custom-part")

    def test_component_mass_properties_and_inertia_model(self) -> None:
        from setuav_studio.model import InertiaTensor

        tensor = InertiaTensor(ixx=0.05, iyy=0.08, izz=0.12, ixy=0.001)
        matrix = tensor.as_matrix()
        self.assertEqual(matrix[0][0], 0.05)
        self.assertEqual(matrix[0][1], -0.001)
        from_mat = InertiaTensor.from_matrix(matrix)
        self.assertAlmostEqual(from_mat.ixx, 0.05)
        self.assertAlmostEqual(from_mat.ixy, 0.001)

        comp = Component(
            {
                "id": "battery",
                "name": "LiPo Pack",
                "mass": 450.0,
                "local_cg_mm": {"x": 50.0, "y": 0.0, "z": -10.0},
                "inertia_kg_m2": {"ixx": 0.01, "iyy": 0.02, "izz": 0.03},
            }
        )
        self.assertEqual(comp.mass, 450.0)
        self.assertEqual(comp.local_cg["x"], 50.0)
        self.assertEqual(comp.inertia["izz"], 0.03)
        self.assertIsInstance(comp.inertia_tensor, InertiaTensor)
        self.assertAlmostEqual(comp.inertia_tensor.izz, 0.03)

        # Setter updates underlying raw dict
        comp.local_cg = {"x": 60.0, "y": 5.0, "z": 0.0}
        self.assertEqual(comp.raw_data["local_cg_mm"]["x"], 60.0)

        # Legacy extensions fallback
        legacy_comp = Component(
            {
                "id": "legacy_motor",
                "mass": 120.0,
                "extensions": {
                    "org.setuav.weight-balance": {
                        "local_cg_mm": {"x": 10.0, "y": 0.0, "z": 0.0},
                        "inertia_kg_m2": {"ixx": 0.005},
                    }
                },
            }
        )
        self.assertEqual(legacy_comp.local_cg["x"], 10.0)
        self.assertEqual(legacy_comp.inertia["ixx"], 0.005)


if __name__ == "__main__":
    unittest.main()
