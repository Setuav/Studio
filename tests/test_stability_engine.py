"""Unit tests for linear stability, control effectiveness, and elevator trim engine."""
from __future__ import annotations

import math
import unittest

from setuav_studio.plugins.aerodynamics.engine.base import (
    AnalysisMethod,
    FlightCondition,
    ReferenceValues,
)
from setuav_studio.plugins.aerodynamics.engine.stability_models import (
    ControlEffectiveness,
    ElevatorTrim,
    StabilityDerivatives,
)
from setuav_studio.plugins.aerodynamics.engine.stability_engine import (
    HAS_AEROSANDBOX,
    StabilityAnalysisEngine,
)
from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import AeroSandboxEngine


class TestStabilityModels(unittest.TestCase):
    """Test Stability models serialization and calculation logic."""

    def test_control_effectiveness_serialization(self) -> None:
        ctrl = ControlEffectiveness(
            control_tag="elevator",
            c_m_delta=-0.015,
            c_L_delta=0.008,
            c_D_delta=0.001,
        )
        d = ctrl.to_dict()
        self.assertEqual(d["control_tag"], "elevator")
        self.assertAlmostEqual(d["c_m_delta"], -0.015)

        restored = ControlEffectiveness.from_dict(d)
        self.assertEqual(restored.control_tag, "elevator")
        self.assertAlmostEqual(restored.c_m_delta, -0.015)

    def test_elevator_trim_serialization(self) -> None:
        trim = ElevatorTrim(
            alpha_ref=2.0,
            cm_0=0.05,
            cm_alpha=-0.02,
            cm_delta_e=-0.015,
            delta_e_trim=0.667,
            alpha_trim_neutral=2.5,
            cl_trim=0.45,
        )
        d = trim.to_dict()
        self.assertAlmostEqual(d["delta_e_trim"], 0.667)

        restored = ElevatorTrim.from_dict(d)
        self.assertAlmostEqual(restored.alpha_ref, 2.0)
        self.assertAlmostEqual(restored.delta_e_trim, 0.667)

    def test_stability_derivatives_serialization(self) -> None:
        sd = StabilityDerivatives(
            c_L_alpha_rad=4.8,
            c_L_alpha_deg=0.0838,
            c_m_alpha_rad=-1.2,
            c_m_alpha_deg=-0.0209,
            c_m_q=-12.5,
            c_n_beta_rad=0.08,
            c_l_beta_rad=-0.015,
            c_l_p=-0.45,
            c_n_r=-0.09,
            x_cg=0.05,
            x_np=0.09,
            static_margin=25.0,
            is_pitch_stable=True,
            is_pitch_damped=True,
            is_roll_stable=True,
            is_roll_damped=True,
            is_yaw_stable=True,
            is_yaw_damped=True,
            controls={
                "elevator": ControlEffectiveness(control_tag="elevator", c_m_delta=-0.015),
            },
            elevator_trim=ElevatorTrim(alpha_ref=2.0, delta_e_trim=0.5),
        )
        d = sd.to_dict()
        self.assertAlmostEqual(d["static_margin"], 25.0)
        self.assertTrue(d["is_pitch_stable"])
        self.assertIn("elevator", d["controls"])

        restored = StabilityDerivatives.from_dict(d)
        self.assertAlmostEqual(restored.c_m_alpha_rad, -1.2)
        self.assertAlmostEqual(restored.static_margin, 25.0)
        self.assertIsNotNone(restored.elevator_trim)


@unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
class TestStabilityAnalysisEngine(unittest.TestCase):
    """Test full 6-DoF stability and trim analysis engine."""

    def setUp(self) -> None:
        self.engine = AeroSandboxEngine()
        self.components = [
            {
                "id": "wing-1",
                "name": "Main Wing",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "control_surfaces": [
                            {"tag": "aileron", "type": "aileron", "eta_start": 0.6, "eta_end": 1.0, "chord_fraction": 0.25}
                        ],
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
                        "control_surfaces": [
                            {"tag": "elevator", "type": "elevator", "eta_start": 0.0, "eta_end": 1.0, "chord_fraction": 0.35}
                        ],
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
                        "control_surfaces": [
                            {"tag": "rudder", "type": "rudder", "eta_start": 0.0, "eta_end": 1.0, "chord_fraction": 0.35}
                        ],
                        "profiles": [
                            {"position": {"x": 480, "y": 0, "z": 0}, "chord": 120, "twist": 0, "airfoil": "naca0012"},
                            {"position": {"x": 510, "y": 0, "z": 150}, "chord": 80, "twist": 0, "airfoil": "naca0012"},
                        ]
                    }
                },
            },
        ]
        # Give the stability fixture an explicit forward CG so the native
        # static-margin sign is tested independently of geometry-only mass
        # derivation.
        self.components[0]["mass"] = 100000.0
        self.components[1]["mass"] = 100.0
        self.components[2]["mass"] = 100.0
        for component in self.components:
            component["extensions"] = {
                "org.setuav.weight-balance": {
                    "local_cg_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
                }
            }

    def test_stability_derivatives_computation(self) -> None:
        """Verify longitudinal and lateral-directional stability derivatives."""
        cond = FlightCondition(velocity=20.0, alpha=2.0, beta=0.0)
        res = self.engine.analyze(self.components, cond, method=AnalysisMethod.COMPREHENSIVE)

        self.assertIsNotNone(res.stability_derivatives)
        sd = res.stability_derivatives
        self.assertIsInstance(sd, StabilityDerivatives)

        # 1. Longitudinal derivatives
        self.assertGreater(sd.c_L_alpha_rad, 3.0)      # Realistic lift slope CLa ~ 4-5 /rad
        self.assertLess(sd.c_m_alpha_rad, 0.0)         # Pitch stable (Cma < 0)
        self.assertLess(sd.c_m_q, 0.0)                 # Pitch damped (Cmq < 0)
        self.assertTrue(sd.is_pitch_stable)
        self.assertTrue(sd.is_pitch_damped)

        # 2. Static Margin and Neutral point
        self.assertGreater(sd.x_np, sd.x_cg)           # Neutral point aft of CG
        self.assertGreater(sd.static_margin, 5.0)      # Positive static margin > 5%

        # 3. Lateral-Directional derivatives
        self.assertGreater(sd.c_n_beta_rad, 0.0)       # Directionally stable with vertical fin (Cnb > 0)
        self.assertLess(sd.c_l_p, 0.0)                 # Roll damped (Clp < 0)
        self.assertLess(sd.c_n_r, 0.0)                 # Yaw damped (Cnr < 0)
        self.assertTrue(sd.is_yaw_stable)
        self.assertTrue(sd.is_roll_damped)
        self.assertTrue(sd.is_yaw_damped)

        # 4. Control effectiveness
        self.assertIn("elevator", sd.controls)
        elev_eff = sd.controls["elevator"]
        self.assertLess(elev_eff.c_m_delta, 0.0)       # Downward deflection produces negative pitch moment

        # 5. Elevator trim
        self.assertIsNotNone(sd.elevator_trim)
        self.assertTrue(math.isfinite(sd.elevator_trim.delta_e_trim))
        self.assertTrue(math.isfinite(sd.elevator_trim.alpha_trim_neutral))


if __name__ == "__main__":
    unittest.main()
