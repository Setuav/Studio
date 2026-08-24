"""Unit tests for 2D airfoil analysis, caching, and NeuralFoil integration."""
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

    def test_cache_key_includes_neuralfoil_configuration(self) -> None:
        base = _compute_cache_key("naca2412", 300_000, 0.05, [0.0, 4.0])
        float_equivalent = _compute_cache_key(
            "naca2412", 300_000.0, 0.05, [0.0, 4.0]
        )
        different_ncrit = _compute_cache_key(
            "naca2412", 300_000, 0.05, [0.0, 4.0], n_crit=7.0
        )
        different_model = _compute_cache_key(
            "naca2412", 300_000, 0.05, [0.0, 4.0], model_size="xlarge"
        )
        self.assertEqual(base, float_equivalent)
        self.assertNotEqual(base, different_ncrit)
        self.assertNotEqual(base, different_model)


@unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
class TestAirfoilEngine(unittest.TestCase):
    """Test 2D airfoil aerodynamic analysis with NeuralFoil and 3D solver integration."""

    def setUp(self) -> None:
        self.engine = AirfoilAnalysisEngine()

    def test_custom_airfoil_cache_identifier_uses_coordinates(self) -> None:
        af_a, ident_a = self.engine._resolve_airfoil(
            [(1.0, 0.0), (0.5, 0.1), (0.0, 0.0)]
        )
        af_b, ident_b = self.engine._resolve_airfoil(
            [(1.0, 0.0), (0.5, 0.2), (0.0, 0.0)]
        )
        self.assertNotEqual(ident_a, ident_b)
        self.assertEqual(af_a.name, "custom_airfoil")
        self.assertEqual(af_b.name, "custom_airfoil")

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
        self.assertIsNotNone(polar.points[0].top_transition)
        self.assertIsNotNone(polar.points[0].bottom_transition)
        self.assertEqual(polar.model_size, "large")

    def test_neuralfoil_configuration_is_preserved(self) -> None:
        polar = self.engine.analyze_airfoil(
            airfoil="naca2412",
            reynolds=350_000.0,
            alphas=[0.0, 4.0],
            mach=0.05,
            n_crit=7.0,
            model_size="medium",
            use_cache=False,
        )
        self.assertEqual(polar.n_crit, 7.0)
        self.assertEqual(polar.model_size, "medium")
        self.assertEqual(polar.backend_used, "neuralfoil (medium)")

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

    def test_2d_airfoil_analysis_on_surface_profile(self) -> None:
        """Verify AirfoilAnalysisEngine analyzes section airfoils on request."""
        engine_2d = AirfoilAnalysisEngine()
        polar = engine_2d.analyze_airfoil(
            airfoil="naca2412",
            reynolds=200_000,
            alphas=[-4.0, 0.0, 4.0, 8.0, 12.0],
            mach=0.07,
        )
        self.assertIsNotNone(polar)
        self.assertEqual(len(polar.points), 5)
        self.assertGreater(polar.cl_max, 0.8)


if __name__ == "__main__":
    unittest.main()
