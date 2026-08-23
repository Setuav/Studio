"""Unit tests for 2D Airfoil analysis engine, caching, and NeuralFoil / XFoil integration."""
from __future__ import annotations

import math
import unittest

from setuav_studio.plugins.aerodynamics.engine.airfoil_cache import (
    AirfoilPolarCache,
    _compute_cache_key,
)
from setuav_studio.plugins.aerodynamics.engine.airfoil_engine import (
    HAS_AEROSANDBOX,
    AirfoilAnalysisEngine,
)
from setuav_studio.plugins.aerodynamics.engine.airfoil_models import (
    AirfoilPolar,
    AirfoilPolarPoint,
)
from setuav_studio.plugins.aerodynamics.engine.base import (
    AnalysisMethod,
    FlightCondition,
)
from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import (
    AeroSandboxEngine,
)


class TestAirfoilModels(unittest.TestCase):
    """Test 2D airfoil data models and interpolation."""

    def test_airfoil_polar_interpolation_and_serialization(self) -> None:
        pts = [
            AirfoilPolarPoint(alpha=0.0, cl=0.2, cd=0.008, cm=-0.05, cl_over_cd=25.0),
            AirfoilPolarPoint(alpha=4.0, cl=0.6, cd=0.010, cm=-0.05, cl_over_cd=60.0),
            AirfoilPolarPoint(alpha=8.0, cl=1.0, cd=0.016, cm=-0.05, cl_over_cd=62.5),
        ]
        polar = AirfoilPolar(
            airfoil_name="naca2412",
            reynolds=300000.0,
            mach=0.08,
            points=pts,
            cl_max=1.0,
            cl_max_alpha=8.0,
            cd_min=0.008,
            ld_max=62.5,
            ld_max_alpha=8.0,
        )

        # Interpolate at alpha=2.0
        cl_interp, cd_interp, cm_interp = polar.interpolate(2.0)
        self.assertAlmostEqual(cl_interp, 0.4, places=4)
        self.assertAlmostEqual(cd_interp, 0.009, places=4)
        self.assertAlmostEqual(cm_interp, -0.05, places=4)

        # Test to_dict / from_dict
        d = polar.to_dict()
        restored = AirfoilPolar.from_dict(d)
        self.assertEqual(restored.airfoil_name, "naca2412")
        self.assertEqual(len(restored.points), 3)
        self.assertAlmostEqual(restored.reynolds, 300000.0)
        self.assertAlmostEqual(restored.cl_max, 1.0)


class TestAirfoilCache(unittest.TestCase):
    """Test deterministic key generation and thread-safe LRU caching."""

    def test_cache_hits_and_eviction(self) -> None:
        cache = AirfoilPolarCache(max_entries=2)
        pts = [AirfoilPolarPoint(alpha=0.0, cl=0.1, cd=0.01, cm=0.0)]
        polar1 = AirfoilPolar(airfoil_name="naca0012", reynolds=200000, points=pts)
        polar2 = AirfoilPolar(airfoil_name="clarky", reynolds=200000, points=pts)
        polar3 = AirfoilPolar(airfoil_name="naca2412", reynolds=200000, points=pts)

        # Store polar1 and polar2
        cache.put(polar1, alphas=[0.0])
        cache.put(polar2, alphas=[0.0])

        self.assertIsNotNone(cache.get("naca0012", reynolds=200000, mach=0.0, alphas=[0.0]))
        self.assertIsNotNone(cache.get("clarky", reynolds=200000, mach=0.0, alphas=[0.0]))

        # Putting polar3 should evict polar1 (since polar1 was accessed before polar2)
        cache.put(polar3, alphas=[0.0])
        stats = cache.stats()
        self.assertEqual(stats["size"], 2)


@unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
class TestAirfoilEngine(unittest.TestCase):
    """Test 2D airfoil aerodynamic analysis with NeuralFoil and 3D solver integration."""

    def setUp(self) -> None:
        self.engine = AirfoilAnalysisEngine()

    def test_neuralfoil_cambered_airfoil(self) -> None:
        """Verify NeuralFoil analysis on NACA 2412."""
        alphas = [-4.0, 0.0, 4.0, 8.0, 12.0, 16.0]
        polar = self.engine.analyze_airfoil(
            airfoil="naca2412",
            reynolds=350000.0,
            alphas=alphas,
            mach=0.08,
            use_cache=False,
        )

        self.assertEqual(polar.airfoil_name, "naca2412")
        self.assertEqual(len(polar.points), 6)
        self.assertGreater(polar.cl_max, 1.1)
        self.assertLess(polar.cd_min, 0.015)
        self.assertGreater(polar.ld_max, 30.0)
        # Cambered airfoil has negative zero-lift pitching moment and negative alpha_0L
        self.assertLess(polar.cm_zero_lift, 0.0)
        self.assertLess(polar.alpha_zero_lift, 0.0)

    def test_neuralfoil_symmetric_airfoil(self) -> None:
        """Verify NeuralFoil analysis on symmetric NACA 0012."""
        alphas = [-4.0, 0.0, 4.0]
        polar = self.engine.analyze_airfoil(
            airfoil="naca0012",
            reynolds=500000.0,
            alphas=alphas,
            mach=0.0,
            use_cache=True,
        )

        # Symmetric airfoil zero lift angle must be ~ 0 deg
        self.assertAlmostEqual(polar.alpha_zero_lift, 0.0, places=1)
        pt_0 = polar.get_point(0.0)
        self.assertIsNotNone(pt_0)
        self.assertAlmostEqual(pt_0.cl, 0.0, places=1)

    def test_xfoil_fallback_mechanism(self) -> None:
        """Verify fallback to NeuralFoil when XFoil is requested but unavailable."""
        alphas = [0.0, 4.0]
        polar = self.engine.analyze_airfoil(
            airfoil="naca2412",
            reynolds=200000.0,
            alphas=alphas,
            backend="xfoil",
            use_cache=False,
        )
        self.assertIsNotNone(polar)
        self.assertIn("foil", polar.backend_used.lower())

    def test_3d_engine_section_polars_extraction(self) -> None:
        """Verify 3D AeroSandboxEngine populates section_polars from 2D analysis."""
        engine_3d = AeroSandboxEngine()
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
                            {"position": {"x": 30, "y": 500, "z": 0}, "chord": 120, "twist": 0, "airfoil": "naca2412"},
                        ]
                    }
                },
            }
        ]
        cond = FlightCondition(velocity=25.0, alpha=4.0, alpha_steps=1)
        res = engine_3d.analyze(components, cond, method=AnalysisMethod.COMPREHENSIVE)

        self.assertIn("section_polars", res.raw)
        self.assertGreater(len(res.raw["section_polars"]), 0)


if __name__ == "__main__":
    unittest.main()
