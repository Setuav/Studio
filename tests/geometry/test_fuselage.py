"""Unit and integration tests for fuselage geometry, lofts, sections, and editor."""

from __future__ import annotations

import math
import unittest
from typing import Any

from PySide6.QtWidgets import QComboBox

from plugins.geometry.engine.fuselage_geometry import (
    SECTION_SAMPLES,
    build_fuselage_geometry,
    sample_profile,
)
from setuav_studio.project import open_project
from setuav_studio.ui.widget.table import ExpressionPropertyCell
from tests._common import TEST_PROJECT_PATH, cell_widget, get_qapp, table_item


def _build_fuselage_component() -> dict[str, Any]:
    """Build a two-segment fuselage component for editor tests."""
    return {
        "id": "fuselage-1",
        "name": "Main Fuselage",
        "type": "org.setuav.core:fuselage",
        "mass": 500.0,
        "parameters": {
            "geometry": {
                "segments": [
                    {
                        "tag": "nose",
                        "loft": {"method": "smooth"},
                        "sections": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 80.0},
                            },
                            {
                                "position": {"x": 300.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 120.0},
                            },
                            {
                                "position": {"x": 700.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 60.0},
                            },
                        ],
                    },
                    {
                        "tag": "tail",
                        "loft": {"method": "ruled"},
                        "sections": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {
                                    "type": "polygon",
                                    "vertices": [
                                        {"y": -50.0, "z": -50.0, "radius": 0.0},
                                        {"y": 50.0, "z": -50.0, "radius": 0.0},
                                        {"y": 0.0, "z": 50.0, "radius": 0.0},
                                    ],
                                },
                            },
                            {
                                "position": {"x": 100.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {
                                    "type": "triangle",
                                    "base_width": 60.0,
                                    "height": 40.0,
                                    "orientation": "up",
                                    "corner_radius": 2.0,
                                },
                            },
                        ],
                    },
                ]
            },
        },
    }


class FuselageGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_all_fuselage_profiles_use_matching_samples(self) -> None:
        profiles = (
            {"type": "circle", "diameter": 100},
            {"type": "ellipse", "width": 120, "height": 80},
            {"type": "rectangle", "width": 120, "height": 80, "corner_radius": 10},
            {
                "type": "trapezoid",
                "top_width": 80,
                "bottom_width": 120,
                "height": 90,
                "corner_radius": 5,
            },
            {
                "type": "triangle",
                "base_width": 100,
                "height": 90,
                "orientation": "down",
                "corner_radius": 4,
            },
            {
                "type": "polygon",
                "vertices": [
                    {"y": 60, "z": 0, "radius": 5},
                    {"y": 0, "z": 50, "radius": 5},
                    {"y": -60, "z": 0, "radius": 5},
                    {"y": 0, "z": -50, "radius": 5},
                ],
            },
        )
        for profile in profiles:
            with self.subTest(profile=profile["type"]):
                points = sample_profile(profile)
                self.assertEqual(len(points), SECTION_SAMPLES)
                self.assertTrue(all(math.isfinite(value) for point in points for value in point))

    def test_polygon_samples_cover_the_outline_wherever_the_origin_is(self) -> None:
        from plugins.geometry.engine.fuselage_geometry import compute_section_metrics

        def polygon(points: list[tuple[float, float]]) -> dict[str, Any]:
            return {
                "type": "polygon",
                "vertices": [{"y": y, "z": z, "radius": 0.0} for y, z in points],
            }

        outlines = {
            # The section origin lies outside this square.
            "offset square": [(100.0, 50.0), (200.0, 50.0), (200.0, 150.0), (100.0, 150.0)],
            # No point sees every edge of this L shape along a straight ray.
            "concave L": [
                (0.0, 0.0),
                (100.0, 0.0),
                (100.0, 30.0),
                (30.0, 30.0),
                (30.0, 100.0),
                (0.0, 100.0),
            ],
        }
        areas = {"offset square": 100.0 * 100.0, "concave L": 100.0 * 30.0 + 30.0 * 70.0}
        for label, outline in outlines.items():
            with self.subTest(label):
                points = sample_profile(polygon(outline))
                self.assertEqual(len(points), SECTION_SAMPLES)
                ys = [y for y, _ in points]
                zs = [z for _, z in points]
                self.assertAlmostEqual(min(ys), min(y for y, _ in outline), delta=1.0)
                self.assertAlmostEqual(max(ys), max(y for y, _ in outline), delta=1.0)
                self.assertAlmostEqual(min(zs), min(z for _, z in outline), delta=1.0)
                self.assertAlmostEqual(max(zs), max(z for _, z in outline), delta=1.0)
                area = compute_section_metrics(points)["area"]
                self.assertAlmostEqual(area, areas[label], delta=0.03 * areas[label])

    def test_invalid_profiles_raise(self) -> None:
        invalid = {
            "unknown type": {"type": "hexagon", "width": 100.0},
            "two vertices": {
                "type": "polygon",
                "vertices": [
                    {"y": 0.0, "z": 0.0, "radius": 0.0},
                    {"y": 1.0, "z": 0.0, "radius": 0},
                ],
            },
            "missing dimension": {"type": "circle"},
            "non-numeric dimension": {"type": "ellipse", "width": "wide", "height": 80.0},
        }
        for label, profile in invalid.items():
            with self.subTest(label), self.assertRaises(ValueError):
                sample_profile(profile)

    def test_fuselage_component_builds_one_loft_per_segment(self) -> None:
        component = {
            "id": "body",
            "parameters": {
                "geometry": {
                    "segments": [
                        {
                            "tag": "main",
                            "loft": {"method": "smooth"},
                            "sections": [
                                {
                                    "position": {"x": 0},
                                    "profile": {"type": "circle", "diameter": 0},
                                },
                                {
                                    "position": {"x": 500},
                                    "profile": {"type": "ellipse", "width": 200, "height": 150},
                                },
                                {
                                    "position": {"x": 1000},
                                    "profile": {"type": "circle", "diameter": 0},
                                },
                            ],
                        }
                    ]
                }
            },
        }
        lofts = build_fuselage_geometry(component)
        self.assertEqual(len(lofts), 1)
        self.assertEqual(len(lofts[0].sections), 3)

    def test_fuselage_section_dialog_and_metrics(self) -> None:
        """Verify 2D fuselage section metrics calculation and dialog functionality."""
        from plugins.geometry.editors.fuselage import (
            FuselageCanvasWidget,
            FuselageSectionDialog,
        )
        from plugins.geometry.engine.fuselage_geometry import (
            compute_section_metrics,
            sample_profile,
        )
        from setuav_studio.api import StudioAPI

        # 1. Test geometric metrics calculation
        circle_pts = sample_profile({"type": "circle", "diameter": 100.0})
        m_circ = compute_section_metrics(circle_pts)
        self.assertAlmostEqual(m_circ["area"], math.pi * 50.0**2, delta=20.0)
        self.assertAlmostEqual(m_circ["perimeter"], math.pi * 100.0, delta=2.0)
        self.assertAlmostEqual(m_circ["width"], 100.0, places=1)
        self.assertAlmostEqual(m_circ["height"], 100.0, places=1)

        rect_pts = sample_profile(
            {"type": "rectangle", "width": 120.0, "height": 80.0, "corner_radius": 10.0}
        )
        m_rect = compute_section_metrics(rect_pts)
        self.assertGreater(m_rect["area"], 9000.0)
        self.assertAlmostEqual(m_rect["width"], 120.0, places=1)
        self.assertAlmostEqual(m_rect["height"], 80.0, places=1)
        self.assertAlmostEqual(m_rect["aspect_ratio"], 1.5, places=2)

        # 2. Test FuselageCanvasWidget rendering and zoom/pan
        canvas = FuselageCanvasWidget()
        canvas.resize(400, 300)
        canvas.set_section_data(
            profile={"type": "rectangle", "width": 120.0, "height": 80.0, "corner_radius": 10.0},
            prev_profile={"type": "circle", "diameter": 60.0},
            next_profile={"type": "circle", "diameter": 100.0},
            title_info="Sec 2/3",
            auto_fit=True,
        )
        self.assertGreater(len(canvas._active_points), 0)
        self.assertGreater(len(canvas._prev_points), 0)
        self.assertGreater(len(canvas._next_points), 0)
        self.assertGreater(canvas._scale, 0.0)

        # Zoom & Pan operations
        init_scale = canvas._scale
        canvas.zoom_in()
        self.assertGreater(canvas._scale, init_scale)
        canvas.zoom_out()
        canvas.fit_view()

        api = StudioAPI()
        fuse_comp = {
            "id": "fuselage-1",
            "name": "Main Fuselage",
            "type": "org.setuav.core:fuselage",
            "mass": 500.0,
            "parameters": {
                "geometry": {
                    "segments": [
                        {
                            "id": "seg_1",
                            "name": "Nose to Tail",
                            "sections": [
                                {
                                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "profile": {"type": "circle", "diameter": 80.0},
                                },
                                {
                                    "position": {"x": 300.0, "y": 0.0, "z": 0.0},
                                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "profile": {"type": "circle", "diameter": 120.0},
                                },
                                {
                                    "position": {"x": 700.0, "y": 0.0, "z": 0.0},
                                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "profile": {"type": "circle", "diameter": 60.0},
                                },
                            ],
                        }
                    ]
                },
            },
        }

        dlg = FuselageSectionDialog(api, fuse_comp)
        self.assertEqual(dlg.segment_combo.count(), 1)
        self.assertIn("Section 1 of 3", dlg.section_label.text())
        self.assertEqual(dlg.profile_type_combo.currentText(), "circle")

        dlg._on_next_section()
        self.assertEqual(dlg._section_index, 1)

        # Change profile type to ellipse and test Undo/Redo
        dlg._on_profile_type_changed("ellipse")
        sec_1 = fuse_comp["parameters"]["geometry"]["segments"][0]["sections"][1]
        self.assertEqual(sec_1["profile"]["type"], "ellipse")
        self.assertTrue(dlg.undo_stack.canUndo())

        # Edit width property with undo
        w_spin = dlg.props_table.cellWidget(0, 1)
        if isinstance(w_spin, ExpressionPropertyCell):
            w_spin.setValue(140.0)
        else:
            dlg._on_prop_spin_changed("width", 140.0)
        self.assertAlmostEqual(sec_1["profile"]["width"], 140.0)

        dlg.undo_stack.undo()
        self.assertAlmostEqual(sec_1["profile"]["width"], 120.0)
        dlg.undo_stack.redo()
        self.assertAlmostEqual(sec_1["profile"]["width"], 140.0)

        # 4. Test Interactive Polygon Editing & Undo/Redo
        dlg._on_profile_type_changed("polygon")
        self.assertEqual(sec_1["profile"]["type"], "polygon")
        num_v_initial = len(sec_1["profile"]["vertices"])
        self.assertGreaterEqual(num_v_initial, 3)

        # Hit test vertex on canvas
        v0 = sec_1["profile"]["vertices"][0]
        v0_screen = dlg.canvas.world_to_screen(v0["y"], v0["z"])
        hit_idx = dlg.canvas._hit_test_vertex(v0_screen)
        self.assertEqual(hit_idx, 0)

        # Selection synchronization: Table row click -> Canvas selection
        dlg.vertices_table.selectRow(1)
        dlg._on_vertices_row_selected(1, 0)
        self.assertEqual(dlg.canvas.selected_vertex_index, 1)

        # Selection synchronization: Canvas click -> Table selection
        dlg.canvas.vertexSelected.emit(2)
        self.assertEqual(dlg.vertices_table.currentRow(), 2)

        # Move vertex with Undo/Redo
        orig_y = float(sec_1["profile"]["vertices"][0]["y"])
        dlg._on_canvas_vertex_drag_finished(0, orig_y, 0.0, orig_y + 25.0, 10.0)
        self.assertAlmostEqual(sec_1["profile"]["vertices"][0]["y"], orig_y + 25.0)

        dlg.undo_stack.undo()
        self.assertAlmostEqual(sec_1["profile"]["vertices"][0]["y"], orig_y)
        dlg.undo_stack.redo()
        self.assertAlmostEqual(sec_1["profile"]["vertices"][0]["y"], orig_y + 25.0)

        # Insert vertex on edge with Undo/Redo
        dlg.canvas.vertexInserted.emit(1, 30.0, 40.0)
        self.assertEqual(len(sec_1["profile"]["vertices"]), num_v_initial + 1)
        self.assertAlmostEqual(sec_1["profile"]["vertices"][1]["y"], 30.0)

        dlg.undo_stack.undo()
        self.assertEqual(len(sec_1["profile"]["vertices"]), num_v_initial)
        dlg.undo_stack.redo()
        self.assertEqual(len(sec_1["profile"]["vertices"]), num_v_initial + 1)

        # Delete vertex with Undo/Redo
        dlg._delete_polygon_vertex(1)
        self.assertEqual(len(sec_1["profile"]["vertices"]), num_v_initial)
        dlg.undo_stack.undo()
        self.assertEqual(len(sec_1["profile"]["vertices"]), num_v_initial + 1)
        dlg.undo_stack.redo()
        self.assertEqual(len(sec_1["profile"]["vertices"]), num_v_initial)

        # Toggle display options
        dlg.cb_prev.setChecked(False)
        self.assertFalse(dlg.canvas.show_previous)
        dlg.cb_prev.setChecked(True)
        self.assertTrue(dlg.canvas.show_previous)

        # Apply & Close
        dlg._on_ok_clicked()

    def test_fuselage_editor_population(self) -> None:
        """Verify FuselageEditor loads general info, segments, sections, and transforms."""
        from plugins.geometry.editors.fuselage import FuselageEditor
        from setuav_studio.api import StudioAPI

        api = StudioAPI()
        comp = _build_fuselage_component()
        editor = FuselageEditor(api, comp)

        # General section
        self.assertEqual(table_item(editor.general_table, 0, 1).text(), "Main Fuselage")
        self.assertEqual(table_item(editor.general_table, 1, 1).text(), "org.setuav.core:fuselage")

        # Segments table: tags, method combos
        self.assertEqual(editor.segments_table.rowCount(), 2)
        self.assertEqual(table_item(editor.segments_table, 0, 0).text(), "nose")
        self.assertEqual(table_item(editor.segments_table, 0, 1).text(), "3")
        self.assertEqual(
            cell_widget(editor.segments_table, 0, 2, QComboBox).currentData(), "smooth"
        )
        self.assertEqual(cell_widget(editor.segments_table, 1, 2, QComboBox).currentData(), "ruled")

        # First segment auto-loaded -> sections populated
        self.assertEqual(editor._segment_index, 0)
        self.assertEqual(editor.sections_table.rowCount(), 3)
        self.assertEqual(table_item(editor.sections_table, 0, 1).text(), "circle")
        self.assertIn("0", table_item(editor.sections_table, 0, 2).text())

        # Section properties for circle: type + diameter
        self.assertEqual(editor.section_properties_table.rowCount(), 2)
        self.assertAlmostEqual(
            cell_widget(editor.section_properties_table, 1, 1, ExpressionPropertyCell).value(),
            80.0,
        )

        # Transform spinboxes
        self.assertAlmostEqual(
            cell_widget(editor.transform_table, 0, 0, ExpressionPropertyCell).value(), 0.0
        )
        self.assertAlmostEqual(
            cell_widget(editor.transform_table, 1, 0, ExpressionPropertyCell).value(), 0.0
        )

        # Action states
        self.assertTrue(editor.add_segment_button.isEnabled())
        self.assertTrue(editor.delete_segment_button.isEnabled())  # 2 segments
        self.assertTrue(editor.add_section_button.isEnabled())
        self.assertTrue(editor.delete_section_button.isEnabled())  # 3 sections

    def test_fuselage_editor_segment_actions(self) -> None:
        """Verify add/duplicate/move/delete segment mutations."""
        from plugins.geometry.editors.fuselage import FuselageEditor
        from setuav_studio.api import StudioAPI

        api = StudioAPI()
        comp = _build_fuselage_component()
        editor = FuselageEditor(api, comp)

        # Add inserts after the selected segment (index 0 -> 1)
        editor._add_segment()
        segments = comp["parameters"]["geometry"]["segments"]
        self.assertEqual([s["tag"] for s in segments], ["nose", "segment", "tail"])
        self.assertEqual(len(segments[1]["sections"]), 2)
        self.assertEqual(segments[1]["loft"]["method"], "smooth")
        self.assertEqual(editor.segments_table.currentRow(), 1)

        editor._duplicate_segment()
        segments = comp["parameters"]["geometry"]["segments"]
        self.assertEqual([s["tag"] for s in segments], ["nose", "segment", "segment-copy", "tail"])
        self.assertEqual(editor.segments_table.currentRow(), 2)

        editor._move_segment_up()
        segments = comp["parameters"]["geometry"]["segments"]
        self.assertEqual([s["tag"] for s in segments], ["nose", "segment-copy", "segment", "tail"])
        self.assertEqual(editor.segments_table.currentRow(), 1)

        editor._move_segment_down()
        segments = comp["parameters"]["geometry"]["segments"]
        self.assertEqual([s["tag"] for s in segments], ["nose", "segment", "segment-copy", "tail"])
        self.assertEqual(editor.segments_table.currentRow(), 2)

        editor._delete_segment()
        segments = comp["parameters"]["geometry"]["segments"]
        self.assertEqual([s["tag"] for s in segments], ["nose", "segment", "tail"])

    def test_fuselage_editor_section_actions(self) -> None:
        """Verify add/duplicate/move/delete section mutations and x interpolation."""
        from plugins.geometry.editors.fuselage import FuselageEditor
        from setuav_studio.api import StudioAPI

        api = StudioAPI()
        comp = _build_fuselage_component()
        editor = FuselageEditor(api, comp)
        self.assertEqual(editor._section_index, 0)

        # Add: inserted after selection at midpoint of neighbours (0, 300) -> 150
        editor._add_section()
        sections = comp["parameters"]["geometry"]["segments"][0]["sections"]
        self.assertEqual(len(sections), 4)
        self.assertAlmostEqual(sections[1]["position"]["x"], 150.0)
        self.assertEqual(sections[1]["profile"]["type"], "circle")
        self.assertEqual(editor.sections_table.currentRow(), 1)

        # Duplicate
        editor._duplicate_section()
        sections = comp["parameters"]["geometry"]["segments"][0]["sections"]
        self.assertEqual(len(sections), 5)
        self.assertEqual(editor.sections_table.currentRow(), 2)
        self.assertAlmostEqual(sections[2]["position"]["x"], 150.0)

        # Move up / down
        editor._move_section_up()
        sections = comp["parameters"]["geometry"]["segments"][0]["sections"]
        self.assertEqual(editor.sections_table.currentRow(), 1)
        self.assertAlmostEqual(sections[1]["position"]["x"], 150.0)
        editor._move_section_down()
        sections = comp["parameters"]["geometry"]["segments"][0]["sections"]
        self.assertEqual(editor.sections_table.currentRow(), 2)
        self.assertAlmostEqual(sections[2]["position"]["x"], 150.0)

        # Delete (needs > 2 sections)
        editor._delete_section()
        sections = comp["parameters"]["geometry"]["segments"][0]["sections"]
        self.assertEqual(len(sections), 4)
        self.assertEqual(editor.sections_table.currentRow(), 2)

    def test_fuselage_editor_profile_transform_and_vertices(self) -> None:
        """Verify profile type change, numeric property, transform, and polygon vertex edits."""
        from plugins.geometry.editors.fuselage import FuselageEditor
        from setuav_studio.api import StudioAPI

        api = StudioAPI()
        comp = _build_fuselage_component()
        editor = FuselageEditor(api, comp)

        # Profile type change circle -> ellipse
        editor._change_profile_type("ellipse")
        profile = comp["parameters"]["geometry"]["segments"][0]["sections"][0]["profile"]
        self.assertEqual(profile["type"], "ellipse")
        self.assertEqual(editor.section_properties_table.rowCount(), 3)  # type, width, height
        cell_widget(editor.section_properties_table, 1, 1, ExpressionPropertyCell).setValue(140.0)
        profile = comp["parameters"]["geometry"]["segments"][0]["sections"][0]["profile"]
        self.assertAlmostEqual(profile["width"], 140.0)
        self.assertIn("140", table_item(editor.sections_table, 0, 3).text())
        self.assertIn("100", table_item(editor.sections_table, 0, 3).text())

        # Transform edit through the spinbox -> position committed
        cell_widget(editor.transform_table, 0, 0, ExpressionPropertyCell).setValue(25.0)
        self.assertAlmostEqual(
            comp["parameters"]["geometry"]["segments"][0]["sections"][0]["position"]["x"],
            25.0,
        )

        # Triangle orientation via segment 1
        editor.segments_table.selectRow(1)
        self.assertEqual(editor._segment_index, 1)
        editor.sections_table.selectRow(1)  # triangle section
        self.assertEqual(
            editor.section_properties_table.rowCount(), 5
        )  # type, base_width, height, orientation, corner_radius
        editor._update_section_choice("orientation", "down")
        tri_profile = comp["parameters"]["geometry"]["segments"][1]["sections"][1]["profile"]
        self.assertEqual(tri_profile["orientation"], "down")

        # Polygon vertices
        editor.sections_table.selectRow(0)
        self.assertEqual(editor.vertices_table.rowCount(), 3)
        self.assertAlmostEqual(
            cell_widget(editor.vertices_table, 0, 0, ExpressionPropertyCell).value(), -50.0
        )
        editor._on_vertex_spin_changed(0, 0, 60.0)
        self.assertAlmostEqual(
            comp["parameters"]["geometry"]["segments"][1]["sections"][0]["profile"]["vertices"][0][
                "y"
            ],
            60.0,
        )

    def test_fuselage_editor_general_and_segment_edits(self) -> None:
        """Verify general name/mass edits and segment tag/loft choice edits."""
        from plugins.geometry.editors.fuselage import FuselageEditor
        from setuav_studio.api import StudioAPI

        api = StudioAPI()
        comp = _build_fuselage_component()
        editor = FuselageEditor(api, comp)

        # Name edit
        table_item(editor.general_table, 0, 1).setText("Renamed Body")
        editor._update_general(0, 1)
        self.assertEqual(comp["name"], "Renamed Body")

        # Segment tag inline edit
        table_item(editor.segments_table, 0, 0).setText("nose-renamed")
        editor._update_segment_cell(0, 0)
        self.assertEqual(comp["parameters"]["geometry"]["segments"][0]["tag"], "nose-renamed")

        # Segment loft choice edits
        editor._update_segment_choice(0, "method", "ruled")
        self.assertEqual(comp["parameters"]["geometry"]["segments"][0]["loft"]["method"], "ruled")

    def test_fuselage_editor_property_expression_changes(self) -> None:
        """Verify editing section properties via expressions or numbers applies correctly."""
        from plugins.geometry.editors.fuselage import FuselageEditor
        from setuav_studio.api import StudioAPI

        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)

        comp = _build_fuselage_component()
        doc.data["components"].append(comp)
        editor = FuselageEditor(api, comp)

        def current_profile() -> dict[str, Any]:
            return comp["parameters"]["geometry"]["segments"][0]["sections"][0]["profile"]

        # Section 0 is a circle (diameter = 80.0)
        self.assertAlmostEqual(current_profile()["diameter"], 80.0)

        # Change diameter via numeric input
        editor._on_property_expression_changed("diameter", "110.0")
        self.assertAlmostEqual(current_profile()["diameter"], 110.0)
        self.assertNotIn("_expressions", current_profile())
        self.assertIn("110", table_item(editor.sections_table, 0, 3).text())

        # Change diameter via expression
        editor._on_property_expression_changed("diameter", "=50 + 75")
        self.assertAlmostEqual(current_profile()["diameter"], 125.0)
        self.assertEqual(current_profile().get("_expressions", {}).get("diameter"), "=50 + 75")
        self.assertIn("125", table_item(editor.sections_table, 0, 3).text())

        # Verify undo works
        api.undo()
        self.assertAlmostEqual(current_profile()["diameter"], 110.0)
        self.assertNotIn("_expressions", current_profile())

    def test_fuselage_engine_helpers_and_metrics(self) -> None:
        """Verify fuselage engine calculation and data template helpers."""
        from plugins.geometry.engine.fuselage_geometry import (
            compute_section_metrics,
            create_default_section,
            create_default_segment,
            format_profile_size,
            get_default_profile,
        )

        # 1. Section metrics computation (unit square: -50..50)
        square_points = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
        metrics = compute_section_metrics(square_points)
        self.assertAlmostEqual(metrics["area"], 10000.0, places=1)
        self.assertAlmostEqual(metrics["perimeter"], 400.0, places=1)
        self.assertAlmostEqual(metrics["width"], 100.0, places=1)
        self.assertAlmostEqual(metrics["height"], 100.0, places=1)
        self.assertAlmostEqual(metrics["aspect_ratio"], 1.0, places=2)

        # 2. Template creators
        profile = get_default_profile("rectangle")
        self.assertEqual(profile["type"], "rectangle")
        self.assertEqual(profile["width"], 100.0)

        section = create_default_section(150.0, "ellipse")
        self.assertEqual(section["position"]["x"], 150.0)
        self.assertEqual(section["profile"]["type"], "ellipse")

        segment = create_default_segment("mid", 0.0, 300.0)
        self.assertEqual(segment["tag"], "mid")
        self.assertEqual(len(segment["sections"]), 2)
        self.assertEqual(segment["sections"][1]["position"]["x"], 300.0)

        # 3. Formatter
        self.assertEqual(format_profile_size({"type": "circle", "diameter": 80.0}), "D 80.0")
        self.assertEqual(
            format_profile_size({"type": "ellipse", "width": 120.0, "height": 60.0}), "120.0 × 60.0"
        )


if __name__ == "__main__":
    unittest.main()
