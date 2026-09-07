"""Unit tests for concept preset models and default archetypes."""

from __future__ import annotations

import unittest

from plugins.geometry.concepts import (
    CONCEPT_PRESETS,
    CONVENTIONAL_TRACTOR,
    FLYING_WING,
    TALON_PUSHER,
    TWIN_BOOM_PUSHER,
    ConceptPreset,
    PlanformMetrics,
)


class ConceptModelsTests(unittest.TestCase):
    def test_all_archetype_presets_registered(self) -> None:
        expected_ids = {"talon_pusher", "conventional_tractor", "twin_boom_pusher", "flying_wing"}
        self.assertEqual(set(CONCEPT_PRESETS.keys()), expected_ids)

    def test_talon_pusher_proportions(self) -> None:
        p = TALON_PUSHER
        self.assertEqual(p.id, "talon_pusher")
        self.assertEqual(p.tail_type, "V-Tail")
        self.assertEqual(p.propulsion_layout, "Pusher")
        self.assertEqual(p.wingspan_mm, 1400.0)

        metrics = p.compute_metrics()
        self.assertIsInstance(metrics, PlanformMetrics)
        # S = 1.4 * (0.21 + 0.13) / 2 = 0.238 m2
        self.assertAlmostEqual(metrics.wing_area_m2, 0.238, places=3)
        self.assertAlmostEqual(metrics.aspect_ratio, 8.235, places=2)
        self.assertAlmostEqual(metrics.taper_ratio, 130.0 / 210.0, places=3)
        self.assertTrue(150.0 < metrics.mean_aerodynamic_chord_mm < 190.0)

    def test_conventional_tractor_proportions(self) -> None:
        p = CONVENTIONAL_TRACTOR
        self.assertEqual(p.id, "conventional_tractor")
        self.assertEqual(p.tail_type, "Conventional")
        self.assertEqual(p.propulsion_layout, "Tractor")
        self.assertEqual(p.wingspan_mm, 1600.0)

        metrics = p.compute_metrics()
        # S = 1.6 * (0.22 + 0.15) / 2 = 0.296 m2
        self.assertAlmostEqual(metrics.wing_area_m2, 0.296, places=3)
        self.assertAlmostEqual(metrics.aspect_ratio, 8.649, places=2)

    def test_twin_boom_pusher_proportions(self) -> None:
        p = TWIN_BOOM_PUSHER
        self.assertEqual(p.id, "twin_boom_pusher")
        self.assertEqual(p.tail_type, "Twin Boom")
        self.assertEqual(p.wingspan_mm, 1800.0)

        metrics = p.compute_metrics()
        # S = 1.8 * (0.24 + 0.16) / 2 = 0.360 m2
        self.assertAlmostEqual(metrics.wing_area_m2, 0.360, places=3)
        self.assertAlmostEqual(metrics.aspect_ratio, 9.0, places=2)

    def test_flying_wing_proportions(self) -> None:
        p = FLYING_WING
        self.assertEqual(p.id, "flying_wing")
        self.assertEqual(p.tail_type, "Winglets Only")
        self.assertEqual(p.wingspan_mm, 1200.0)
        self.assertEqual(p.wing_sweep_deg, 18.0)
        self.assertEqual(p.wing_airfoil, "MH 45")

        metrics = p.compute_metrics()
        # S = 1.2 * (0.30 + 0.16) / 2 = 0.276 m2
        self.assertAlmostEqual(metrics.wing_area_m2, 0.276, places=3)
        self.assertAlmostEqual(metrics.aspect_ratio, 5.217, places=2)

    def test_preset_to_dict(self) -> None:
        d = TALON_PUSHER.to_dict()
        self.assertEqual(d["concept_id"], "talon_pusher")
        self.assertIn("wingspan_mm", d)
        self.assertIn("wing_root_chord_mm", d)
        self.assertIn("fuselage_length_mm", d)
        self.assertIn("tail_arm_mm", d)
