"""Unit tests for motor mount target generation, frame calculation, clearance analysis, and validation."""

from __future__ import annotations

import unittest

from plugins.electrical_propulsion.models.motor import MotorModel
from plugins.geometry.engine.mount import (
    MountFrame,
    MountTarget,
    compute_propeller_clearance,
    generate_clearance_circle_points,
    generate_mount_targets,
    resolve_mount_point,
)
from setuav_studio.project.validation import validate_project


class MotorMountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_data = {
            "name": "Test Plane",
            "components": [
                {
                    "id": "fuselage",
                    "name": "Main Fuselage",
                    "type": "org.setuav.core:fuselage",
                    "parameters": {
                        "geometry": {
                            "segments": [
                                {
                                    "tag": "nose",
                                    "sections": [
                                        {
                                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                            "profile": {"type": "circle", "diameter": 80.0},
                                        },
                                        {
                                            "position": {"x": 300.0, "y": 0.0, "z": 0.0},
                                            "profile": {"type": "circle", "diameter": 120.0},
                                        },
                                    ],
                                },
                                {
                                    "tag": "cabin",
                                    "sections": [
                                        {
                                            "position": {"x": 300.0, "y": 0.0, "z": 0.0},
                                            "profile": {"type": "circle", "diameter": 120.0},
                                        },
                                        {
                                            "position": {"x": 800.0, "y": 0.0, "z": 0.0},
                                            "profile": {"type": "circle", "diameter": 90.0},
                                        },
                                    ],
                                },
                            ]
                        }
                    },
                },
                {
                    "id": "main-wing",
                    "name": "Main Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "parameters": {
                        "geometry": {
                            "profiles": [
                                {
                                    "chord": 200.0,
                                    "position": {"x": 250.0, "y": 0.0, "z": 20.0},
                                },
                                {
                                    "chord": 140.0,
                                    "position": {"x": 280.0, "y": 600.0, "z": 25.0},
                                },
                            ]
                        }
                    },
                },
                {
                    "id": "motor-01",
                    "name": "Tractor Motor",
                    "type": "org.setuav.core:motor",
                    "parameters": {
                        "kv": 900.0,
                        "max_power": 1200.0,
                        "mount": {
                            "target_id": "main-wing",
                            "position": "front",
                            "offset": {"x": -50.0, "y": 150.0, "z": 0.0},
                            "orientation": {"roll": 0.0, "pitch": -2.0, "yaw": 0.0},
                        },
                    },
                },
                {
                    "id": "prop-01",
                    "name": "10x5 Propeller",
                    "type": "org.setuav.core:propeller",
                    "parameters": {
                        "diameter": 254.0,
                        "pitch": 127.0,
                    },
                },
            ],
        }

    def test_generate_mount_targets(self) -> None:
        targets = generate_mount_targets(self.project_data)
        target_ids = [t.id for t in targets]

        self.assertIn("main-wing", target_ids)
        self.assertIn("fuselage/segment-01", target_ids)
        self.assertIn("fuselage/segment-02", target_ids)

        wing_target = next(t for t in targets if t.id == "main-wing")
        self.assertIsInstance(wing_target, MountTarget)
        self.assertEqual(wing_target.type, "wing")
        self.assertEqual(wing_target.parent_id, "main-wing")
        self.assertIn("front", wing_target.frames)
        self.assertIn("rear", wing_target.frames)

        # Wing front frame: LE at root
        front_frame = wing_target.frames["front"]
        self.assertIsInstance(front_frame, MountFrame)
        self.assertEqual(front_frame.position, (250.0, 0.0, 20.0))
        # Wing rear frame: TE at root (250 + 200 = 450)
        rear_frame = wing_target.frames["rear"]
        self.assertEqual(rear_frame.position, (450.0, 0.0, 20.0))

    def test_fuselage_segment_frames(self) -> None:
        targets = generate_mount_targets(self.project_data)
        seg1 = next(t for t in targets if t.id == "fuselage/segment-01")
        self.assertEqual(seg1.type, "fuselage_segment")
        self.assertEqual(seg1.frames["front"].position, (0.0, 0.0, 0.0))
        self.assertEqual(seg1.frames["rear"].position, (300.0, 0.0, 0.0))

    def test_resolve_mount_point(self) -> None:
        targets = generate_mount_targets(self.project_data)
        wing_target = next(t for t in targets if t.id == "main-wing")

        offset = {"x": -30.0, "y": 200.0, "z": 10.0}
        orientation = {"roll": 1.0, "pitch": -3.0, "yaw": 2.0}

        pt, ori = resolve_mount_point(wing_target, "front", offset, orientation)
        # Front frame is (250, 0, 20) -> with offset (-30, 200, 10) = (220, 200, 30)
        self.assertEqual(pt, (220.0, 200.0, 30.0))
        self.assertEqual(ori, (1.0, -3.0, 2.0))

    def test_propeller_clearance_calculation(self) -> None:
        # Motor positioned well in front of wing with 150mm lateral offset: safe
        res = compute_propeller_clearance(
            self.project_data,
            target_id="main-wing",
            position="front",
            offset={"x": -100.0, "y": 250.0, "z": 0.0},
            orientation={"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            propeller_diameter=254.0,
        )
        self.assertTrue(res["valid"])
        self.assertFalse(res["has_collision"])
        self.assertGreater(res["clearance_mm"], 0.0)
        self.assertIn("Clearance OK", res["message"])

    def test_propeller_clearance_wing_with_transform_offset_y(self) -> None:
        from copy import deepcopy

        proj = deepcopy(self.project_data)
        proj["components"][1]["transform"] = {
            "position": {"x": 30.0, "y": 75.0, "z": 20.0}
        }
        res = compute_propeller_clearance(
            proj,
            target_id="main-wing",
            position="front",
            offset={"x": 0.0, "y": 200.0, "z": 0.0},
            orientation={"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            propeller_diameter=304.8,
        )
        self.assertTrue(res["valid"])
        self.assertFalse(res["has_collision"])
        self.assertGreater(res["clearance_mm"], 0.0)
        self.assertIn("Clearance OK", res["message"])

    def test_propeller_clearance_collision_detected(self) -> None:
        # Motor positioned intersecting wing chord at z=0 without clearance
        res = compute_propeller_clearance(
            self.project_data,
            target_id="main-wing",
            position="front",
            offset={"x": 50.0, "y": 250.0, "z": 0.0},  # 50mm behind leading edge
            orientation={"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            propeller_diameter=300.0,
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["has_collision"])
        self.assertLess(res["clearance_mm"], 0.0)
        self.assertIn("intersects wing leading edge", res["message"])

    def test_clearance_invalid_target(self) -> None:
        res = compute_propeller_clearance(
            self.project_data,
            target_id="nonexistent-target",
            position="front",
            offset={"x": 0.0, "y": 0.0, "z": 0.0},
            orientation={"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            propeller_diameter=250.0,
        )
        self.assertFalse(res["valid"])
        self.assertTrue(res["has_collision"])
        self.assertIn("not found", res["message"])

    def test_clearance_circle_points_generation(self) -> None:
        pts = generate_clearance_circle_points(
            mount_point=(100.0, 200.0, 50.0),
            orientation=(0.0, 0.0, 0.0),
            diameter=200.0,
            num_points=16,
        )
        self.assertEqual(len(pts), 16)
        # Check radius of generated circle points is 100mm from center in YZ plane
        for p in pts:
            self.assertAlmostEqual(p[0], 100.0, delta=1e-3)
            dist = ((p[1] - 200.0) ** 2 + (p[2] - 50.0) ** 2) ** 0.5
            self.assertAlmostEqual(dist, 100.0, delta=1e-3)

    def test_motor_model_properties(self) -> None:
        comp_dict = {
            "id": "m1",
            "type": "org.setuav.core:motor",
            "parameters": {
                "kv": 950.0,
                "mount": {
                    "target_id": "main-wing",
                    "position": "rear",
                    "offset": {"x": 10.0, "y": -50.0, "z": 5.0},
                    "orientation": {"roll": 0.0, "pitch": 5.0, "yaw": -1.0},
                },
            },
        }
        model = MotorModel(comp_dict)
        self.assertEqual(model.kv, 950.0)
        self.assertEqual(model.mount_target_id, "main-wing")
        self.assertEqual(model.mount_position, "rear")
        self.assertEqual(model.mount_offset["x"], 10.0)
        self.assertEqual(model.mount_offset["y"], -50.0)
        self.assertEqual(model.mount_orientation["pitch"], 5.0)

        exposed = model.get_exposed_properties()
        self.assertIn("mount", exposed)
        self.assertEqual(exposed["mount_target_id"], "main-wing")
        self.assertEqual(exposed["mount_position"], "rear")

    def test_validation_detects_unknown_mount_target(self) -> None:
        invalid_project = {
            "name": "Invalid Mount Project",
            "components": [
                {
                    "id": "motor-01",
                    "type": "org.setuav.core:motor",
                    "parameters": {
                        "mount": {
                            "target_id": "deleted-wing",
                            "position": "front",
                        }
                    },
                }
            ],
        }
        issues = validate_project(invalid_project)
        error_msgs = [i.message for i in issues if i.severity == "error"]
        self.assertTrue(
            any("references unknown mount target 'deleted-wing'" in msg for msg in error_msgs)
        )

    def test_validation_passes_valid_mount_target(self) -> None:
        issues = validate_project(self.project_data)
        mount_errors = [i for i in issues if "mount" in i.path and i.severity == "error"]
        self.assertEqual(len(mount_errors), 0)

    def test_viewport_scene_propeller_clearance_circle(self) -> None:
        from plugins.geometry.viewport.scene import build_project_geometry

        geom_data = build_project_geometry(self.project_data, {})

        # Verify NO motor 3D body/cylinder lofts are created
        motor_lofts = [loft for loft in geom_data.lofts if "motor" in loft.component_id]
        self.assertEqual(len(motor_lofts), 0)

        # Verify propeller clearance envelope is created
        prop_envs = [
            env
            for env in geom_data.envelopes
            if env.component_id == "motor-01:propeller_clearance"
        ]
        self.assertEqual(len(prop_envs), 1)
        prop_env = prop_envs[0]
        # Must have circle perimeter lines, crosshairs, and shaft axis
        self.assertGreater(len(prop_env.lines), 40)

    def test_viewport_mesh_renders_propeller_clearance(self) -> None:
        from plugins.geometry.viewport.mesh import build_envelope_wire_vertices
        from plugins.geometry.viewport.scene import build_project_geometry

        geom_data = build_project_geometry(self.project_data, {})

        # When unselected, clearance circle should still be rendered (cyan wireframe)
        unselected_verts = build_envelope_wire_vertices(
            geom_data, selected_envelope_component_id=None
        )
        self.assertGreater(len(unselected_verts), 0)

        # When motor component is selected, clearance circle is highlighted
        selected_verts = build_envelope_wire_vertices(
            geom_data,
            selected_envelope_component_id=None,
            selected_component_id="motor-01",
        )
        self.assertGreater(len(selected_verts), 0)
        # Verify color in selected_verts contains highlight color (orange: 0.95, 0.6, 0.1)
        # vertex stride is 6 (x, y, z, r, g, b)
        r_vals = [selected_verts[i + 3] for i in range(0, len(selected_verts), 6)]
        self.assertTrue(any(abs(r - 0.95) < 0.01 for r in r_vals))


if __name__ == "__main__":
    unittest.main()
