"""Unit tests for geometry-derived physical envelope computation and synchronization."""

from __future__ import annotations

import unittest
from copy import deepcopy
from typing import Any

from plugins.geometry.engine.envelope import (
    GEOMETRY_COMPONENT_TYPES,
    compute_geometry_envelope,
    sync_component_envelope,
    sync_project_geometry_envelopes,
)
from setuav_studio.ui.editor.envelope import EnvelopeEditor
from tests._common import TEST_PROJECT_PATH, get_qapp


def _sample_wing(mirror: bool = True) -> dict[str, Any]:
    return {
        "id": "test-wing",
        "name": "Test Wing",
        "type": "org.setuav.core:lifting-surface",
        "parameters": {
            "geometry": {
                "mirror": mirror,
                "symmetric": mirror,
                "profiles": [
                    {
                        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "chord": 200.0,
                        "airfoil": "naca2412",
                    },
                    {
                        "position": {"x": 50.0, "y": 600.0, "z": 30.0},
                        "chord": 100.0,
                        "airfoil": "naca2412",
                    },
                ],
            }
        },
    }


def _sample_fuselage() -> dict[str, Any]:
    return {
        "id": "test-fuse",
        "name": "Test Fuselage",
        "type": "org.setuav.core:fuselage",
        "parameters": {
            "geometry": {
                "segments": [
                    {
                        "tag": "main",
                        "sections": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 40.0},
                            },
                            {
                                "position": {"x": 300.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 120.0},
                            },
                            {
                                "position": {"x": 800.0, "y": 0.0, "z": 10.0},
                                "profile": {"type": "circle", "diameter": 30.0},
                            },
                        ],
                    }
                ]
            }
        },
    }


def _sample_control_surface(parent_id: str = "test-wing") -> dict[str, Any]:
    return {
        "id": "test-aileron",
        "name": "Test Aileron",
        "type": "org.setuav.core:control-surface",
        "parent": parent_id,
        "attach_to": parent_id,
        "parameters": {
            "geometry": {
                "tag": "aileron",
                "type": "aileron",
                "span_start": 200.0,
                "span_end": 500.0,
                "chord": 45.0,
                "chord_fraction": 0.25,
            }
        },
    }


class GeometryEnvelopeTests(unittest.TestCase):
    def test_geometry_component_types_set(self) -> None:
        self.assertIn("org.setuav.core:lifting-surface", GEOMETRY_COMPONENT_TYPES)
        self.assertIn("org.setuav.core:fuselage", GEOMETRY_COMPONENT_TYPES)
        self.assertIn("org.setuav.core:control-surface", GEOMETRY_COMPONENT_TYPES)

    def test_mirrored_lifting_surface_envelope(self) -> None:
        wing = _sample_wing(mirror=True)
        env = compute_geometry_envelope(wing)
        self.assertIsNotNone(env)
        assert env is not None

        self.assertEqual(env["shape"], "box")
        size = env["size_mm"]
        offset = env["offset_mm"]

        # Mirrored wing: span is 2 * 600 = 1200 mm, offset_y is centered at 0.0
        self.assertAlmostEqual(size["y"], 1200.0, delta=5.0)
        self.assertEqual(offset["y"], 0.0)

        # X size covers root chord (200) plus sweep (50 + 100)
        self.assertGreaterEqual(size["x"], 200.0)
        self.assertGreater(offset["x"], 0.0)

        # Z size covers dihedral (30) plus airfoil thickness (~24)
        self.assertGreaterEqual(size["z"], 30.0)

    def test_non_mirrored_lifting_surface_envelope(self) -> None:
        fin = _sample_wing(mirror=False)
        env = compute_geometry_envelope(fin)
        self.assertIsNotNone(env)
        assert env is not None

        self.assertEqual(env["shape"], "box")
        size = env["size_mm"]
        offset = env["offset_mm"]

        # Non-mirrored: Y spans from 0 to 600 mm
        self.assertAlmostEqual(size["y"], 600.0, delta=5.0)
        # Trapezoidal panel volumetric centroid shifts towards the root chord (200 vs 100 mm)
        self.assertAlmostEqual(offset["y"], 235.7, delta=2.0)
        self.assertGreater(env["volume_mm3"], 0.0)
        self.assertIn("unit_inertia", env)
        self.assertEqual(len(env["slices"]), 1)

    def test_fuselage_envelope(self) -> None:
        fuse = _sample_fuselage()
        env = compute_geometry_envelope(fuse)
        self.assertIsNotNone(env)
        assert env is not None

        self.assertEqual(env["shape"], "trapezoid")
        size = env["size_mm"]
        offset = env["offset_mm"]

        # Length from 0 to 800 mm
        self.assertAlmostEqual(size["x"], 800.0, delta=2.0)
        # True volumetric centroid from frustum slices: wider front section shifts CG forward to ~355.5 mm
        self.assertAlmostEqual(offset["x"], 355.5, delta=2.0)

        # Max diameter is 120 mm -> Y and Z size ~ 120 mm
        self.assertAlmostEqual(size["y"], 120.0, delta=2.0)
        self.assertAlmostEqual(size["z"], 120.0, delta=15.0)
        self.assertAlmostEqual(offset["y"], 0.0, delta=1.0)
        self.assertGreater(env["volume_mm3"], 0.0)
        self.assertIn("unit_inertia", env)
        self.assertIn("sections", env)
        self.assertEqual(len(env["sections"]), 3)
        self.assertEqual(env["sections"][0]["station_x_mm"], 0.0)
        self.assertEqual(env["sections"][1]["station_x_mm"], 300.0)
        self.assertEqual(env["sections"][2]["station_x_mm"], 800.0)
        self.assertEqual(len(env["slices"]), 2)

    def test_control_surface_envelope(self) -> None:
        parent = _sample_wing()
        cs = _sample_control_surface()
        env = compute_geometry_envelope(cs, parent)
        self.assertIsNotNone(env)
        assert env is not None

        self.assertEqual(env["shape"], "box")
        size = env["size_mm"]
        offset = env["offset_mm"]

        # Span from 200 to 500 mm -> width 300 mm, offset_y = 350 mm
        self.assertAlmostEqual(size["y"], 300.0, delta=1.0)
        self.assertAlmostEqual(offset["y"], 350.0, delta=1.0)

        # Chord = 45 mm
        self.assertAlmostEqual(size["x"], 45.0, delta=1.0)
        # Offset X placed towards trailing edge of parent root chord
        self.assertGreater(offset["x"], 100.0)

    def test_unsupported_component_returns_none(self) -> None:
        motor = {"id": "motor-1", "type": "org.setuav.core:motor"}
        self.assertIsNone(compute_geometry_envelope(motor))

    def test_sync_component_envelope(self) -> None:
        wing = _sample_wing()
        self.assertNotIn("envelope", wing)

        # First sync adds envelope
        changed = sync_component_envelope(wing)
        self.assertTrue(changed)
        self.assertIn("envelope", wing)
        self.assertEqual(wing["envelope"]["shape"], "box")

        # Second sync without changes returns False
        changed_again = sync_component_envelope(wing)
        self.assertFalse(changed_again)

    def test_sync_project_geometry_envelopes(self) -> None:
        wing = _sample_wing()
        fuse = _sample_fuselage()
        cs = _sample_control_surface()
        battery = {
            "id": "battery-1",
            "type": "org.setuav.core:battery",
            "envelope": {"shape": "box", "size_mm": {"x": 100, "y": 50, "z": 30}},
        }
        project_data = {
            "components": [fuse, wing, cs, battery],
        }

        count = sync_project_geometry_envelopes(project_data)
        self.assertEqual(count, 3)  # fuse, wing, cs updated; battery untouched
        self.assertIn("envelope", fuse)
        self.assertIn("envelope", wing)
        self.assertIn("envelope", cs)

    def test_empty_or_none_project_handled_safely(self) -> None:
        self.assertEqual(sync_project_geometry_envelopes(None), 0)
        self.assertEqual(sync_project_geometry_envelopes({}), 0)
        self.assertEqual(sync_project_geometry_envelopes({"components": "not-a-list"}), 0)


class EnvelopeEditorUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def test_envelope_editor_supports_trapezoid_and_volume(self) -> None:
        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument
        from pathlib import Path

        api = StudioAPI()
        fuse = _sample_fuselage()
        sync_component_envelope(fuse)
        doc = ProjectDocument(Path("test.uav"), "uav", {"components": [fuse]})
        api.current_project = doc

        editor = EnvelopeEditor(
            api,
            {"component_id": "test-fuse", "kind": "envelope"},
        )
        self.assertIsNotNone(editor.shape_combo)
        # Trapezoid option exists and is selected for fuselage
        self.assertEqual(editor.shape_combo.currentData(), "trapezoid")

        # Check volume returns exact integrated volume when present
        self.assertAlmostEqual(editor.volume_value(), fuse["envelope"]["volume_mm3"], places=1)

        # Invalidate volume_mm3 to test cylinder formula
        fuse["envelope"].pop("volume_mm3", None)
        idx = editor.shape_combo.findData("cylinder")
        editor.shape_combo.setCurrentIndex(idx)
        expected_box_vol = (
            fuse["envelope"]["size_mm"]["x"]
            * fuse["envelope"]["size_mm"]["y"]
            * fuse["envelope"]["size_mm"]["z"]
        )
        expected_cyl_vol = expected_box_vol * 0.7853981633974483
        self.assertAlmostEqual(editor.volume_value(), expected_cyl_vol, delta=100.0)

    def test_envelope_editor_populates_sections_table(self) -> None:
        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument
        from pathlib import Path
        from PySide6.QtCore import Qt

        api = StudioAPI()
        fuse = _sample_fuselage()
        sync_component_envelope(fuse)
        doc = ProjectDocument(Path("test.uav"), "uav", {"components": [fuse]})
        api.current_project = doc

        editor = EnvelopeEditor(
            api,
            {"component_id": "test-fuse", "kind": "envelope"},
        )
        self.assertFalse(editor._sections_container.isHidden())
        self.assertEqual(editor.sections_table.rowCount(), 3)
        self.assertEqual(
            editor.sections_table.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(
            editor.sections_table.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(editor.sections_table.height(), 23 + 3 * 23 + 2)
        self.assertIn("0.0", editor.sections_table.item(0, 0).text())
        self.assertIn("300.0", editor.sections_table.item(1, 0).text())
        self.assertIn("800.0", editor.sections_table.item(2, 0).text())


if __name__ == "__main__":
    unittest.main()
