"""Unit tests for geometry-derived physical envelope computation and synchronization."""

from __future__ import annotations

import math
import unittest
from copy import deepcopy
from typing import Any

from plugins.geometry.engine.airfoil import AIRFOILS_DATA_DIR, parse_airfoil_dat
from plugins.geometry.engine.envelope import (
    GEOMETRY_COMPONENT_TYPES,
    compute_geometry_envelope,
    sync_component_envelope,
    sync_project_geometry_envelopes,
)
from plugins.geometry.engine.fuselage_geometry import sample_profile
from setuav_studio.ui.editor.envelope import EnvelopeEditor
from tests._common import get_qapp, table_item


def _sample_wing(mirror: bool = True) -> dict[str, Any]:
    return {
        "id": "test-wing",
        "name": "Test Wing",
        "type": "org.setuav.core:lifting-surface",
        "parameters": {
            "geometry": {
                "mirror": mirror,
                "profiles": [
                    {
                        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "chord": 200.0,
                        "airfoil": "2412",
                    },
                    {
                        "position": {"x": 50.0, "y": 600.0, "z": 30.0},
                        "chord": 100.0,
                        "airfoil": "2412",
                    },
                ],
            }
        },
    }


def _clark_y_airfoil() -> dict[str, Any]:
    _, points = parse_airfoil_dat((AIRFOILS_DATA_DIR / "clarky.dat").read_text(encoding="utf-8"))
    return {"type": "coordinates", "name": "Clark-Y", "points": [[x, z] for x, z in points]}


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
        "parameters": {
            "geometry": {
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
        clark_y = _clark_y_airfoil()
        wing = {
            "id": "clark-wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 300.0,
                            "airfoil": clark_y,
                        },
                        {
                            "position": {"x": 0.0, "y": 500.0, "z": 0.0},
                            "chord": 300.0,
                            "airfoil": clark_y,
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

        # Span from 200 to 500 mm -> width 300 mm. The wing tapers, so the section
        # area at 500 mm is 0.49 of that at 200 mm and the volume centroid of the
        # prismatoid sits 0.442 of the span out: y = 200 + 0.442 * 300.
        self.assertAlmostEqual(size["y"], 300.0, delta=1.0)
        self.assertAlmostEqual(offset["y"], 332.5, delta=0.5)

        # Size covers control surface chord plus sweep (from 125.7 to 183.3 mm -> ~57.7 mm)
        self.assertAlmostEqual(size["x"], 57.7, delta=1.0)
        # Offset X placed towards trailing edge of parent root chord
        self.assertGreater(offset["x"], 100.0)
        self.assertIn("sections", env)
        self.assertEqual(len(env["sections"]), 2)
        self.assertIn("corners_3d", env["sections"][0])

    def test_control_surface_mass_properties_follow_its_section(self) -> None:
        wing = {
            "id": "rect-wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "mirror": False,
                    "profiles": [
                        {"position": {"x": 0, "y": y, "z": 0}, "chord": 200.0, "airfoil": "0012"}
                        for y in (0.0, 600.0)
                    ],
                }
            },
        }
        control = _sample_control_surface("rect-wing")
        env = compute_geometry_envelope(control, wing)
        assert env is not None
        hinge = env["sections"][0]["x_bounds_mm"][0] / 200.0

        # Aft NACA 0012 section from the hinge, integrated from the thickness formula.
        def half_thickness(x: float) -> float:
            return 0.6 * (
                0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4
            )

        steps = 4000
        stations = [hinge + (1.0 - hinge) * (k + 0.5) / steps for k in range(steps)]
        width = (1.0 - hinge) / steps
        area = sum(2.0 * half_thickness(x) for x in stations) * width * 200.0**2
        centroid = sum(x * 2.0 * half_thickness(x) for x in stations) * width * 200.0**3 / area

        self.assertAlmostEqual(env["volume_mm3"], area * 300.0, delta=0.03 * area * 300.0)
        self.assertAlmostEqual(env["offset_mm"]["x"], centroid, delta=2.0)
        self.assertAlmostEqual(env["offset_mm"]["y"], 350.0, delta=0.1)

    def test_polygon_section_bbox_is_measured_from_profile(self) -> None:
        fuse = _sample_fuselage()
        sections = fuse["parameters"]["geometry"]["segments"][0]["sections"]
        profile = {
            "type": "polygon",
            "vertices": [
                {"y": -30.0, "z": -20.0, "radius": 0.0},
                {"y": 50.0, "z": -20.0, "radius": 0.0},
                {"y": 10.0, "z": 80.0, "radius": 0.0},
            ],
        }
        sections[1]["profile"] = profile
        env = compute_geometry_envelope(fuse)
        assert env is not None
        bbox = env["sections"][1]

        # Bounds are those of the lofted outline, which is off-centre in both axes
        outline = sample_profile(profile)
        ys = [p[0] for p in outline]
        zs = [p[1] for p in outline]
        self.assertAlmostEqual(min(ys), -30.0, delta=2.0)
        self.assertAlmostEqual(max(zs), 80.0, delta=5.0)
        self.assertEqual(bbox["y_bounds_mm"], [round(min(ys), 2), round(max(ys), 2)])
        self.assertEqual(bbox["z_bounds_mm"], [round(min(zs), 2), round(max(zs), 2)])

    def test_invalid_fuselage_profile_raises(self) -> None:
        fuse = _sample_fuselage()
        sections = fuse["parameters"]["geometry"]["segments"][0]["sections"]
        sections[1]["profile"] = {"type": "hexagon", "width": 120.0}
        with self.assertRaises(ValueError):
            compute_geometry_envelope(fuse)

    def test_non_positive_chord_raises(self) -> None:
        wing = _sample_wing()
        wing["parameters"]["geometry"]["profiles"][1]["chord"] = 0.0
        with self.assertRaisesRegex(ValueError, "chord must be positive"):
            compute_geometry_envelope(wing)

    def test_lifting_surface_without_two_profiles_has_no_envelope(self) -> None:
        wing = _sample_wing()
        wing["parameters"]["geometry"]["profiles"] = wing["parameters"]["geometry"]["profiles"][:1]
        self.assertIsNone(compute_geometry_envelope(wing))

    def test_control_surface_without_parent_surface_has_no_envelope(self) -> None:
        cs = _sample_control_surface()
        self.assertIsNone(compute_geometry_envelope(cs))
        self.assertIsNone(compute_geometry_envelope(cs, _sample_fuselage()))
        self.assertFalse(sync_component_envelope(cs))
        self.assertNotIn("envelope", cs)

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

    def test_geometry_envelope_is_read_only_with_integrated_volume(self) -> None:
        from pathlib import Path

        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument

        api = StudioAPI()
        fuse = _sample_fuselage()
        sync_component_envelope(fuse)
        doc = ProjectDocument(Path("test.json"), "json", {"components": [fuse]})
        api._host.set_project(doc)

        editor = EnvelopeEditor(api, fuse)
        assert editor.shape_combo is not None
        self.assertEqual(editor.shape_combo.currentData(), "trapezoid")
        self.assertFalse(editor.shape_combo.isEnabled())
        self.assertFalse(editor.dimension_spins["x"].isEnabled())
        self.assertAlmostEqual(editor.volume_value(), fuse["envelope"]["volume_mm3"], places=1)

    def test_defined_envelope_volume_follows_its_shape(self) -> None:
        import math
        from pathlib import Path

        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument

        api = StudioAPI()
        battery = {
            "id": "battery",
            "type": "org.setuav.core:battery",
            "envelope": {
                "shape": "box",
                "size_mm": {"x": 140.0, "y": 45.0, "z": 30.0},
                "offset_mm": {"x": 70.0, "y": 0.0, "z": 0.0},
            },
        }
        doc = ProjectDocument(Path("test.json"), "json", {"components": [battery]})
        api._host.set_project(doc)

        editor = EnvelopeEditor(api, battery)
        assert editor.shape_combo is not None
        self.assertTrue(editor.shape_combo.isEnabled())
        self.assertEqual(editor.shape_combo.findData("trapezoid"), -1)
        box_volume = 140.0 * 45.0 * 30.0
        self.assertAlmostEqual(editor.volume_value(), box_volume, places=1)

        editor.shape_combo.setCurrentIndex(editor.shape_combo.findData("cylinder"))
        self.assertEqual(battery["envelope"]["shape"], "cylinder")
        self.assertAlmostEqual(editor.volume_value(), box_volume * math.pi / 4.0, delta=1.0)

        editor.shape_combo.setCurrentIndex(editor.shape_combo.findData("sphere"))
        self.assertAlmostEqual(editor.volume_value(), box_volume * math.pi / 6.0, delta=1.0)

    def test_envelope_editor_populates_sections_table(self) -> None:
        from pathlib import Path

        from PySide6.QtCore import Qt

        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument

        api = StudioAPI()
        fuse = _sample_fuselage()
        sync_component_envelope(fuse)
        doc = ProjectDocument(Path("test.json"), "json", {"components": [fuse]})
        api._host.set_project(doc)

        editor = EnvelopeEditor(api, fuse)
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
        self.assertIn("0.0", table_item(editor.sections_table, 0, 0).text())
        self.assertIn("300.0", table_item(editor.sections_table, 1, 0).text())
        self.assertIn("800.0", table_item(editor.sections_table, 2, 0).text())

    def test_envelope_editor_shows_aggregate_envelope_for_assembly(self) -> None:
        from pathlib import Path

        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument

        api = StudioAPI()
        fuse = _sample_fuselage()
        sync_component_envelope(fuse)
        battery = {
            "id": "battery-1",
            "type": "org.setuav.core:battery",
            "parent": "test-fuse",
            "transform": {
                "position": {"x": 1000.0, "y": 0.0, "z": 0.0},
                "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            },
            "envelope": {
                "shape": "box",
                "size_mm": {"x": 100.0, "y": 50.0, "z": 30.0},
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
        }
        doc = ProjectDocument(Path("test.json"), "json", {"components": [fuse, battery]})
        api._host.set_project(doc)

        editor = EnvelopeEditor(api, fuse)
        self.assertIsNotNone(editor.shape_combo)
        assert editor.shape_combo is not None
        self.assertEqual(editor.shape_combo.currentData(), "box")
        self.assertTrue(editor._sections_container.isHidden())
        # Union spans the fuselage nose through the battery's aft face at x = 1050 mm
        self.assertGreater(
            editor.dimension_spins["x"].value(), fuse["envelope"]["size_mm"]["x"] + 200.0
        )

    def test_build_project_geometry_includes_envelopes(self) -> None:
        from pathlib import Path

        from plugins.geometry.engine.fuselage_geometry import build_fuselage_geometry
        from plugins.geometry.engine.lifting_surface_geometry import build_lifting_surface_geometry
        from plugins.geometry.engine.scene import build_project_geometry
        from setuav_studio.project import ProjectDocument

        fuse = _sample_fuselage()
        wing = _sample_wing()
        sync_component_envelope(fuse)
        sync_component_envelope(wing)

        doc = ProjectDocument(Path("test.json"), "json", {"components": [fuse, wing]})
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
        from plugins.geometry.engine.data import EnvelopeWireGeometry, GeometryData
        from setuav_studio.ui.viewport.mesh import (
            ENVELOPE_HIGHLIGHT,
            build_envelope_wire_vertices,
        )

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
        from pathlib import Path

        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument
        from setuav_studio.ui.viewport import StudioViewport

        api = StudioAPI()
        fuse = _sample_fuselage()
        sync_component_envelope(fuse)
        doc = ProjectDocument(Path("test.json"), "json", {"components": [fuse]})
        api._host.set_project(doc)

        viewport = StudioViewport(api=api)
        self.addCleanup(viewport.deleteLater)
        renderer = viewport.viewer
        assert renderer is not None
        from plugins.geometry.engine.fuselage_geometry import build_fuselage_geometry
        from plugins.geometry.engine.scene import build_project_geometry
        from setuav_studio.ui.viewport import LoftPrimitive, SceneObject

        geom = build_project_geometry(doc, {"org.setuav.core:fuselage": build_fuselage_geometry})
        loft = geom.lofts[0]
        env = geom.envelopes[0]
        sections_pts = tuple(tuple(pt for pt in sec.points) for sec in loft.sections)
        obj = SceneObject(
            object_id="test-fuse",
            layer="airframe",
            name="Fuselage",
            primitives=[LoftPrimitive(sections=sections_pts, color=loft.color)],
            envelope=env,
        )
        viewport.add_object(obj)

        # 0. Nothing selected -> no envelope lines drawn
        api.set_selection(None)
        renderer._upload_meshes()
        self.assertEqual(renderer._envelope_count, 0)

        # 1. Select the component and open its Envelope tab -> envelope shown
        api.set_selection(fuse)
        viewport.set_selected_envelope("test-fuse")
        self.assertEqual(renderer._selected_envelope_component_id, "test-fuse")
        self.assertEqual(renderer._selected_component_id, "test-fuse")
        renderer._upload_meshes()
        self.assertGreater(renderer._envelope_count, 0)

        # 2. Select component while envelope display is active -> envelope follows the component
        api.set_selection(fuse)
        self.assertEqual(renderer._selected_envelope_component_id, "test-fuse")
        self.assertEqual(renderer._selected_component_id, "test-fuse")
        renderer._upload_meshes()
        self.assertGreater(renderer._envelope_count, 0)

        # 3. Envelope display turned off (e.g. leaving the Envelope tab) -> component stays selected
        viewport.set_selected_envelope(None)
        self.assertIsNone(renderer._selected_envelope_component_id)
        self.assertEqual(renderer._selected_component_id, "test-fuse")
        renderer._upload_meshes()
        self.assertEqual(renderer._envelope_count, 0)

        # 4. Plain component selection does not turn envelope display on
        api.set_selection(fuse)
        self.assertIsNone(renderer._selected_envelope_component_id)
        self.assertEqual(renderer._selected_component_id, "test-fuse")
        renderer._upload_meshes()
        self.assertEqual(renderer._envelope_count, 0)

        # 5. Clear selection -> envelope and component selections are cleared
        api.set_selection(None)
        self.assertIsNone(renderer._selected_envelope_component_id)
        self.assertIsNone(renderer._selected_component_id)
        renderer._upload_meshes()
        self.assertEqual(renderer._envelope_count, 0)

    def test_lifting_surface_tip_cap_envelope_lines(self) -> None:
        from plugins.geometry.engine.scene import _append_lifting_surface_tip_envelope_lines
        from plugins.geometry.engine.transforms import identity_matrix

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
        from plugins.geometry.engine.scene import _append_lifting_surface_tip_envelope_lines
        from plugins.geometry.engine.transforms import identity_matrix

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
        from plugins.geometry.engine.scene import _rotate_control_surface_envelope

        rotated_env = _rotate_control_surface_envelope(env_0, 20.0)
        sec0_corners = env_0["sections"][0]["corners_3d"]
        rot0_corners = rotated_env["sections"][0]["corners_3d"]
        # Corner Z coordinates should shift under rotation
        self.assertNotEqual(sec0_corners[1]["z"], rot0_corners[1]["z"])

    def test_polygon_cross_section_properties(self) -> None:
        from plugins.geometry.engine.envelope import _polygon_cross_section_properties

        # Rectangle W=4 (X), H=2 (Z), centered at origin
        rect = [(-2.0, -1.0), (2.0, -1.0), (2.0, 1.0), (-2.0, 1.0)]
        area, cx, cz, izz_c, ixx_c, ixz_c = _polygon_cross_section_properties(rect)
        self.assertAlmostEqual(area, 8.0, places=5)
        self.assertAlmostEqual(cx, 0.0, places=5)
        self.assertAlmostEqual(cz, 0.0, places=5)
        # Analytical: Izz_c = W^3 * H / 12 = 4^3 * 2 / 12 = 10.66667
        self.assertAlmostEqual(izz_c, 64.0 / 6.0, places=4)
        # Analytical: Ixx_c = W * H^3 / 12 = 4 * 2^3 / 12 = 2.66667
        self.assertAlmostEqual(ixx_c, 32.0 / 12.0, places=4)
        self.assertAlmostEqual(ixz_c, 0.0, places=5)

    def test_airfoil_inertia_thickness_scaling(self) -> None:
        from plugins.geometry.engine.envelope import _compute_airfoil_properties

        # Baseline NACA 0012
        a_base, _, _, izz_base, ixx_base, _ = _compute_airfoil_properties(
            "0012", thickness_scale=1.0
        )
        # Halved thickness: thickness_scale = 0.5
        a_half, _, _, izz_half, ixx_half, _ = _compute_airfoil_properties(
            "0012", thickness_scale=0.5
        )

        # Area scales linearly with thickness scale
        self.assertAlmostEqual(a_half / a_base, 0.5, delta=0.01)
        # Chordwise moment of area izz scales with thickness scale (proportional to area)
        self.assertAlmostEqual(izz_half / izz_base, 0.5, delta=0.01)
        # Thicknesswise moment of area ixx scales with (thickness_scale)^3 = 0.125
        self.assertAlmostEqual(ixx_half / ixx_base, 0.125, delta=0.02)


if __name__ == "__main__":
    unittest.main()
