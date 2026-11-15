"""Unit tests for parametric sweep infrastructure (Alpha, Beta, Control Deflections, Velocity, Altitude, and Multi-grids)."""

from __future__ import annotations

import unittest

from plugins.aerodynamics.engine.aerosandbox_engine import (
    HAS_AEROSANDBOX,
    AeroSandboxEngine,
)
from plugins.aerodynamics.engine.base import (
    AnalysisMethod,
    FlightCondition,
    SweepType,
    control_channels_for_components,
)


class TestSweepConfiguration(unittest.TestCase):
    """Test FlightCondition sweep configuration and range calculations."""

    def test_flight_condition_sweep_values(self) -> None:
        cond = FlightCondition(
            sweep_variable="alpha",
            sweep_min=-4.0,
            sweep_max=16.0,
            sweep_steps=5,
        )
        self.assertEqual(cond.sweep_type, SweepType.ALPHA)
        vals = cond.sweep_values()
        self.assertEqual(len(vals), 5)
        self.assertAlmostEqual(vals[0], -4.0)
        self.assertAlmostEqual(vals[-1], 16.0)

        single = FlightCondition(
            alpha=3.5,
            sweep_variable="alpha",
            sweep_steps=1,
        )
        self.assertEqual(single.sweep_values(), [3.5])

    def test_sweep_serialization(self) -> None:
        cond = FlightCondition(
            sweep_variable="elevator",
            sweep_min=-15.0,
            sweep_max=15.0,
            sweep_steps=7,
        )
        d = cond.to_dict()
        self.assertNotIn("sweep_type", d)
        self.assertEqual(d["sweep_variable"], "elevator")

        restored = FlightCondition.from_dict(d)
        self.assertEqual(restored.sweep_type, SweepType.CONTROL_DEFLECTION)
        self.assertEqual(restored.sweep_variable, "elevator")
        self.assertAlmostEqual(restored.sweep_min, -15.0)
        self.assertEqual(FlightCondition(sweep_variable="alpha").sweep_type, SweepType.ALPHA)
        self.assertEqual(FlightCondition(sweep_variable="beta").sweep_type, SweepType.BETA)

    def test_composite_surfaces_expose_canonical_control_channels(self) -> None:
        components = [
            {
                "id": "left-elevon",
                "name": "left-elevon",
                "type": "org.setuav.core:control-surface",
                "parameters": {"geometry": {"type": "elevon"}},
            },
            {
                "id": "right-ruddervator",
                "name": "right-ruddervator",
                "type": "org.setuav.core:control-surface",
                "parameters": {"geometry": {"type": "ruddervator"}},
            },
        ]
        self.assertEqual(
            control_channels_for_components(components),
            ("elevator", "aileron", "rudder"),
        )


@unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
class TestParametricSweeps(unittest.TestCase):
    """Test parametric sweep execution across flight mechanics states."""

    def setUp(self) -> None:
        self.engine = AeroSandboxEngine()
        # Aircraft with main wing, horizontal tail with elevator, and vertical fin
        self.components = [
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
                                "position": {"x": 30, "y": 500, "z": 0},
                                "chord": 140,
                                "twist": 0,
                                "airfoil": "naca2412",
                            },
                        ],
                    }
                },
            },
            {
                "id": "htail-1",
                "name": "Horizontal Tail",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "profiles": [
                            {
                                "position": {"x": 500, "y": 0, "z": 50},
                                "chord": 100,
                                "twist": 0,
                                "airfoil": "naca0012",
                            },
                            {
                                "position": {"x": 520, "y": 180, "z": 50},
                                "chord": 80,
                                "twist": 0,
                                "airfoil": "naca0012",
                            },
                        ],
                    },
                },
            },
            {
                "id": "vfin-1",
                "name": "Vertical Fin",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {
                    "geometry": {
                        "mirror": False,
                        "profiles": [
                            {
                                "position": {"x": 480, "y": 0, "z": 0},
                                "chord": 120,
                                "twist": 0,
                                "airfoil": "naca0012",
                            },
                            {
                                "position": {"x": 510, "y": 0, "z": 150},
                                "chord": 80,
                                "twist": 0,
                                "airfoil": "naca0012",
                            },
                        ],
                    },
                },
            },
            {
                "id": "elevator-1",
                "name": "Elevator",
                "type": "org.setuav.core:control-surface",
                "parent": "htail-1",
                "parameters": {
                    "geometry": {
                        "type": "elevator",
                        "eta_start": 0.0,
                        "eta_end": 1.0,
                        "chord_fraction": 0.35,
                        "symmetry_mode": "symmetric",
                    }
                },
            },
            {
                "id": "rudder-1",
                "name": "Rudder",
                "type": "org.setuav.core:control-surface",
                "parent": "vfin-1",
                "parameters": {
                    "geometry": {
                        "type": "rudder",
                        "eta_start": 0.0,
                        "eta_end": 1.0,
                        "chord_fraction": 0.35,
                        "symmetry_mode": "symmetric",
                    }
                },
            },
        ]

    def test_beta_sideslip_sweep(self) -> None:
        """Verify sideslip sweep produces consistent sideforce CY and directional yaw moment Cn."""
        cond = FlightCondition(
            velocity=20.0,
            alpha=2.0,
            sweep_variable="beta",
            sweep_min=-10.0,
            sweep_max=10.0,
            sweep_steps=5,
        )
        res = self.engine.analyze(self.components, cond, method=AnalysisMethod.AERO_BUILDUP)

        self.assertEqual(len(res.polar_points), 5)
        self.assertIsNotNone(res.sweep_result)

        # Check points at beta=-10 and beta=+10
        pt_neg = res.polar_points[0]
        pt_pos = res.polar_points[-1]

        self.assertAlmostEqual(pt_neg.beta, -10.0)
        self.assertAlmostEqual(pt_pos.beta, 10.0)

        # Positive sideslip (wind from right) produces negative sideforce CY
        self.assertGreater(pt_neg.cy, pt_pos.cy)
        # Vertical fin directional restoring moment (Cn_beta > 0) -> Cn(beta=+10) > Cn(beta=-10)
        self.assertGreater(pt_pos.cn, pt_neg.cn)

    def test_control_deflection_sweep(self) -> None:
        """Verify elevator deflection sweep produces pitching moment control derivative."""
        cond = FlightCondition(
            velocity=20.0,
            alpha=2.0,
            sweep_variable="elevator",
            sweep_min=-10.0,
            sweep_max=10.0,
            sweep_steps=5,
        )
        res = self.engine.analyze(self.components, cond, method=AnalysisMethod.AERO_BUILDUP)

        self.assertEqual(len(res.polar_points), 5)
        self.assertIsNotNone(res.control_analysis)
        self.assertEqual(res.control_analysis.channel, "elevator")
        self.assertEqual(res.control_analysis.sample_count, 5)
        self.assertLess(res.control_analysis.derivatives_per_deg["Cm"], 0.0)
        self.assertGreater(res.control_analysis.linearity_r2["Cm"], 0.9)
        # Elevator deflection down (+10 deg) causes nose-down pitch (negative Cm)
        # Elevator deflection up (-10 deg) causes nose-up pitch (positive Cm)
        cm_up = res.polar_points[0].cm  # delta_e = -10 deg
        cm_down = res.polar_points[-1].cm  # delta_e = +10 deg
        self.assertGreater(cm_up, cm_down)

    def test_surface_name_cannot_be_used_as_control_analysis_channel(self) -> None:
        cond = FlightCondition(
            velocity=20.0,
            alpha=2.0,
            sweep_variable="left-elevator",
            sweep_min=-10.0,
            sweep_max=10.0,
            sweep_steps=3,
        )
        with self.assertRaisesRegex(ValueError, "surface name"):
            self.engine.analyze(
                self.components,
                cond,
                method=AnalysisMethod.AERO_BUILDUP,
            )


if __name__ == "__main__":
    unittest.main()
