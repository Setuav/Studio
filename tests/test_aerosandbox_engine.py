"""Unit tests for AeroSandbox aerodynamic engine implementation."""
from __future__ import annotations

import json
import math
from pathlib import Path
import unittest

from setuav_studio.plugins.aerodynamics.engine.base import (
    AeroResult,
    AnalysisMethod,
    AnalysisType,
    FlightCondition,
)
from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import (
    HAS_AEROSANDBOX,
    AeroSandboxEngine,
)


def _sample_components() -> list[dict]:
    return [
        {
            "id": "fuselage_1",
            "name": "Main Fuselage",
            "type": "org.setuav.core:fuselage",
            "parameters": {
                "geometry": {
                    "segments": [
                        {
                            "sections": [
                                {
                                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "profile": {"type": "circle", "diameter": 80.0},
                                },
                                {
                                    "position": {"x": 800.0, "y": 0.0, "z": 0.0},
                                    "profile": {"type": "circle", "diameter": 40.0},
                                },
                            ]
                        }
                    ]
                }
            },
        },
        {
            "id": "wing_1",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
            "transform": {
                "position": {"x": 200.0, "y": 0.0, "z": 50.0},
            },
            "parameters": {
                "geometry": {
                    "mirror": True,
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "rotation": {"x": 2.0},
                            "airfoil": "2412",
                        },
                        {
                            "position": {"x": 50.0, "y": 750.0, "z": 20.0},
                            "chord": 120.0,
                            "rotation": {"x": 0.0},
                            "airfoil": "2412",
                        },
                    ],
                }
            },
        },
    ]


class AeroSandboxEngineTests(unittest.TestCase):
    def test_engine_metadata(self) -> None:
        engine = AeroSandboxEngine()
        self.assertEqual(engine.name, "AeroSandbox")
        caps = engine.capabilities()
        self.assertIn(AnalysisMethod.VLM, caps.methods)
        self.assertIn(AnalysisMethod.AERO_BUILDUP, caps.methods)
        self.assertIn(AnalysisType.SINGLE_POINT, caps.analysis_types)
        self.assertIn(AnalysisType.ALPHA_SWEEP, caps.analysis_types)
        self.assertTrue(caps.supports_fuselage)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_geometry_conversion_to_airplane(self) -> None:
        engine = AeroSandboxEngine()
        components = _sample_components()
        airplane = engine._build_airplane(components)

        self.assertEqual(len(airplane.wings), 1)
        self.assertEqual(len(airplane.fuselages), 1)

        wing = airplane.wings[0]
        self.assertEqual(wing.name, "Main Wing")
        self.assertTrue(wing.symmetric)
        self.assertEqual(len(wing.xsecs), 2)

        # Check root cross section conversion (mm -> m)
        root = wing.xsecs[0]
        self.assertAlmostEqual(root.xyz_le[0], 0.2, places=3)  # 200 mm base_x
        self.assertAlmostEqual(root.xyz_le[1], 0.0, places=3)
        self.assertAlmostEqual(root.xyz_le[2], 0.05, places=3) # 50 mm base_z
        self.assertAlmostEqual(root.chord, 0.2, places=3)      # 200 mm chord
        self.assertEqual(root.twist, 2.0)

        tip = wing.xsecs[1]
        self.assertAlmostEqual(tip.xyz_le[0], 0.25, places=3) # 200 + 50 mm
        self.assertAlmostEqual(tip.xyz_le[1], 0.75, places=3) # 750 mm
        self.assertAlmostEqual(tip.chord, 0.12, places=3)     # 120 mm chord

        span, area = engine._compute_reference_geometry(airplane)
        self.assertGreater(span, 1.4)  # symmetric 750mm half-span -> ~1.5m total
        self.assertGreater(area, 0.2)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_analyze_aerobuildup_sweep_with_6dof_and_forces(self) -> None:
        engine = AeroSandboxEngine()
        components = _sample_components()
        cond = FlightCondition(
            velocity=20.0,
            altitude=500.0,
            alpha_min=-4.0,
            alpha_max=8.0,
            alpha_steps=7,
        )

        result = engine.analyze(components, cond, method=AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(result.method, AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(len(result.polar_points), 7)
        self.assertGreater(result.cl_max, 0.0)
        self.assertGreater(result.cd_min, 0.0)
        self.assertGreater(result.ld_max, 0.0)
        self.assertGreater(result.reference.s_ref, 0.0)
        self.assertGreater(result.reference.b_ref, 0.0)
        self.assertGreater(result.reynolds, 10000.0)
        self.assertGreater(result.dynamic_pressure, 0.0)

        # Verify 6-DoF coefficients, forces and moments on points
        for pt in result.polar_points:
            self.assertIsNotNone(pt.forces_moments)
            self.assertIsNotNone(pt.state)
            self.assertEqual(pt.state.velocity, 20.0)
            self.assertEqual(pt.state.altitude, 500.0)
            # Body coefficients
            self.assertIsInstance(pt.cx, float)
            self.assertIsInstance(pt.cy, float)
            self.assertIsInstance(pt.cz, float)
            self.assertIsInstance(pt.cl_roll, float)
            self.assertIsInstance(pt.cm, float)
            self.assertIsInstance(pt.cn, float)
            # Dimensional forces (Newtons)
            self.assertGreater(pt.drag, 0.0)
            self.assertIsInstance(pt.lift, float)
            self.assertIsInstance(pt.forces_moments.fx_b, float)
            self.assertIsInstance(pt.forces_moments.fz_b, float)

        # Verify Sweep result
        self.assertIsNotNone(result.sweep_result)
        self.assertEqual(len(result.sweep_result.points), 7)
        self.assertEqual(result.sweep_result.variable_names, ["alpha"])

        # Verify serialization
        d = result.to_dict()
        restored = AeroResult.from_dict(d)
        self.assertEqual(len(restored.polar_points), 7)
        self.assertAlmostEqual(restored.polar_points[0].cl, result.polar_points[0].cl, places=5)
        self.assertAlmostEqual(restored.polar_points[0].cx, result.polar_points[0].cx, places=5)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_analyze_vlm_single_point_with_6dof(self) -> None:
        engine = AeroSandboxEngine()
        components = _sample_components()
        cond = FlightCondition(
            velocity=25.0,
            altitude=0.0,
            alpha=4.0,
            beta=1.0,
            alpha_steps=1,
        )

        result = engine.analyze(components, cond, method=AnalysisMethod.VLM)
        self.assertEqual(result.method, AnalysisMethod.VLM)
        self.assertEqual(len(result.polar_points), 1)
        pt = result.polar_points[0]
        self.assertEqual(pt.alpha, 4.0)
        self.assertEqual(pt.beta, 1.0)
        self.assertGreater(pt.cl, 0.0)
        self.assertGreater(pt.cd, 0.0)
        self.assertIsNotNone(pt.forces_moments)
        self.assertNotEqual(pt.forces_moments.lift, 0.0)
        self.assertNotEqual(pt.cz, 0.0)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_analyze_fixed_wing_fixture(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "fixed-wing" / "project.json"
        with open(fixture_path, encoding="utf-8") as f:
            proj_data = json.load(f)

        components = proj_data.get("components", [])
        engine = AeroSandboxEngine()
        cond = FlightCondition(
            velocity=25.0,
            altitude=1000.0,
            alpha_min=-2.0,
            alpha_max=10.0,
            alpha_steps=5,
        )

        # 1. AeroBuildup with Clark-Y wing
        result_ab = engine.analyze(components, cond, method=AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(result_ab.method, AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(len(result_ab.polar_points), 5)
        self.assertGreater(result_ab.cl_max, 0.5)
        self.assertGreater(result_ab.ld_max, 5.0)

        # 2. VLM with Clark-Y wing
        result_vlm = engine.analyze(components, cond, method=AnalysisMethod.VLM)
        self.assertEqual(result_vlm.method, AnalysisMethod.VLM)
        self.assertEqual(len(result_vlm.polar_points), 5)
        self.assertGreater(result_vlm.cl_max, 0.5)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_control_surface_aileron_roll_moment(self) -> None:
        """Verify that aileron deflection generates aerodynamic roll moment in VLM."""
        engine = AeroSandboxEngine()
        components = [
            {
                "id": "wing-1",
                "name": "Main Wing",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "profiles": [
                            {"position": {"x": 0, "y": 0, "z": 0}, "chord": 200, "twist": 0, "airfoil": "naca2412"},
                            {"position": {"x": 50, "y": 800, "z": 0}, "chord": 120, "twist": 0, "airfoil": "naca2412"},
                        ],
                        "control_surfaces": [
                            {
                                "tag": "aileron",
                                "type": "aileron",
                                "eta_start": 0.5,
                                "eta_end": 0.95,
                                "chord_fraction": 0.25,
                                "deflection": 0.0,
                                "symmetry_mode": "auto",
                            }
                        ],
                    }
                },
            }
        ]

        # 1. Neutral aileron (0 deg) -> zero roll moment
        cond_neutral = FlightCondition(velocity=25.0, alpha=2.0, alpha_steps=1, control_deflections={"aileron": 0.0})
        res_neutral = engine.analyze(components, cond_neutral, method=AnalysisMethod.VLM)
        self.assertAlmostEqual(res_neutral.polar_points[0].cl_roll, 0.0, places=3)

        # 2. Deflected aileron (10 deg) -> significant roll moment
        cond_deflected = FlightCondition(velocity=25.0, alpha=2.0, alpha_steps=1, control_deflections={"aileron": 10.0})
        res_deflected = engine.analyze(components, cond_deflected, method=AnalysisMethod.VLM)
        cl_roll = res_deflected.polar_points[0].cl_roll
        self.assertNotAlmostEqual(cl_roll, 0.0, places=2)
        self.assertLess(cl_roll, -0.01)  # Right down (+10) -> left up (-10) -> roll to left (negative Cl)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_control_surface_child_component_and_elevator_pitch(self) -> None:
        """Verify child control-surface components and elevator pitch moment effects."""
        engine = AeroSandboxEngine()
        components = [
            {
                "id": "htail-1",
                "name": "Horizontal Tail",
                "type": "org.setuav.core:lifting-surface",
                "transform": {"position": {"x": 800, "y": 0, "z": 50}},
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "profiles": [
                            {"position": {"x": 0, "y": 0, "z": 0}, "chord": 150, "twist": 0, "airfoil": "naca0012"},
                            {"position": {"x": 0, "y": 300, "z": 0}, "chord": 100, "twist": 0, "airfoil": "naca0012"},
                        ],
                    }
                },
            },
            {
                "id": "elev-1",
                "name": "Elevator",
                "type": "org.setuav.core:control-surface",
                "transform": {"parent": "htail-1"},
                "parameters": {
                    "geometry": {
                        "tag": "elevator",
                        "type": "elevator",
                        "eta_start": 0.0,
                        "eta_end": 1.0,
                        "chord_fraction": 0.35,
                        "deflection": 5.0,
                        "symmetry_mode": "symmetric",
                    }
                },
            },
        ]

        # 1. Deflect down (+10 deg) -> increases tail lift, pitching nose down (more negative Cm)
        cond_down = FlightCondition(velocity=25.0, alpha=0.0, alpha_steps=1, control_deflections={"elevator": 10.0})
        res_down = engine.analyze(components, cond_down, method=AnalysisMethod.VLM)

        # 2. Deflect up (-10 deg) -> decreases tail lift, pitching nose up (more positive Cm)
        cond_up = FlightCondition(velocity=25.0, alpha=0.0, alpha_steps=1, control_deflections={"elevator": -10.0})
        res_up = engine.analyze(components, cond_up, method=AnalysisMethod.VLM)

        cm_down = res_down.polar_points[0].cm
        cm_up = res_up.polar_points[0].cm
        self.assertLess(cm_down, cm_up)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_propulsion_points_extraction(self) -> None:
        """Verify motor and propeller attachment points and thrust lines extraction."""
        engine = AeroSandboxEngine()
        components = [
            {
                "id": "wing-1",
                "name": "Wing",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "profiles": [
                            {"position": {"x": 0, "y": 0, "z": 0}, "chord": 200, "twist": 0, "airfoil": "naca2412"},
                            {"position": {"x": 50, "y": 500, "z": 0}, "chord": 150, "twist": 0, "airfoil": "naca2412"},
                        ]
                    }
                },
            },
            {
                "id": "motor-1",
                "name": "Front Motor",
                "type": "org.setuav.core:motor",
                "transform": {
                    "position": {"x": -150, "y": 0, "z": 10},
                    "rotation": {"pitch": -2.0, "yaw": 0.0, "roll": 0.0},
                },
                "parameters": {
                    "diameter": 254.0,  # 10 inch in mm
                    "pitch": 4.5,
                    "max_thrust": 18.5,
                    "kv": 920.0,
                },
            },
        ]

        cond = FlightCondition(velocity=20.0, alpha=2.0, alpha_steps=1)
        result = engine.analyze(components, cond, method=AnalysisMethod.AERO_BUILDUP)

        self.assertEqual(len(result.propulsion_points), 1)
        prop = result.propulsion_points[0]
        self.assertEqual(prop.id, "motor-1")
        self.assertEqual(prop.name, "Front Motor")
        self.assertAlmostEqual(prop.position[0], -0.150, places=3)
        self.assertAlmostEqual(prop.position[2], 0.010, places=3)
        self.assertAlmostEqual(prop.diameter, 0.254, places=3)
        self.assertEqual(prop.max_thrust, 18.5)
        self.assertEqual(prop.motor_kv, 920.0)
        self.assertAlmostEqual(prop.thrust_vector[0], math.cos(math.radians(-2.0)), places=3)


if __name__ == "__main__":
    unittest.main()

