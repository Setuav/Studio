"""Tests for the lifting-surface layout: sections, the profiles built from them, wing formulas."""

from __future__ import annotations

import math
import unittest
from typing import Any

from plugins.geometry.engine.lifting_surface_layout import (
    append_section,
    apply_wing_formulas,
    build_profiles,
    delete_section,
    derive_profiles,
    layout_planform,
    set_overall_angle,
    set_planform,
    split_section,
)
from setuav_studio.model.expression import set_expression


def _section(
    span: float, sweep: float, dihedral: float, twist: float, tip_chord: float
) -> dict[str, Any]:
    return {
        "span": span,
        "sweep": sweep,
        "dihedral": dihedral,
        "twist": twist,
        "tip": {"chord": tip_chord, "airfoil": "0012"},
    }


def _geometry() -> dict[str, Any]:
    """A cranked wing: an inner section with little sweep, an outer one swept and tapered."""
    return {
        "sweep_location": 0.25,
        "planform": {"active_drivers": ["span", "root_chord", "tip_chord"]},
        "root": {"chord": 240.0, "airfoil": "2412"},
        "sections": [
            _section(300.0, 2.0, 1.0, -1.0, 200.0),
            _section(400.0, 15.0, 6.0, -2.0, 120.0),
        ],
    }


class LiftingSurfaceLayoutTests(unittest.TestCase):
    def test_profiles_chain_from_the_root_along_the_sections(self) -> None:
        geometry = _geometry()

        profiles = build_profiles(geometry["root"], geometry["sections"], 0.25)

        def tan(degrees: float) -> float:
            return math.tan(math.radians(degrees))

        # Each tip moves out by the span, aft by the sweep of the quarter-chord line
        # (corrected to the leading edge for the chord change) and up by the dihedral.
        x1 = 300.0 * tan(2.0) + 0.25 * (240.0 - 200.0)
        x2 = x1 + 400.0 * tan(15.0) + 0.25 * (200.0 - 120.0)
        z1 = 300.0 * tan(1.0)
        z2 = z1 + 400.0 * tan(6.0)
        expected = [(0.0, 0.0, 0.0, 240.0), (x1, 300.0, z1, 200.0), (x2, 700.0, z2, 120.0)]
        self.assertEqual(len(profiles), 3)
        for profile, (x, y, z, chord) in zip(profiles, expected, strict=True):
            self.assertAlmostEqual(profile["position"]["x"], x)
            self.assertAlmostEqual(profile["position"]["y"], y)
            self.assertAlmostEqual(profile["position"]["z"], z)
            self.assertAlmostEqual(profile["chord"], chord)
        self.assertEqual(profiles[0]["airfoil"], "2412")
        self.assertEqual(profiles[2]["rotation"], {"x": 0.0, "y": -3.0, "z": 0.0})

    def test_a_non_positive_span_or_chord_is_an_error(self) -> None:
        geometry = _geometry()
        geometry["sections"][1]["span"] = 0.0
        with self.assertRaisesRegex(ValueError, "Section 2 span must be positive"):
            build_profiles(geometry["root"], geometry["sections"], 0.25)
        geometry = _geometry()
        geometry["root"]["chord"] = -5.0
        with self.assertRaisesRegex(ValueError, "Root chord must be positive"):
            build_profiles(geometry["root"], geometry["sections"], 0.25)

    def test_span_spreads_over_the_sections_and_keeps_the_crank(self) -> None:
        geometry = _geometry()

        set_planform(geometry, {"span": 1400.0}, symmetric=False, y_offset=0.0)

        spans = [s["span"] for s in geometry["sections"]]
        self.assertAlmostEqual(spans[0], 600.0)
        self.assertAlmostEqual(spans[1], 800.0)
        self.assertEqual([s["sweep"] for s in geometry["sections"]], [2.0, 15.0])
        self.assertAlmostEqual(
            layout_planform(geometry, symmetric=False, y_offset=0.0)["span"], 1400.0
        )

    def test_a_mirrored_wing_spans_both_halves_and_the_root_offset(self) -> None:
        geometry = _geometry()

        set_planform(geometry, {"span": 1600.0}, symmetric=True, y_offset=100.0)

        self.assertAlmostEqual(sum(s["span"] for s in geometry["sections"]), 700.0)

    def test_inner_chords_keep_their_place_between_root_and_tip(self) -> None:
        geometry = _geometry()

        set_planform(
            geometry, {"root_chord": 280.0, "tip_chord": 80.0}, symmetric=False, y_offset=0.0
        )

        # The inner tip chord was 40/120 of the way from root to tip.
        self.assertAlmostEqual(geometry["root"]["chord"], 280.0)
        self.assertAlmostEqual(geometry["sections"][0]["tip"]["chord"], 280.0 - 200.0 / 3.0)
        self.assertAlmostEqual(geometry["sections"][1]["tip"]["chord"], 80.0)

    def test_overall_angles_move_every_section_and_keep_kinks(self) -> None:
        geometry = _geometry()
        tan = [math.tan(math.radians(s["sweep"])) for s in geometry["sections"]]

        set_overall_angle(geometry, "sweep", 20.0)
        set_overall_angle(geometry, "dihedral", 0.0)
        set_overall_angle(geometry, "twist", -6.0)

        planform = layout_planform(geometry, symmetric=False, y_offset=0.0)
        self.assertAlmostEqual(planform["sweep"], 20.0)
        self.assertAlmostEqual(planform["dihedral"], 0.0)
        self.assertAlmostEqual(planform["twist"], -6.0)
        new_tan = [math.tan(math.radians(s["sweep"])) for s in geometry["sections"]]
        self.assertAlmostEqual(new_tan[1] - new_tan[0], tan[1] - tan[0])
        # The extra washout follows the span: 3/7 inboard, 4/7 outboard.
        self.assertAlmostEqual(geometry["sections"][0]["twist"], -1.0 - 3.0 * 3.0 / 7.0)

    def test_wing_formulas_reach_the_profiles(self) -> None:
        geometry = _geometry()
        planform = geometry["planform"]
        planform["span"] = 1000.0
        set_expression(planform, "span", "SPAN")
        planform["dihedral"] = 4.0
        set_expression(planform, "dihedral", "DIH")

        derive_profiles(geometry, symmetric=False, y_offset=0.0)

        tip = geometry["profiles"][-1]["position"]
        self.assertAlmostEqual(tip["y"], 1000.0)
        self.assertAlmostEqual(tip["z"], 1000.0 * math.tan(math.radians(4.0)))

        # Deriving again changes nothing.
        before = [dict(s) for s in geometry["sections"]]
        derive_profiles(geometry, symmetric=False, y_offset=0.0)
        for got, want in zip(geometry["sections"], before, strict=True):
            self.assertAlmostEqual(got["span"], want["span"])
            self.assertAlmostEqual(got["dihedral"], want["dihedral"])

    def test_a_wing_formula_may_not_override_a_section_formula(self) -> None:
        geometry = _geometry()
        set_expression(geometry["sections"][0], "span", "INNER")
        geometry["planform"]["span"] = 1400.0
        set_expression(geometry["planform"], "span", "SPAN")

        with self.assertRaisesRegex(
            ValueError, "wing span formula would change the section 1 span formula"
        ):
            apply_wing_formulas(geometry, symmetric=False, y_offset=0.0)

    def test_split_append_and_delete_sections(self) -> None:
        geometry = _geometry()
        root, sections = geometry["root"], geometry["sections"]

        split_section(root, sections, 1)
        self.assertEqual([s["span"] for s in sections], [300.0, 200.0, 200.0])
        self.assertEqual(sections[1]["tip"], {"chord": 160.0, "airfoil": "0012"})
        self.assertEqual([s["twist"] for s in sections], [-1.0, -1.0, -1.0])

        append_section(sections)
        self.assertAlmostEqual(sections[-1]["span"], 160.0)
        self.assertAlmostEqual(sections[-1]["tip"]["chord"], 84.0)

        delete_section(sections, 0)
        self.assertEqual(len(sections), 3)
        for _ in range(2):
            delete_section(sections, 0)
        with self.assertRaisesRegex(ValueError, "at least one section"):
            delete_section(sections, 0)

    def test_splitting_a_section_with_a_span_formula_is_refused(self) -> None:
        geometry = _geometry()
        set_expression(geometry["sections"][0], "span", "INNER")

        with self.assertRaisesRegex(ValueError, "Section 1 span is a formula"):
            split_section(geometry["root"], geometry["sections"], 0)


if __name__ == "__main__":
    unittest.main()
