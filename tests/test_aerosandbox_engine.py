"""Unit tests for AeroSandbox aerodynamic engine implementation."""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import (
    HAS_AEROSANDBOX,
    AeroSandboxEngine,
)
from setuav_studio.plugins.aerodynamics.engine.base import (
    AeroAnalysisError,
    AeroResult,
    AnalysisMethod,
    AnalysisType,
    FlightCondition,
)
from setuav_studio.plugins.aerodynamics.engine.stability_engine import (
    StabilityAnalysisEngine,
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
        self.assertIn(AnalysisType.CONTROL_CHANNEL, caps.analysis_types)
        self.assertTrue(caps.supports_fuselage)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_all_operating_point_failures_raise_analysis_error(self) -> None:
        engine = AeroSandboxEngine()
        condition = FlightCondition(alpha=2.0, alpha_steps=1, sweep_steps=1)

        with patch(
            "setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine.asb.AeroBuildup.run",
            side_effect=RuntimeError("solver exploded"),
        ):
            with self.assertRaisesRegex(
                AeroAnalysisError,
                "failed at all 1 operating point.*solver exploded",
            ):
                engine.analyze(
                    _sample_components(),
                    condition,
                    method=AnalysisMethod.AERO_BUILDUP,
                )

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_stability_failure_is_explicit_on_usable_result(self) -> None:
        engine = AeroSandboxEngine()
        condition = FlightCondition(alpha=2.0, alpha_steps=1, sweep_steps=1)

        with patch.object(
            StabilityAnalysisEngine,
            "compute_stability",
            side_effect=RuntimeError("stability exploded"),
        ):
            result = engine.analyze(
                _sample_components(),
                condition,
                method=AnalysisMethod.AERO_BUILDUP,
            )

        self.assertEqual(result.converged_point_count, 1)
        self.assertIsNone(result.stability_derivatives)
        self.assertEqual(result.raw["stability_status"], "failed")
        self.assertEqual(result.raw["stability_error"], "stability exploded")

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
        self.assertAlmostEqual(root.xyz_le[2], 0.05, places=3)  # 50 mm base_z
        self.assertAlmostEqual(root.chord, 0.2, places=3)  # 200 mm chord
        # rotation.x is the source geometry's dihedral axis, not aerodynamic
        # twist.  AeroSandbox WingXSec currently receives explicit twist only.
        self.assertEqual(root.twist, 0.0)

        tip = wing.xsecs[1]
        self.assertAlmostEqual(tip.xyz_le[0], 0.25, places=3)  # 200 + 50 mm
        self.assertAlmostEqual(tip.xyz_le[1], 0.75, places=3)  # 750 mm
        self.assertAlmostEqual(tip.chord, 0.12, places=3)  # 120 mm chord

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
        self.assertEqual(
            restored.polar_points[0].forces_moments.force_wind,
            result.polar_points[0].forces_moments.force_wind,
        )

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
    def test_fixed_wing_fixture_matches_regression_snapshot(self) -> None:
        """Detect aerodynamic regressions against the pinned fixed-wing baseline."""
        fixture_dir = Path(__file__).parent / "fixtures" / "fixed-wing"
        proj_data = json.loads((fixture_dir / "project.json").read_text(encoding="utf-8"))
        golden = json.loads(
            (fixture_dir / "aerodynamics-reference.json").read_text(encoding="utf-8")
        )

        components = proj_data.get("components", [])
        engine = AeroSandboxEngine()
        condition = FlightCondition.from_dict(golden["condition"])
        settings = golden["settings"]
        tolerances = golden["tolerances"]

        coefficient_rel = float(tolerances["coefficient_relative"])
        coefficient_abs = float(tolerances["coefficient_absolute"])
        near_zero_abs = float(tolerances["near_zero_absolute"])
        reference_abs = float(tolerances["reference_absolute"])

        methods = (
            AnalysisMethod.AERO_BUILDUP,
            AnalysisMethod.VLM,
        )
        coefficient_fields = ("cl", "cd", "cm", "cy", "cl_roll", "cn")
        summary_fields = (
            "cl_max",
            "cl_max_alpha",
            "cd_min",
            "ld_max",
            "ld_max_alpha",
            "reynolds",
            "mach",
            "dynamic_pressure",
        )

        for method in methods:
            with self.subTest(solver=method.value):
                expected = golden["solvers"][method.value]
                result = engine.analyze(
                    components,
                    condition,
                    method=method,
                    settings=settings,
                )

                self.assertEqual(result.method, method)
                self.assertEqual(len(result.polar_points), len(expected["points"]))
                self.assertTrue(all(point.converged for point in result.polar_points))

                for field, expected_value in expected["reference"].items():
                    self.assertAlmostEqual(
                        float(getattr(result.reference, field)),
                        float(expected_value),
                        delta=reference_abs,
                        msg=f"{method.value} reference {field} changed",
                    )

                for field in summary_fields:
                    actual_value = float(getattr(result, field))
                    expected_value = float(expected["summary"][field])
                    self.assertTrue(
                        math.isclose(
                            actual_value,
                            expected_value,
                            rel_tol=coefficient_rel,
                            abs_tol=coefficient_abs,
                        ),
                        msg=(
                            f"{method.value} summary {field} changed: "
                            f"expected {expected_value:.12g}, got {actual_value:.12g}"
                        ),
                    )

                for point, expected_point in zip(
                    result.polar_points, expected["points"], strict=True
                ):
                    self.assertAlmostEqual(
                        point.alpha,
                        float(expected_point["alpha"]),
                        places=10,
                    )
                    for field in coefficient_fields:
                        actual_value = float(getattr(point, field))
                        expected_value = float(expected_point[field])
                        absolute_tolerance = (
                            near_zero_abs
                            if abs(expected_value) < near_zero_abs
                            else coefficient_abs
                        )
                        self.assertTrue(
                            math.isclose(
                                actual_value,
                                expected_value,
                                rel_tol=coefficient_rel,
                                abs_tol=absolute_tolerance,
                            ),
                            msg=(
                                f"{method.value} {field} at alpha={point.alpha:g} changed: "
                                f"expected {expected_value:.12g}, got {actual_value:.12g}"
                            ),
                        )

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_fixed_wing_fixture_matches_independent_native_model(self) -> None:
        """Compare Setuav results with a direct AeroSandbox model of the aircraft."""
        import aerosandbox as asb
        import aerosandbox.numpy as asb_np

        from tests._aerosandbox_reference import build_fixed_wing_reference

        fixture_dir = Path(__file__).parent / "fixtures" / "fixed-wing"
        project = json.loads((fixture_dir / "project.json").read_text(encoding="utf-8"))
        components = project["components"]
        main_wing = next(component for component in components if component["id"] == "main-wing")
        clark_y_coordinates = main_wing["parameters"]["geometry"]["profiles"][0]["airfoil"][
            "points"
        ]

        native_airplane = build_fixed_wing_reference(clark_y_coordinates)
        condition = FlightCondition(
            velocity=25.0,
            altitude=1000.0,
            alpha=4.0,
            beta=0.0,
            alpha_min=-2.0,
            alpha_max=10.0,
            alpha_steps=3,
        )
        settings = {
            "spanwise_resolution": 12,
            "chordwise_resolution": 8,
            "spanwise_spacing": "cosine",
            "chordwise_spacing": "cosine",
            "include_wave_drag": True,
        }
        atmosphere = asb.Atmosphere(altitude=condition.altitude)
        coefficient_map = {
            "cl": "CL",
            "cd": "CD",
            "cm": "Cm",
            "cy": "CY",
            "cl_roll": "Cl",
            "cn": "Cn",
        }
        frame_vector_map = {
            "force_body": "F_b",
            "force_wind": "F_w",
            "force_geometry": "F_g",
            "moment_body": "M_b",
            "moment_wind": "M_w",
            "moment_geometry": "M_g",
        }
        aerodynamic_force_map = {
            "lift": "L",
            "drag": "D",
            "sideforce": "Y",
        }

        for method in (AnalysisMethod.AERO_BUILDUP, AnalysisMethod.VLM):
            studio_result = AeroSandboxEngine().analyze(
                components,
                condition,
                method=method,
                settings=settings,
            )

            for studio_point in studio_result.polar_points:
                op_point = asb.OperatingPoint(
                    atmosphere=atmosphere,
                    velocity=condition.velocity,
                    alpha=studio_point.alpha,
                    beta=condition.beta,
                )
                if method == AnalysisMethod.AERO_BUILDUP:
                    native_result = asb.AeroBuildup(
                        airplane=native_airplane,
                        op_point=op_point,
                        include_wave_drag=True,
                    ).run()
                else:
                    native_result = asb.VortexLatticeMethod(
                        airplane=native_airplane,
                        op_point=op_point,
                        spanwise_resolution=12,
                        chordwise_resolution=8,
                        spanwise_spacing_function=asb_np.cosspace,
                        chordwise_spacing_function=asb_np.cosspace,
                    ).run()

                for studio_field, native_field in coefficient_map.items():
                    actual_value = float(getattr(studio_point, studio_field))
                    expected_value = float(asb_np.ravel(native_result[native_field])[0])
                    self.assertTrue(
                        math.isclose(
                            actual_value,
                            expected_value,
                            rel_tol=0.005,
                            abs_tol=0.00005,
                        ),
                        msg=(
                            f"{method.value} {studio_field} at alpha={studio_point.alpha:g} "
                            f"differs from native AeroSandbox: expected "
                            f"{expected_value:.12g}, got {actual_value:.12g}"
                        ),
                    )

                forces_moments = studio_point.forces_moments
                self.assertIsNotNone(forces_moments)
                assert forces_moments is not None

                for studio_field, native_field in frame_vector_map.items():
                    actual_vector = getattr(forces_moments, studio_field)
                    expected_vector = asb_np.ravel(native_result[native_field])
                    self.assertEqual(len(actual_vector), 3)
                    self.assertEqual(len(expected_vector), 3)
                    for axis, (actual_value, expected_value) in enumerate(
                        zip(actual_vector, expected_vector, strict=True)
                    ):
                        # Body-frame force components can be close to zero
                        # after the wind-to-body rotation; a fixed 5e-5 N/m
                        # tolerance is too strict for that numerical case.
                        force_abs_tol = max(
                            0.00005,
                            0.001 * max(abs(float(expected_value)), 1.0),
                        )
                        self.assertTrue(
                            math.isclose(
                                float(actual_value),
                                float(expected_value),
                                rel_tol=0.005,
                                abs_tol=force_abs_tol,
                            ),
                            msg=(
                                f"{method.value} {studio_field}[{axis}] at "
                                f"alpha={studio_point.alpha:g} differs from native "
                                f"AeroSandbox: expected {float(expected_value):.12g}, "
                                f"got {float(actual_value):.12g}"
                            ),
                        )

                for studio_field, native_field in aerodynamic_force_map.items():
                    actual_value = float(getattr(forces_moments, studio_field))
                    expected_value = float(asb_np.ravel(native_result[native_field])[0])
                    force_abs_tol = max(
                        0.00005,
                        0.001 * max(abs(expected_value), 1.0),
                    )
                    self.assertTrue(
                        math.isclose(
                            actual_value,
                            expected_value,
                            rel_tol=0.005,
                            abs_tol=force_abs_tol,
                        ),
                        msg=(
                            f"{method.value} {studio_field} at alpha={studio_point.alpha:g} "
                            f"differs from native AeroSandbox: expected "
                            f"{expected_value:.12g}, got {actual_value:.12g}"
                        ),
                    )

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_fixed_wing_fixture_geometry_contract(self) -> None:
        """Keep the project-to-AeroSandbox geometry contract explicit."""
        fixture_path = Path(__file__).parent / "fixtures" / "fixed-wing" / "project.json"
        components = json.loads(fixture_path.read_text(encoding="utf-8"))["components"]
        airplane = AeroSandboxEngine()._build_airplane(components)

        self.assertEqual([wing.name for wing in airplane.wings], ["Main Wing", "V-Tail"])
        self.assertTrue(airplane.wings[0].symmetric)
        self.assertTrue(airplane.wings[1].symmetric)
        self.assertEqual(len(airplane.fuselages), 1)
        self.assertGreater(airplane.wings[0].area(), 0.1)
        self.assertGreater(
            airplane.fuselages[0].xsecs[-1].xyz_c[0], airplane.fuselages[0].xsecs[0].xyz_c[0]
        )

        # Attachment offsets are part of the component frame and must survive
        # the mirrored conversion; they are not forced onto the centerline.
        self.assertAlmostEqual(float(airplane.wings[0].xsecs[0].xyz_le[1]), 0.075, places=6)
        self.assertAlmostEqual(float(airplane.wings[0].xsecs[-1].xyz_le[1]), 0.751190, places=5)
        self.assertAlmostEqual(float(airplane.wings[1].xsecs[0].xyz_le[1]), 0.038, places=6)

        # The fixture uses rounded rectangular body sections.  Native
        # FuselageXSec cannot encode the exact arc/line outline, but the
        # rounded superellipse approximation and section normal are retained.
        self.assertGreater(float(airplane.fuselages[0].xsecs[0].shape), 2.0)
        self.assertAlmostEqual(float(airplane.fuselages[0].xsecs[0].xyz_normal[0]), 1.0, places=6)

    def test_non_superellipse_fuselage_profiles_keep_bounded_envelopes(self) -> None:
        """Document the controlled envelope mapping for non-native section types."""
        engine = AeroSandboxEngine()
        cases = (
            (
                {"type": "trapezoid", "top_width": 40, "bottom_width": 80, "height": 30},
                (0.08, 0.03, 1000.0),
            ),
            ({"type": "triangle", "base_width": 60, "height": 25}, (0.06, 0.025, 1.05)),
            (
                {
                    "type": "polygon",
                    "vertices": [
                        {"y": -20, "z": -10},
                        {"y": 30, "z": -5},
                        {"y": 15, "z": 20},
                    ],
                },
                (0.05, 0.03, 1.05),
            ),
        )
        for profile, expected in cases:
            with self.subTest(profile=profile["type"]):
                width, height, shape = engine._fuselage_profile_parameters(profile)
                self.assertAlmostEqual(width, expected[0])
                self.assertAlmostEqual(height, expected[1])
                self.assertAlmostEqual(shape, expected[2])

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
                            {
                                "position": {"x": 0, "y": 0, "z": 0},
                                "chord": 200,
                                "twist": 0,
                                "airfoil": "naca2412",
                            },
                            {
                                "position": {"x": 50, "y": 800, "z": 0},
                                "chord": 120,
                                "twist": 0,
                                "airfoil": "naca2412",
                            },
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
        cond_neutral = FlightCondition(
            velocity=25.0, alpha=2.0, alpha_steps=1, control_deflections={"aileron": 0.0}
        )
        res_neutral = engine.analyze(components, cond_neutral, method=AnalysisMethod.VLM)
        self.assertAlmostEqual(res_neutral.polar_points[0].cl_roll, 0.0, places=3)
        native_controls = [
            surface
            for wing in res_neutral.raw["airplane"].wings
            for xsec in wing.xsecs
            for surface in xsec.control_surfaces
        ]
        self.assertTrue(any(surface.name == "aileron" for surface in native_controls))
        self.assertTrue(
            any(math.isclose(float(surface.hinge_point), 0.75) for surface in native_controls)
        )

        # 2. Deflected aileron (10 deg) -> significant roll moment
        cond_deflected = FlightCondition(
            velocity=25.0, alpha=2.0, alpha_steps=1, control_deflections={"aileron": 10.0}
        )
        res_deflected = engine.analyze(components, cond_deflected, method=AnalysisMethod.VLM)
        cl_roll = res_deflected.polar_points[0].cl_roll
        self.assertNotAlmostEqual(cl_roll, 0.0, places=2)
        self.assertLess(
            cl_roll, -0.01
        )  # Right down (+10) -> left up (-10) -> roll to left (negative Cl)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_control_surface_child_component_and_elevator_pitch(self) -> None:
        """Verify child control-surface components and elevator pitch moment effects."""
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
                            {
                                "position": {"x": 0, "y": 0, "z": 0},
                                "chord": 250,
                                "twist": 0,
                                "airfoil": "naca0012",
                            },
                            {
                                "position": {"x": 30, "y": 700, "z": 0},
                                "chord": 150,
                                "twist": 0,
                                "airfoil": "naca0012",
                            },
                        ],
                    }
                },
            },
            {
                "id": "htail-1",
                "name": "Horizontal Tail",
                "type": "org.setuav.core:lifting-surface",
                "transform": {"position": {"x": 800, "y": 0, "z": 50}},
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "profiles": [
                            {
                                "position": {"x": 0, "y": 0, "z": 0},
                                "chord": 150,
                                "twist": 0,
                                "airfoil": "naca0012",
                            },
                            {
                                "position": {"x": 0, "y": 300, "z": 0},
                                "chord": 100,
                                "twist": 0,
                                "airfoil": "naca0012",
                            },
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
                        "deflection": 0.0,
                        "symmetry_mode": "symmetric",
                    }
                },
            },
        ]

        # 1. Deflect down (+10 deg) -> increases tail lift, pitching nose down (more negative Cm)
        cond_down = FlightCondition(
            velocity=25.0, alpha=0.0, alpha_steps=1, control_deflections={"elevator": 10.0}
        )
        res_down = engine.analyze(components, cond_down, method=AnalysisMethod.VLM)

        # 2. Deflect up (-10 deg) -> decreases tail lift, pitching nose up (more positive Cm)
        cond_up = FlightCondition(
            velocity=25.0, alpha=0.0, alpha_steps=1, control_deflections={"elevator": -10.0}
        )
        res_up = engine.analyze(components, cond_up, method=AnalysisMethod.VLM)

        cm_down = res_down.polar_points[0].cm
        cm_up = res_up.polar_points[0].cm
        self.assertLess(cm_down, cm_up)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_control_surface_overlap_preserves_exact_span_intervals(self) -> None:
        """Flap/aileron overlap must remain two controls without spanwise bleeding."""
        components = [
            {
                "id": "wing-1",
                "name": "Main Wing",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "profiles": [
                            {
                                "position": {"x": 0, "y": 0, "z": 0},
                                "chord": 200,
                                "airfoil": "naca0012",
                            },
                            {
                                "position": {"x": 30, "y": 1000, "z": 0},
                                "chord": 100,
                                "airfoil": "naca0012",
                            },
                        ],
                        "control_surfaces": [
                            {
                                "tag": "flap",
                                "type": "flap",
                                "eta_start": 0.10,
                                "eta_end": 0.65,
                                "chord_fraction": 0.30,
                                "symmetry_mode": "auto",
                            },
                            {
                                "tag": "aileron",
                                "type": "aileron",
                                "eta_start": 0.45,
                                "eta_end": 0.90,
                                "chord_fraction": 0.25,
                                "symmetry_mode": "auto",
                            },
                        ],
                    }
                },
            }
        ]
        airplane = AeroSandboxEngine()._build_airplane(
            components,
            condition=FlightCondition(control_deflections={"flap": 8.0, "aileron": 5.0}),
            control_encoding="native",
        )

        self.assertEqual(
            [wing.name for wing in airplane.wings], ["Main Wing_Right", "Main Wing_Left"]
        )

        def section_controls(wing: object) -> list[list[tuple[str, float]]]:
            return [
                [(surface.name, float(surface.deflection)) for surface in xsec.control_surfaces]
                for xsec in wing.xsecs[:-1]
            ]

        self.assertEqual(
            section_controls(airplane.wings[0]),
            [
                [],
                [("flap", 8.0)],
                [("flap", 8.0), ("aileron", 5.0)],
                [("aileron", 5.0)],
                [],
            ],
        )
        self.assertEqual(
            section_controls(airplane.wings[1]),
            [
                [],
                [("aileron", -5.0)],
                [("flap", 8.0), ("aileron", -5.0)],
                [("flap", 8.0)],
                [],
            ],
        )

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_control_surface_right_left_symmetry_modes(self) -> None:
        """Auto, explicit symmetric/antisymmetric and one-sided modes are deterministic."""

        def converted_deflections(
            surface_type: str, symmetry_mode: str
        ) -> tuple[float, float | None]:
            components = [
                {
                    "id": "wing-1",
                    "name": "Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "parameters": {
                        "geometry": {
                            "mirror": True,
                            "profiles": [
                                {
                                    "position": {"x": 0, "y": 0, "z": 0},
                                    "chord": 200,
                                    "airfoil": "naca0012",
                                },
                                {
                                    "position": {"x": 0, "y": 500, "z": 0},
                                    "chord": 120,
                                    "airfoil": "naca0012",
                                },
                            ],
                            "control_surfaces": [
                                {
                                    "tag": surface_type,
                                    "type": surface_type,
                                    "eta_start": 0.2,
                                    "eta_end": 0.9,
                                    "chord_fraction": 0.3,
                                    "symmetry_mode": symmetry_mode,
                                }
                            ],
                        }
                    },
                }
            ]
            airplane = AeroSandboxEngine()._build_airplane(
                components,
                condition=FlightCondition(control_deflections={surface_type: 6.0}),
                control_encoding="native",
            )
            right = next(
                float(surface.deflection)
                for xsec in airplane.wings[0].xsecs
                for surface in xsec.control_surfaces
            )
            left_controls = [
                float(surface.deflection)
                for xsec in airplane.wings[-1].xsecs
                for surface in xsec.control_surfaces
            ]
            return right, left_controls[0] if left_controls else None

        cases = [
            ("elevator", "auto", (6.0, 6.0)),
            ("aileron", "auto", (6.0, -6.0)),
            ("aileron", "symmetric", (6.0, 6.0)),
            ("elevator", "antisymmetric", (6.0, -6.0)),
            ("flap", "none", (6.0, None)),
        ]
        for surface_type, symmetry_mode, expected in cases:
            with self.subTest(surface_type=surface_type, symmetry_mode=symmetry_mode):
                self.assertEqual(converted_deflections(surface_type, symmetry_mode), expected)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_composite_elevon_and_ruddervator_channel_mixing(self) -> None:
        """Composite controls mix symmetric pitch with differential lateral channels."""

        def lifting_surface(component_id: str, name: str, surface_type: str, roll: float) -> dict:
            return {
                "id": component_id,
                "name": name,
                "type": "org.setuav.core:lifting-surface",
                "transform": {"rotation": {"roll": roll}},
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "profiles": [
                            {
                                "position": {"x": 0, "y": 0, "z": 0},
                                "chord": 200,
                                "airfoil": "naca0012",
                            },
                            {
                                "position": {"x": 0, "y": 500, "z": 0},
                                "chord": 120,
                                "airfoil": "naca0012",
                            },
                        ],
                        "control_surfaces": [
                            {
                                "tag": surface_type,
                                "type": surface_type,
                                "eta_start": 0.2,
                                "eta_end": 0.9,
                                "chord_fraction": 0.3,
                                "symmetry_mode": "auto",
                            }
                        ],
                    }
                },
            }

        airplane = AeroSandboxEngine()._build_airplane(
            [
                lifting_surface("elevon-1", "Elevon Wing", "elevon", 0.0),
                lifting_surface("vtail-1", "V-Tail", "ruddervator", 35.0),
            ],
            condition=FlightCondition(
                control_deflections={"elevator": 4.0, "aileron": 3.0, "rudder": 2.0}
            ),
            control_encoding="native",
        )

        def deflections(wing_name: str) -> list[float]:
            wing = next(wing for wing in airplane.wings if wing.name == wing_name)
            return [
                float(surface.deflection)
                for xsec in wing.xsecs
                for surface in xsec.control_surfaces
            ]

        self.assertEqual(deflections("Elevon Wing_Right"), [7.0])
        self.assertEqual(deflections("Elevon Wing_Left"), [1.0])
        self.assertEqual(deflections("V-Tail_Right"), [6.0])
        self.assertEqual(deflections("V-Tail_Left"), [2.0])

        # The rolled V-tail remains a real left/right pair, not a global-XZ
        # AeroSandbox mirror that would lose its attachment frame.
        right_tip = airplane.wings[2].xsecs[-1].xyz_le
        left_tip = airplane.wings[3].xsecs[0].xyz_le
        self.assertGreater(float(right_tip[2]), 0.0)
        self.assertAlmostEqual(float(right_tip[1]), -float(left_tip[1]), places=6)
        self.assertAlmostEqual(float(right_tip[2]), float(left_tip[2]), places=6)

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
                            {
                                "position": {"x": 0, "y": 0, "z": 0},
                                "chord": 200,
                                "twist": 0,
                                "airfoil": "naca2412",
                            },
                            {
                                "position": {"x": 50, "y": 500, "z": 0},
                                "chord": 150,
                                "twist": 0,
                                "airfoil": "naca2412",
                            },
                        ],
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

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_aero_buildup_primary_solver(self) -> None:
        """Verify native AeroBuildup primary solver executes cleanly and computes 3D aerodynamics."""
        engine = AeroSandboxEngine()
        components = _sample_components()
        cond = FlightCondition(
            velocity=25.0,
            altitude=500.0,
            alpha_min=-2.0,
            alpha_max=8.0,
            alpha_steps=3,
        )

        settings = {
            "spanwise_resolution": 10,
            "chordwise_resolution": 6,
            "spanwise_spacing": "cosine",
            "include_wave_drag": True,
            "compressibility_correction": True,
        }

        result = engine.analyze(
            components,
            cond,
            method=AnalysisMethod.AERO_BUILDUP,
            settings=settings,
        )

        self.assertEqual(result.method, AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(len(result.polar_points), 3)

        # Check native polar points and coefficients
        for pt in result.polar_points:
            self.assertGreater(pt.cd, 0.0)
            self.assertIsNotNone(pt.forces_moments)
            self.assertTrue(pt.converged)

        # Check serialization round-trip
        d = result.to_dict()
        json.dumps(d, allow_nan=False)
        restored = AeroResult.from_dict(d)
        self.assertEqual(restored.method, AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(len(restored.polar_points), 3)

    def test_weight_balance_cg_is_used_as_reference(self) -> None:
        components = _sample_components()
        components[0]["mass"] = 1000.0
        components[0]["extensions"] = {
            "org.setuav.weight-balance": {
                "local_cg_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
        }
        components[1]["mass"] = 3000.0
        components[1]["extensions"] = {
            "org.setuav.weight-balance": {
                "local_cg_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
        }
        cg, source = AeroSandboxEngine._resolve_mass_cg(components)
        self.assertEqual(source, "weight_balance")
        self.assertIsNotNone(cg)
        assert cg is not None
        self.assertAlmostEqual(cg[0], 0.15, places=6)

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_lifting_line_direct_method(self) -> None:
        """Verify direct LiftingLine analysis execution."""
        engine = AeroSandboxEngine()
        components = _sample_components()
        cond = FlightCondition(velocity=25.0, alpha=4.0, alpha_steps=1)

        result = engine.analyze(components, cond, method=AnalysisMethod.LIFTING_LINE)
        self.assertEqual(result.method, AnalysisMethod.LIFTING_LINE)
        self.assertEqual(len(result.polar_points), 1)
        pt = result.polar_points[0]
        self.assertGreater(pt.cl, 0.0)
        self.assertGreater(pt.cd, 0.0)


if __name__ == "__main__":
    unittest.main()
