"""Unit tests for parametric sweep infrastructure (Alpha, Beta, Control Deflections, Velocity, Altitude, and Multi-grids)."""
from __future__ import annotations

import math
import unittest

from setuav_studio.plugins.aerodynamics.engine.base import (
    AnalysisMethod,
    FlightCondition,
    MultiDimensionalSweepResult,
    PolarPoint,
    SweepType,
    SweepVariable,
)
from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import (
    HAS_AEROSANDBOX,
    AeroSandboxEngine,
)


class TestSweepConfiguration(unittest.TestCase):
    """Test FlightCondition sweep configuration and range calculations."""

    def test_flight_condition_sweep_values(self) -> None:
        cond = FlightCondition(
            sweep_type=SweepType.ALPHA,
            sweep_variable="alpha",
            sweep_min=-4.0,
            sweep_max=16.0,
            sweep_steps=5,
        )
        vals = cond.get_primary_sweep_values()
        self.assertEqual(len(vals), 5)
        self.assertAlmostEqual(vals[0], -4.0)
        self.assertAlmostEqual(vals[-1], 16.0)

        # Dual Alpha + Beta sweep values
        dual_cond = FlightCondition(
            sweep_type=SweepType.DUAL_ALPHA_BETA,
            sweep_variable="alpha",
            sweep_min=-4.0,
            sweep_max=8.0,
            sweep_steps=4,
            secondary_variable="beta",
            secondary_min=-10.0,
            secondary_max=10.0,
            secondary_steps=3,
        )
        p_vals = dual_cond.get_primary_sweep_values()
        s_vals = dual_cond.get_secondary_sweep_values()
        self.assertEqual(len(p_vals), 4)
        self.assertEqual(len(s_vals), 3)

    def test_sweep_serialization(self) -> None:
        cond = FlightCondition(
            sweep_type=SweepType.CONTROL_DEFLECTION,
            sweep_variable="elevator",
            sweep_min=-15.0,
            sweep_max=15.0,
            sweep_steps=7,
        )
        d = cond.to_dict()
        self.assertEqual(d["sweep_type"], "control_deflection")
        self.assertEqual(d["sweep_variable"], "elevator")

        restored = FlightCondition.from_dict(d)
        self.assertEqual(restored.sweep_type, SweepType.CONTROL_DEFLECTION)
        self.assertEqual(restored.sweep_variable, "elevator")
        self.assertAlmostEqual(restored.sweep_min, -15.0)


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
                            {"position": {"x": 0, "y": 0, "z": 0}, "chord": 200, "twist": 0, "airfoil": "naca2412"},
                            {"position": {"x": 30, "y": 500, "z": 0}, "chord": 140, "twist": 0, "airfoil": "naca2412"},
                        ]
                    }
                },
            },
            {
                "id": "htail-1",
                "name": "Horizontal Tail",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {
                    "tags": ["elevator"],
                    "geometry": {
                        "mirror": True,
                        "profiles": [
                            {"position": {"x": 500, "y": 0, "z": 50}, "chord": 100, "twist": 0, "airfoil": "naca0012"},
                            {"position": {"x": 520, "y": 180, "z": 50}, "chord": 80, "twist": 0, "airfoil": "naca0012"},
                        ]
                    }
                },
            },
            {
                "id": "vfin-1",
                "name": "Vertical Fin",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {
                    "tags": ["rudder"],
                    "geometry": {
                        "mirror": False,
                        "profiles": [
                            {"position": {"x": 480, "y": 0, "z": 0}, "chord": 120, "twist": 0, "airfoil": "naca0012"},
                            {"position": {"x": 510, "y": 0, "z": 150}, "chord": 80, "twist": 0, "airfoil": "naca0012"},
                        ]
                    }
                },
            },
        ]

    def test_beta_sideslip_sweep(self) -> None:
        """Verify sideslip sweep produces consistent sideforce CY and directional yaw moment Cn."""
        cond = FlightCondition(
            velocity=20.0,
            alpha=2.0,
            sweep_type=SweepType.BETA,
            sweep_variable="beta",
            sweep_min=-10.0,
            sweep_max=10.0,
            sweep_steps=5,
        )
        res = self.engine.analyze(self.components, cond, method=AnalysisMethod.COMPREHENSIVE)

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
            sweep_type=SweepType.CONTROL_DEFLECTION,
            sweep_variable="elevator",
            sweep_min=-10.0,
            sweep_max=10.0,
            sweep_steps=5,
        )
        res = self.engine.analyze(self.components, cond, method=AnalysisMethod.COMPREHENSIVE)

        self.assertEqual(len(res.polar_points), 5)
        # Elevator deflection down (+10 deg) causes nose-down pitch (negative Cm)
        # Elevator deflection up (-10 deg) causes nose-up pitch (positive Cm)
        cm_up = res.polar_points[0].cm    # delta_e = -10 deg
        cm_down = res.polar_points[-1].cm  # delta_e = +10 deg
        self.assertGreater(cm_up, cm_down)

    def test_dual_alpha_beta_sweep(self) -> None:
        """Verify dual alpha+beta sweep computes both alpha and beta datasets simultaneously."""
        cond = FlightCondition(
            sweep_type=SweepType.DUAL_ALPHA_BETA,
            alpha=2.0,
            beta=0.0,
            alpha_min=-4.0,
            alpha_max=8.0,
            alpha_steps=3,
            beta_min=-6.0,
            beta_max=6.0,
            beta_steps=3,
        )
        res = self.engine.analyze(self.components, cond, method=AnalysisMethod.AERO_BUILDUP)

        self.assertEqual(len(res.polar_points), 6)  # 3 alpha points + 3 beta points

        alpha_pts = res.polar_points[:3]
        beta_pts = res.polar_points[3:]

        self.assertEqual(len(alpha_pts), 3)
        self.assertEqual(len(beta_pts), 3)

        # Verify alpha points vary alpha with fixed beta
        self.assertAlmostEqual(alpha_pts[0].alpha, -4.0)
        self.assertAlmostEqual(alpha_pts[-1].alpha, 8.0)
        self.assertAlmostEqual(alpha_pts[0].beta, 0.0)

        # Verify beta points vary beta with fixed alpha
        self.assertAlmostEqual(beta_pts[0].beta, -6.0)
        self.assertAlmostEqual(beta_pts[-1].beta, 6.0)
        self.assertAlmostEqual(beta_pts[0].alpha, 2.0)


if __name__ == "__main__":
    unittest.main()
