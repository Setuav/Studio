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
        self.assertIn("sections", env)
        self.assertEqual(len(env["sections"]), 2)
        sec0 = env["sections"][0]
        self.assertIn("corners_3d", sec0)
        self.assertEqual(len(sec0["corners_3d"]), 4)
        # Root chord 200 mm with NACA 2412: actual bounds should enclose camber
        z_b = sec0["z_bounds_mm"]
        self.assertLess(z_b[0], 0.0)
        self.assertGreater(z_b[1], 0.0)
        self.assertGreater(sec0["thickness_mm"], 20.0)

    def test_lifting_surface_clark_y_bounds(self) -> None:
        wing = {
            "id": "clark-wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 300.0,
                            "airfoil": "clark-y",
                        },
                        {
                            "position": {"x": 0.0, "y": 500.0, "z": 0.0},
                            "chord": 300.0,
                            "airfoil": "clark-y",
                        },
                    ],
                }
            },
        }
        env = compute_geometry_envelope(wing)
        self.assertIsNotNone(env)
        assert env is not None
        sec = env["sections"][0]
        self.assertIn("corners_3d", sec)
        # Clark-Y has asymmetric camber: top rises much higher than bottom
        z_b = sec["z_bounds_mm"]
        self.assertAlmostEqual(z_b[0], -9.08, delta=1.0)
        self.assertAlmostEqual(z_b[1], 27.48, delta=1.0)
        self.assertAlmostEqual(sec["thickness_mm"], 36.56, delta=1.0)

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

        # Size covers control surface chord plus sweep (from 125.7 to 183.3 mm -> ~57.7 mm)
        self.assertAlmostEqual(size["x"], 57.7, delta=1.0)
        # Offset X placed towards trailing edge of parent root chord
        self.assertGreater(offset["x"], 100.0)
        self.assertIn("sections", env)
        self.assertEqual(len(env["sections"]), 2)
        self.assertIn("corners_3d", env["sections"][0])

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

    def test_build_project_geometry_includes_envelopes(self) -> None:
        from plugins.geometry.viewport.scene import build_project_geometry
        from plugins.geometry.engine.fuselage_geometry import build_fuselage_geometry
        from plugins.geometry.engine.lifting_surface_geometry import build_lifting_surface_geometry
        from setuav_studio.project import ProjectDocument
        from pathlib import Path

        fuse = _sample_fuselage()
        wing = _sample_wing()
        sync_component_envelope(fuse)
        sync_component_envelope(wing)

        doc = ProjectDocument(Path("test.uav"), "uav", {"components": [fuse, wing]})
        providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }
        geom_data = build_project_geometry(doc, providers)
        self.assertGreater(len(geom_data.envelopes), 0)

        env_ids = [e.component_id for e in geom_data.envelopes]
        self.assertIn("test-fuse", env_ids)
        self.assertIn("test-wing", env_ids)

        fuse_env = next(e for e in geom_data.envelopes if e.component_id == "test-fuse")
        self.assertGreater(len(fuse_env.lines), 0)

    def test_build_envelope_wire_vertices_and_colors(self) -> None:
        from plugins.geometry.viewport.mesh import (
            ENVELOPE_HIGHLIGHT,
            build_envelope_wire_vertices,
        )
        from plugins.geometry.engine.data import EnvelopeWireGeometry, GeometryData

        env = EnvelopeWireGeometry(
            component_id="fuse-1",
            lines=(
                ((0.0, 0.0, 0.0), (100.0, 0.0, 0.0)),
                ((100.0, 0.0, 0.0), (100.0, 50.0, 0.0)),
            ),
        )
        data = GeometryData(envelopes=(env,))

        # Not selected -> empty
        self.assertEqual(build_envelope_wire_vertices(data, None), [])
        self.assertEqual(build_envelope_wire_vertices(data, "other"), [])

        # Selected -> returns line vertices with bright green color
        verts = build_envelope_wire_vertices(data, "fuse-1")
        # 2 lines * 2 vertices * 6 floats (x, y, z, r, g, b) = 24 floats
        self.assertEqual(len(verts), 24)
        # Check green channel
        self.assertAlmostEqual(verts[4], ENVELOPE_HIGHLIGHT[1], places=2)

    def test_workspace_selection_sets_envelope_in_viewer(self) -> None:
        from plugins.geometry.workspace import ViewerWorkspace
        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument
        from pathlib import Path

        api = StudioAPI()
        fuse = _sample_fuselage()
        sync_component_envelope(fuse)
        doc = ProjectDocument(Path("test.uav"), "uav", {"components": [fuse]})
        api.current_project = doc

        workspace = ViewerWorkspace(api)

        # 1. Select Envelope node in tree
        api.set_selection({
            "id": "test-fuse:envelope",
            "name": "Envelope",
            "kind": "envelope",
            "component_id": "test-fuse",
        })
        self.assertEqual(workspace.viewer._selected_envelope_component_id, "test-fuse")

        # 2. Select component itself -> envelope selection is cleared
        api.set_selection(fuse)
        self.assertIsNone(workspace.viewer._selected_envelope_component_id)

        # 3. Clear selection -> envelope selection is cleared
        api.set_selection(None)
        self.assertIsNone(workspace.viewer._selected_envelope_component_id)

    def test_lifting_surface_tip_cap_envelope_lines(self) -> None:
        from plugins.geometry.engine.transforms import identity_matrix
        from plugins.geometry.viewport.scene import _append_lifting_surface_tip_envelope_lines

        wing_round = _sample_wing(mirror=False)
        wing_round["parameters"]["geometry"]["tip_treatment"] = {
            "type": "round",
            "length": 25.0,
            "offset_x": 0.0,
        }

        lines_round: list[tuple[Any, Any]] = []
        _append_lifting_surface_tip_envelope_lines(lines_round, wing_round, identity_matrix())
        self.assertGreater(len(lines_round), 0)

        # Root rib is at Y=0, tip rib is at Y=600. Tip cap must extend to ~625 mm
        ys_round = [p[1] for line in lines_round for p in line]
        self.assertAlmostEqual(min(ys_round), 600.0, delta=1.0)
        self.assertAlmostEqual(max(ys_round), 625.0, delta=1.0)

        # Sharp tip cap
        wing_sharp = _sample_wing(mirror=False)
        wing_sharp["parameters"]["geometry"]["tip_treatment"] = {
            "type": "sharp",
            "length": 20.0,
            "offset_x": 0.0,
        }
        lines_sharp: list[tuple[Any, Any]] = []
        _append_lifting_surface_tip_envelope_lines(lines_sharp, wing_sharp, identity_matrix())
        self.assertGreater(len(lines_sharp), 0)
        ys_sharp = [p[1] for line in lines_sharp for p in line]
        self.assertAlmostEqual(min(ys_sharp), 600.0, delta=1.0)
        self.assertAlmostEqual(max(ys_sharp), 620.0, delta=1.0)

    def test_lifting_surface_winglet_envelope_lines(self) -> None:
        from plugins.geometry.engine.transforms import identity_matrix
        from plugins.geometry.viewport.scene import _append_lifting_surface_tip_envelope_lines

        wing_wl = _sample_wing(mirror=False)
        wing_wl["parameters"]["geometry"]["tip_treatment"] = {
            "type": "winglet",
            "winglet_height": 80.0,
            "cant_angle": 60.0,
        }
        lines: list[tuple[Any, Any]] = []
        _append_lifting_surface_tip_envelope_lines(lines, wing_wl, identity_matrix())
        self.assertGreater(len(lines), 0)
        # Tip rib is at Y=600, Z=30. Winglet extends upwards in Z and outwards in Y
        zs = [p[2] for line in lines for p in line]
        self.assertGreater(max(zs), 65.0)

    def test_control_surface_envelope_invariant_to_deflection(self) -> None:
        wing = _sample_wing(mirror=False)
        cs_0 = _sample_control_surface(parent_id="test-wing")
        cs_0["parameters"]["geometry"]["deflection"] = 0.0

        cs_20 = deepcopy(cs_0)
        cs_20["parameters"]["geometry"]["deflection"] = 20.0

        env_0 = compute_geometry_envelope(cs_0, wing)
        env_20 = compute_geometry_envelope(cs_20, wing)
        self.assertIsNotNone(env_0)
        self.assertIsNotNone(env_20)
        assert env_0 is not None and env_20 is not None

        # Envelope metadata must remain identical regardless of deflection!
        self.assertEqual(env_0["size_mm"], env_20["size_mm"])
        self.assertEqual(env_0["offset_mm"], env_20["offset_mm"])
        self.assertEqual(env_0["volume_mm3"], env_20["volume_mm3"])
        self.assertIn("hinge_axis", env_0)

        # Viewer rotation rotates the envelope wireframe
        from plugins.geometry.viewport.scene import _rotate_control_surface_envelope

        rotated_env = _rotate_control_surface_envelope(env_0, 20.0)
        sec0_corners = env_0["sections"][0]["corners_3d"]
        rot0_corners = rotated_env["sections"][0]["corners_3d"]
        # Corner Z coordinates should shift under rotation
        self.assertNotEqual(sec0_corners[1]["z"], rot0_corners[1]["z"])


if __name__ == "__main__":
    unittest.main()

