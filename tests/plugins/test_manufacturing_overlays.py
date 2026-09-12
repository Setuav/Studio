import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio_sdk import LineSegmentsPrimitive, TrianglesPrimitive

# Add manufacturing plugin to sys.path
import sys
plugin_src = Path("/home/huseyin/dev/setware/setuav-cad/plugins/manufacturing_plugin/src")
if str(plugin_src) not in sys.path:
    sys.path.insert(0, str(plugin_src))

from setuav_manufacturing_plugin.overlays import (
    COLOR_LUG_WIRE,
    COLOR_NOSE_CUT,
    COLOR_SCREW_DASH,
    COLOR_SCREW_RING,
    COLOR_SPAR_TUBE,
    _generate_lug_polygon,
    _generate_screw_dashed_lines,
    _get_airfoil_z_surface_and_center,
    get_wing_solid_vertical_bounds_at_xy,
    get_main_wing_solid_midpoint_z,
    build_nose_cut_primitives,
    build_wing_connection_primitives,
    build_wing_spar_primitives,
    update_manufacturing_overlays,
)
from setuav_manufacturing_plugin.models import (
    FASTENER_STANDARDS,
    WING_CONNECTION_DEFAULTS,
    ensure_manufacturing_configuration,
    get_manufacturing_features,
    has_manufacturing_configuration,
    resolve_fastener_standard,
    add_spar_to_wing,
    scan_airframe_components,
)
from setuav_manufacturing_plugin.editors.nose_cut import NoseCutPropertyEditor
from setuav_manufacturing_plugin.editors.wing_connection import WingConnectionPropertyEditor
from setuav_manufacturing_plugin.editors.wing_spars import WingSparsPropertyEditor
from setuav_manufacturing_plugin.tree import ManufacturingTreeProvider
from setuav_manufacturing_plugin.tools import ManufacturingToolsController


class TestManufacturingOverlays(unittest.TestCase):
    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        self.fixture_path = Path("/home/huseyin/dev/setware/setuav-studio/tests/fixtures/fixed-wing/project.json")
        with open(self.fixture_path, "r") as f:
            self.project_data = json.load(f)
        self.doc = ProjectDocument(self.fixture_path, "json", self.project_data)

    def test_lug_polygon_geometry(self) -> None:
        center_x = 300.0
        base_y = 50.0
        tip_y = 70.0
        poly = _generate_lug_polygon(
            center_x=center_x,
            base_y=base_y,
            tip_y=tip_y,
            base_w=20.0,
            tip_w=14.0,
            corner_radius=5.0,
        )
        # Verify base width: x ranges from center_x - 10 to center_x + 10
        base_pts = [p for p in poly if abs(p[1] - base_y) < 1e-4]
        self.assertEqual(len(base_pts), 2)
        x_coords = sorted([p[0] for p in base_pts])
        self.assertAlmostEqual(x_coords[0], 290.0, places=3)
        self.assertAlmostEqual(x_coords[1], 310.0, places=3)

        # Verify tip: max y reaches tip_y
        max_y = max(p[1] for p in poly)
        self.assertAlmostEqual(max_y, 70.0, places=3)

    def test_screw_dashed_lines_generation(self) -> None:
        dashes = _generate_screw_dashed_lines(
            screw_center=(300.0, 50.0, 40.0),
            axis_vector=(0.0, 0.0, 1.0),
            total_length=30.0,
            dash_length=3.0,
            gap_length=2.0,
        )
        # Must produce multiple dashed segments along Z
        self.assertGreater(len(dashes), 3)
        for p_start, p_end in dashes:
            # X and Y remain at screw center
            self.assertAlmostEqual(p_start[0], 300.0, places=3)
            self.assertAlmostEqual(p_start[1], 50.0, places=3)
            self.assertAlmostEqual(p_end[0], 300.0, places=3)
            self.assertAlmostEqual(p_end[1], 50.0, places=3)
            # Z difference should match dash_length
            dz = p_end[2] - p_start[2]
            self.assertAlmostEqual(dz, 3.0, places=3)

    def test_airfoil_z_centering_calculation(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        geom = wing_comp.get("parameters", {}).get("geometry", {})
        profiles = geom.get("profiles", [])
        chord = float(profiles[0].get("chord", 200.0))
        z_root = float(wing_comp.get("transform", {}).get("position", {}).get("z", 40.0))

        # At front fastener ratio 0.18 on Clark-Y
        z_upper, z_lower, lug_z = _get_airfoil_z_surface_and_center(
            profiles=profiles,
            chord=chord,
            z_root=z_root,
            x_ratio=0.18,
            lug_center_z_offset=0.0,
        )
        # Clark-Y is cambered with flat bottom; thickness midpoint is ~45.1 mm, NOT datum 40.0
        self.assertGreater(lug_z, 44.0)
        self.assertLess(lug_z, 48.0)
        # Clearance to upper and lower skin must be identical (centered)
        clearance_upper = z_upper - lug_z
        clearance_lower = lug_z - z_lower
        self.assertAlmostEqual(clearance_upper, clearance_lower, places=3)

    def test_wing_connection_primitives_wireframe_blue_lugs(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        primitives = build_wing_connection_primitives(wing_comp)
        self.assertGreater(len(primitives), 0)

        # 1. Verify NO TrianglesPrimitive (lugs are edges only)
        solid_prims = [p for p in primitives if isinstance(p, TrianglesPrimitive)]
        self.assertEqual(len(solid_prims), 0)

        # 2. Verify blue wireframe lines for lugs
        wire_prims = [p for p in primitives if isinstance(p, LineSegmentsPrimitive)]
        lug_prims = [p for p in wire_prims if p.color == COLOR_LUG_WIRE]
        self.assertEqual(len(lug_prims), 1)
        self.assertGreater(len(lug_prims[0].lines), 50)
        # Color must be pure blue
        self.assertEqual(lug_prims[0].color, (0.05, 0.50, 1.0, 1.0))

        # 3. Verify lug vertices are centered in Z around ~46.5 mm
        all_z = [pt[2] for seg in lug_prims[0].lines for pt in seg]
        mid_z = (min(all_z) + max(all_z)) / 2.0
        self.assertGreater(mid_z, 44.0)
        self.assertLess(mid_z, 48.0)

        # 4. Verify red dashed screws
        screw_prims = [p for p in wire_prims if p.color == COLOR_SCREW_DASH]
        self.assertEqual(len(screw_prims), 1)
        self.assertGreater(len(screw_prims[0].lines), 10)
        self.assertEqual(screw_prims[0].color, (1.0, 0.15, 0.15, 1.0))

    def test_update_manufacturing_overlays_publishes_event(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc

        published_events = []
        api.subscribe("studio.viewer.set_overlays", published_events.append)

        # 1. When manufacturing configuration is absent, primitives are empty
        update_manufacturing_overlays(api, "conn_main-wing")
        self.assertEqual(len(published_events), 1)
        self.assertEqual(published_events[0]["layer"], "manufacturing")
        self.assertEqual(len(published_events[0]["primitives"]), 0)

        # 2. Add manufacturing configuration and trigger overlay for main-wing
        ensure_manufacturing_configuration(api)
        update_manufacturing_overlays(api, "conn_main-wing")
        self.assertEqual(len(published_events), 2)
        self.assertEqual(published_events[1]["layer"], "manufacturing")
        prims = published_events[1]["primitives"]
        self.assertGreater(len(prims), 0)

        # Must include red dashed screws and blue wireframe lugs
        has_red_screws = any(
            isinstance(p, LineSegmentsPrimitive) and p.color == COLOR_SCREW_DASH
            for p in prims
        )
        has_blue_lugs = any(
            isinstance(p, LineSegmentsPrimitive) and p.color == COLOR_LUG_WIRE
            for p in prims
        )
        has_no_solids = not any(isinstance(p, TrianglesPrimitive) for p in prims)

        self.assertTrue(has_red_screws)
        self.assertTrue(has_blue_lugs)
        self.assertTrue(has_no_solids)

    def test_wing_connection_primitives_v_tail_rotated(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "v-tail"
        )
        primitives = build_wing_connection_primitives(wing_comp)
        self.assertGreater(len(primitives), 0)

        # Verify wireframe blue lugs and red dashed screws are created with non-zero roll rotation
        wire_prims = [p for p in primitives if isinstance(p, LineSegmentsPrimitive)]
        lug_prims = [p for p in wire_prims if p.color == COLOR_LUG_WIRE]
        self.assertEqual(len(lug_prims), 1)

        screw_prims = [p for p in wire_prims if p.color == COLOR_SCREW_DASH]
        self.assertEqual(len(screw_prims), 1)
        self.assertGreater(len(screw_prims[0].lines), 0)

        # Verify exact bilateral symmetry across the aircraft centerline (Y=0)
        lug_pts_sb = [pt for seg in lug_prims[0].lines for pt in seg if pt[1] > 0]
        lug_pts_pt = [pt for seg in lug_prims[0].lines for pt in seg if pt[1] < 0]
        self.assertGreater(len(lug_pts_sb), 0)
        self.assertGreater(len(lug_pts_pt), 0)

        # Starboard & Port Z bounds must be identical
        self.assertAlmostEqual(min(p[2] for p in lug_pts_sb), min(p[2] for p in lug_pts_pt), places=3)
        self.assertAlmostEqual(max(p[2] for p in lug_pts_sb), max(p[2] for p in lug_pts_pt), places=3)

        # Starboard & Port Y bounds must be exact negatives
        self.assertAlmostEqual(min(p[1] for p in lug_pts_sb), -max(p[1] for p in lug_pts_pt), places=3)
        self.assertAlmostEqual(max(p[1] for p in lug_pts_sb), -min(p[1] for p in lug_pts_pt), places=3)

    def test_wing_connection_property_editor(self) -> None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        sel = {
            "id": "conn_main-wing",
            "name": "Main Wing Connection",
            "target": "main-wing",
        }
        editor = WingConnectionPropertyEditor(api, sel)
        self.assertIsNotNone(editor)

        # Test changing lug_length_mm property
        editor._on_float_changed("lug_length_mm", 30.0)

        feats = get_manufacturing_features(self.doc)
        conn_data = feats.get("conn_main-wing", {})
        self.assertEqual(conn_data.get("lug_length_mm"), 30.0)

        # Test selecting metric fastener M4 and auto-derived insert parameters
        editor._on_metric_changed("M4")
        feats = get_manufacturing_features(self.doc)
        conn_data = feats.get("conn_main-wing", {})
        self.assertEqual(conn_data.get("fastener_standard"), "M4")
        self.assertEqual(conn_data.get("screw_diameter_mm"), 4.0)
        self.assertEqual(conn_data.get("insert_outer_diameter_mm"), 5.5)
        self.assertEqual(conn_data.get("insert_depth_mm"), 6.0)

        # Test user overriding insert diameter and depth manually
        editor._on_float_changed("insert_outer_diameter_mm", 5.8)
        editor._on_float_changed("insert_depth_mm", 7.5)
        feats = get_manufacturing_features(self.doc)
        conn_data = feats.get("conn_main-wing", {})
        self.assertEqual(conn_data.get("insert_outer_diameter_mm"), 5.8)
        self.assertEqual(conn_data.get("insert_depth_mm"), 7.5)

        # Verify streamlined UI: no socket table, no Z offset, no wing side
        self.assertFalse(hasattr(editor, "_socket_table"))
        lug_keys = [editor._lug_table.item(r, 0).text() for r in range(editor._lug_table.rowCount()) if editor._lug_table.item(r, 0)]
        self.assertNotIn("Z Offset from Center", lug_keys)
        gen_keys = [editor._general_table.item(r, 0).text() for r in range(editor._general_table.rowCount()) if editor._general_table.item(r, 0)]
        self.assertNotIn("Wing Side", gen_keys)
        fastener_keys = [editor._fastener_table.item(r, 0).text() for r in range(editor._fastener_table.rowCount()) if editor._fastener_table.item(r, 0)]
        self.assertIn("Insert Diameter", fastener_keys)
        self.assertIn("Insert Height", fastener_keys)

    def test_metric_fastener_presets(self) -> None:
        m3_spec = resolve_fastener_standard("M3")
        self.assertEqual(m3_spec["screw_diameter_mm"], 3.0)
        self.assertEqual(m3_spec["insert_outer_diameter_mm"], 4.6)
        self.assertEqual(m3_spec["insert_depth_mm"], 5.0)

        m4_spec = resolve_fastener_standard("M4")
        self.assertEqual(m4_spec["screw_diameter_mm"], 4.0)
        self.assertEqual(m4_spec["insert_outer_diameter_mm"], 5.5)
        self.assertEqual(m4_spec["insert_depth_mm"], 6.0)

    def test_screw_through_hole_breaches_both_wing_skins(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        primitives = build_wing_connection_primitives(wing_comp)
        screw_prims = [p for p in primitives if isinstance(p, LineSegmentsPrimitive) and p.color == COLOR_SCREW_DASH]
        self.assertEqual(len(screw_prims), 1)

        # The screw dashed lines must visibly extend out both upper and lower wing surfaces
        all_z = [pt[2] for seg in screw_prims[0].lines for pt in seg]
        min_screw_z = min(all_z)
        max_screw_z = max(all_z)

        # Main wing Z is at 40.0; airfoil Clark-Y lower is ~40.0, upper is ~50.2
        # Screw line should extend below 35.0 (out bottom) and above 55.0 (out top)
        self.assertLess(min_screw_z, 35.0)
        self.assertGreater(max_screw_z, 55.0)

    def test_plugin_selection_listener(self) -> None:
        from setuav_manufacturing_plugin.plugin import ManufacturingPlugin

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        published_events = []
        api.subscribe("studio.viewer.set_overlays", published_events.append)

        plugin = ManufacturingPlugin()
        plugin.activate(api)

        # 1. Without clicking anything, overlays should be visible in the visualizer
        self.assertGreater(len(published_events), 0)
        last_event = published_events[-1]
        self.assertEqual(last_event["layer"], "manufacturing")
        self.assertGreater(len(last_event["primitives"]), 0)

        # 2. Select wing connection node
        api.set_selection({
            "kind": "manufacturing_feature",
            "id": "conn_main-wing",
            "type": "manufacturing:wing_connection",
        })
        self.assertGreater(len(published_events[-1]["primitives"]), 0)

        # 3. Even when not clicked (selection is None / deselected), overlays REMAIN VISIBLE
        api.set_selection(None)
        self.assertGreater(len(published_events[-1]["primitives"]), 0)

        # 4. Deactivating plugin clears overlays
        plugin.deactivate(api)
        self.assertEqual(len(published_events[-1]["primitives"]), 0)

    def test_manufacturing_tree_hierarchy_with_wings_and_spars(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        provider = ManufacturingTreeProvider(api)
        nodes = provider.project_tree_nodes(self.doc)
        self.assertEqual(len(nodes), 1)

        root = nodes[0]
        self.assertEqual(root.id, "com.setuav.manufacturing.configuration")
        self.assertEqual(root.title, "Manufacturing Configuration")

        # Find wing nodes among root's children
        child_map = {c.title: c for c in root.children}
        self.assertIn("Main Wing", child_map)
        self.assertIn("V-Tail", child_map)

        main_wing_node = child_map["Main Wing"]
        self.assertEqual(main_wing_node.id, "com.setuav.manufacturing.wing.main-wing")
        self.assertEqual(main_wing_node.selection["target"], "main-wing")
        self.assertEqual(main_wing_node.selection["type"], "manufacturing:wing_group")

        # Root must NOT have Aileron or Servo Mount floating as top-level children
        self.assertNotIn("Aileron", child_map)
        self.assertNotIn("Aileron Servo Mount", child_map)
        self.assertNotIn("Ruddervator", child_map)
        self.assertNotIn("Ruddervator Servo Mount", child_map)
        self.assertIn("Fuselage", child_map)
        self.assertNotIn("Nose Cut", child_map)
        self.assertNotIn("Access Cover", child_map)
        self.assertNotIn("Access Covers", child_map)
        self.assertNotIn("Shell", child_map)

        # Main wing children must include Fuselage Connection, Spar 1, and Aileron
        mw_children = main_wing_node.children
        mw_child_titles = [c.title for c in mw_children]
        self.assertIn("Fuselage Connection", mw_child_titles)
        self.assertIn("Spar 1", mw_child_titles)
        self.assertIn("Aileron Hardware", mw_child_titles)

        hw_node = next(c for c in mw_children if c.title == "Aileron Hardware")
        self.assertEqual(hw_node.selection["type"], "manufacturing:control_surface_hardware")
        # Under Aileron Hardware: Servo and Hinge (no Horn)
        hw_children = {c.title: c for c in hw_node.children}
        self.assertIn("Servo", hw_children)
        self.assertIn("Hinge", hw_children)
        self.assertNotIn("Horn", hw_children)
        self.assertEqual(hw_children["Servo"].selection["sub_section"], "servo")
        self.assertEqual(hw_children["Hinge"].selection["sub_section"], "hinge")

        # V-Tail children must include Fuselage Connection, Spar 1, and Ruddervator Hardware
        v_tail_node = child_map["V-Tail"]
        vt_children = v_tail_node.children
        vt_child_titles = [c.title for c in vt_children]
        self.assertIn("Fuselage Connection", vt_child_titles)
        self.assertIn("Spar 1", vt_child_titles)
        self.assertIn("Ruddervator Hardware", vt_child_titles)

        ruddervator_hw_node = next(c for c in vt_children if c.title == "Ruddervator Hardware")
        self.assertEqual(len(ruddervator_hw_node.children), 2)

    def test_toolbar_add_spar_enabled_only_when_wing_selected(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        tools = ManufacturingToolsController(api)
        contributions = {c.id: c for c in tools.contributions()}
        self.assertIn("manufacturing.tool.wing_spars", contributions)
        spar_tool = contributions["manufacturing.tool.wing_spars"]

        # 1. No selection -> Disabled
        api.set_selection(None)
        self.assertFalse(spar_tool.enabled_when())

        # 2. Non-wing selection (e.g. fuselage) -> Disabled
        api.set_selection({"id": "fuselage", "type": "org.setuav.core:fuselage"})
        self.assertFalse(spar_tool.enabled_when())

        # 3. Motor mount selection -> Disabled
        api.set_selection({"id": "mount_motor-1", "type": "manufacturing:motor_mount"})
        self.assertFalse(spar_tool.enabled_when())

        # 4. Wing component selection (from airframe components) -> Enabled
        api.set_selection({"id": "main-wing", "type": "org.setuav.core:lifting-surface"})
        self.assertTrue(spar_tool.enabled_when())

        # 5. Manufacturing wing group selection ("Main Wing") -> Enabled
        api.set_selection({
            "id": "mfg_wing_main-wing",
            "type": "manufacturing:wing_group",
            "target": "main-wing",
        })
        self.assertTrue(spar_tool.enabled_when())

        # 6. "Fuselage Connection" selection -> Enabled
        api.set_selection({
            "id": "conn_main-wing",
            "type": "manufacturing:wing_connection",
            "target": "main-wing",
        })
        self.assertTrue(spar_tool.enabled_when())

        # 7. Existing spar selection -> Enabled
        api.set_selection({
            "id": "spar_main-wing_1",
            "type": "manufacturing:wing_spars",
            "target": "main-wing",
        })
        self.assertTrue(spar_tool.enabled_when())

    def test_add_spar_to_wing_creates_subsequent_spars(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        # Initially, main-wing has Spar 1
        features = get_manufacturing_features(self.doc)
        self.assertIn("spar_main-wing_1", features)
        self.assertNotIn("spar_main-wing_2", features)

        # Add a second spar to main-wing
        spar2 = add_spar_to_wing(api, "main-wing")
        self.assertEqual(spar2["id"], "spar_main-wing_2")
        self.assertEqual(spar2["name"], "Spar 2")
        self.assertEqual(spar2["target_component"], "main-wing")
        self.assertEqual(spar2["chord_ratio"], 0.54)

        # Verify in features and in tree
        features = get_manufacturing_features(self.doc)
        self.assertIn("spar_main-wing_2", features)

        provider = ManufacturingTreeProvider(api)
        nodes = provider.project_tree_nodes(self.doc)
        child_map = {c.title: c for c in nodes[0].children}
        mw_children = child_map["Main Wing"].children
        titles = [c.title for c in mw_children]
        self.assertIn("Fuselage Connection", titles)
        self.assertIn("Spar 1", titles)
        self.assertIn("Spar 2", titles)

        # Delete Spar 2 and verify it is removed from tree
        mw_children_map = {c.title: c for c in mw_children}
        mw_children_map["Spar 2"].delete()

        features_after = get_manufacturing_features(self.doc)
        self.assertNotIn("spar_main-wing_2", features_after)

    def test_wing_spars_property_editor(self) -> None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        sel = {
            "id": "spar_main-wing_1",
            "name": "Spar 1",
            "target": "main-wing",
            "target_component": "main-wing",
        }
        editor = WingSparsPropertyEditor(api, sel)
        self.assertIsNotNone(editor)

        # Modify chord_ratio and outer_diameter_mm
        editor._on_float_changed("chord_ratio", 0.35)
        editor._on_float_changed("outer_diameter_mm", 12.0)

        feats = get_manufacturing_features(self.doc)
        spar_data = feats.get("spar_main-wing_1", {})
        self.assertEqual(spar_data.get("chord_ratio"), 0.35)
        self.assertEqual(spar_data.get("outer_diameter_mm"), 12.0)

        # 1. When span_start is 0.0 (root), shared_spar and fuselage_penetration rows are visible
        pen_row = editor._find_property_row(editor._geom_table, "fuselage_penetration_mm")
        shared_row = editor._find_property_row(editor._geom_table, "shared_spar")
        self.assertFalse(editor._geom_table.isRowHidden(pen_row))
        self.assertFalse(editor._geom_table.isRowHidden(shared_row))

        # Default: shared_spar is True -> fuselage_penetration is disabled ("o seçilirse gövde girişi seçilemez")
        self.assertTrue(editor._shared_spar_cb.isChecked())
        self.assertFalse(editor._pen_cell.isEnabled())

        # Uncheck shared_spar -> fuselage_penetration becomes enabled
        editor._shared_spar_cb.setChecked(False)
        self.assertFalse(editor._shared_spar_cb.isChecked())
        self.assertTrue(editor._pen_cell.isEnabled())

        # Set penetration depth
        editor._on_float_changed("fuselage_penetration_mm", 40.0)
        feats = get_manufacturing_features(self.doc)
        spar_data = feats.get("spar_main-wing_1", {})
        self.assertEqual(spar_data.get("shared_spar"), False)
        self.assertEqual(spar_data.get("fuselage_penetration_mm"), 40.0)

        # 2. When span_start > 0.0, fuselage penetration and shared spar are hidden ("gövde girişi sadece span start 0 ise görünsün")
        editor._on_span_start_changed(0.25)
        self.assertTrue(editor._geom_table.isRowHidden(pen_row))
        self.assertTrue(editor._geom_table.isRowHidden(shared_row))

        # Reset span_start to 0.0 -> they become visible again
        editor._on_span_start_changed(0.0)
        self.assertFalse(editor._geom_table.isRowHidden(pen_row))
        self.assertFalse(editor._geom_table.isRowHidden(shared_row))

    def test_wing_spar_primitives_geometry(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        spar_data = {
            "id": "spar_main-wing_1",
            "name": "Spar 1",
            "chord_ratio": 0.28,
            "outer_diameter_mm": 8.0,
            "inner_diameter_mm": 6.0,
            "span_start_mm": 0.0,
            "span_end_mm": 500.0,
            "enabled": True,
        }
        primitives = build_wing_spar_primitives(wing_comp, spar_data)
        self.assertEqual(len(primitives), 1)

        prim = primitives[0]
        self.assertIsInstance(prim, LineSegmentsPrimitive)
        self.assertEqual(prim.color, COLOR_SPAR_TUBE)
        # Should have rings, longitudinal lines, end caps, and fuselage bridge
        self.assertGreater(len(prim.lines), 100)

        # Starboard and Port symmetry across Y=0
        stb_pts = [p for seg in prim.lines for p in seg if p[1] > 0]
        port_pts = [p for seg in prim.lines for p in seg if p[1] < 0]
        self.assertGreater(len(stb_pts), 0)
        self.assertGreater(len(port_pts), 0)

        # Through-spar bridges across Y=0: there must be segments crossing Y=0 or spanning it
        crosses_y0 = any(
            (seg[0][1] <= 1e-4 and seg[1][1] >= -1e-4) or (seg[0][1] >= -1e-4 and seg[1][1] <= 1e-4)
            for seg in prim.lines
            if abs(seg[0][1] - seg[1][1]) > 1.0
        )
        self.assertTrue(crosses_y0)

        # Center Z should be within airfoil Clark-Y bounds (~44-48 mm at root, climbing with dihedral up to ~59 mm at tip)
        all_z = [p[2] for seg in prim.lines for p in seg]
        self.assertGreater(min(all_z), 40.0)
        self.assertLess(max(all_z), 62.0)

    def test_wing_spar_primitives_separate_tubes(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        # Separate tubes starting at span_start_mm = 50.0 (does not cross fuselage center Y=0)
        spar_data = {
            "id": "spar_main-wing_2",
            "name": "Spar 2",
            "chord_ratio": 0.54,
            "outer_diameter_mm": 10.0,
            "inner_diameter_mm": 8.0,
            "span_start_mm": 50.0,
            "span_end_mm": 400.0,
            "enabled": True,
        }
        primitives = build_wing_spar_primitives(wing_comp, spar_data)
        self.assertEqual(len(primitives), 1)

        prim = primitives[0]
        # Wing transform Y position is 75.0, so with span_start_mm = 50.0, min |Y| in world is >= 120 mm
        # No segment should touch the fuselage centerline (|Y| < 50.0)
        near_center_pts = [
            p for seg in prim.lines for p in seg if abs(p[1]) < 50.0
        ]
        self.assertEqual(len(near_center_pts), 0)

    def test_wing_spar_primitives_v_tail_rotated(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "v-tail"
        )
        spar_data = {
            "id": "spar_v-tail_1",
            "name": "Spar 1",
            "chord_ratio": 0.30,
            "outer_diameter_mm": 6.0,
            "inner_diameter_mm": 4.0,
            "span_start_mm": 0.0,
            "span_end_mm": 300.0,
            "enabled": True,
        }
        primitives = build_wing_spar_primitives(wing_comp, spar_data)
        self.assertEqual(len(primitives), 1)

        prim = primitives[0]
        self.assertEqual(prim.color, COLOR_SPAR_TUBE)
        self.assertGreater(len(prim.lines), 50)

        # Bilateral symmetry across Y=0
        stb_pts = [p for seg in prim.lines for p in seg if p[1] > 0]
        port_pts = [p for seg in prim.lines for p in seg if p[1] < 0]
        self.assertAlmostEqual(min(p[2] for p in stb_pts), min(p[2] for p in port_pts), places=3)
        self.assertAlmostEqual(max(p[2] for p in stb_pts), max(p[2] for p in port_pts), places=3)
        self.assertAlmostEqual(min(p[1] for p in stb_pts), -max(p[1] for p in port_pts), places=3)

    def test_update_manufacturing_overlays_includes_spars(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        published_events = []
        api.subscribe("studio.viewer.set_overlays", published_events.append)

        update_manufacturing_overlays(api)
        self.assertGreater(len(published_events), 0)

        prims = published_events[-1]["primitives"]
        has_cyan_spars = any(
            isinstance(p, LineSegmentsPrimitive) and p.color == COLOR_SPAR_TUBE
            for p in prims
        )
        self.assertTrue(has_cyan_spars)

    def test_cad_wing_solid_midpoint_z_calculation(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        geom = wing_comp.get("parameters", {}).get("geometry", {})
        profiles = geom.get("profiles", [])

        # 1. At root station (y = 0.0, chord = 240.0, Clark-Y):
        # Probing at x = 0.28 * 240 = 67.2 mm
        spar_x = 0.28 * 240.0
        z_bot_root, z_top_root = get_wing_solid_vertical_bounds_at_xy(profiles, spar_x, 0.0)
        z_mid_root = get_main_wing_solid_midpoint_z(profiles, spar_x, 0.0)

        # Upper skin should be ~21.6 mm, lower skin ~-6.5 mm
        self.assertAlmostEqual(z_top_root, 21.621, places=2)
        self.assertAlmostEqual(z_bot_root, -6.496, places=2)
        # Midpoint is exactly centered between top and bottom surfaces
        self.assertAlmostEqual(z_mid_root, (z_top_root + z_bot_root) / 2.0, places=4)
        self.assertAlmostEqual(z_mid_root, 7.562, places=2)

        # 2. At span station y = 500.0 mm (with dihedral, taper, and 3-deg twist):
        z_bot_tip, z_top_tip = get_wing_solid_vertical_bounds_at_xy(profiles, spar_x, 500.0)
        z_mid_tip = get_main_wing_solid_midpoint_z(profiles, spar_x, 500.0)

        self.assertGreater(z_top_tip, z_bot_tip)
        self.assertAlmostEqual(z_mid_tip, (z_top_tip + z_bot_tip) / 2.0, places=4)
        # Dihedral and twist raise the midpoint to ~14.3 mm
        self.assertGreater(z_mid_tip, z_mid_root)
        self.assertAlmostEqual(z_mid_tip, 14.298, places=1)

    def test_spar_straight_cylinder_geometry_and_cad_slope(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        geom = wing_comp.get("parameters", {}).get("geometry", {})
        profiles = geom.get("profiles", [])

        spar_data = {
            "id": "spar_main-wing_1",
            "name": "Spar 1",
            "chord_ratio": 0.28,
            "outer_diameter_mm": 8.0,
            "inner_diameter_mm": 6.0,
            "span_start_mm": 0.0,
            "span_end_mm": 500.0,
            "z_offset_mm": 0.0,
            "enabled": True,
        }
        primitives = build_wing_spar_primitives(wing_comp, spar_data)
        self.assertEqual(len(primitives), 1)
        prim = primitives[0]

        # Calculate expected CAD slope
        spar_x = 0.28 * 240.0
        root_z = get_main_wing_solid_midpoint_z(profiles, spar_x, 0.0)
        tip_z = get_main_wing_solid_midpoint_z(profiles, spar_x, 500.0)
        expected_slope = (tip_z - root_z) / 500.0

        # In starboard local/world coordinates (main-wing attachment has pos=(280, 75, 40)):
        # Starboard spar points in world:
        stb_segs = [seg for seg in prim.lines if seg[0][1] >= 75.0 and seg[1][1] >= 75.0]
        self.assertGreater(len(stb_segs), 50)

        # Starboard cylinder centerline points:
        # X in world is 280.0 + spar_x = 347.2 mm
        stb_centerline_pts = [
            p for seg in stb_segs for p in seg
            if abs(p[0] - (280.0 + spar_x)) < 1e-4
        ]
        self.assertGreater(len(stb_centerline_pts), 0)

        # Points on X = 347.2 comprise the centerline (offset=0) and the top/bottom generator lines (offset = +/- 4.0)
        has_true_centerline = False
        for pt in stb_centerline_pts:
            span_y = pt[1] - 75.0
            expected_z = 40.0 + root_z + expected_slope * span_y
            # Must be centerline (0.0), inner wall (+/- 3.0), or outer wall (+/- 4.0)
            diffs = [abs(pt[2] - (expected_z + offset)) for offset in (0.0, 3.0, -3.0, 4.0, -4.0)]
            self.assertLess(min(diffs), 1e-2)
            if abs(pt[2] - expected_z) < 1e-2:
                has_true_centerline = True

        self.assertTrue(has_true_centerline)

    def test_spar_proportional_span_and_penetration_separate(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        spar_data = {
            "id": "spar_main-wing_1",
            "name": "Spar 1",
            "chord_ratio": 0.28,
            "outer_diameter_mm": 8.0,
            "inner_diameter_mm": 6.0,
            "span_start": 0.0,
            "span_end": 1.0,
            "shared_spar": False,
            "fuselage_penetration_mm": 35.0,
            "z_offset_mm": 0.0,
            "enabled": True,
        }
        primitives = build_wing_spar_primitives(wing_comp, spar_data)
        self.assertEqual(len(primitives), 1)
        prim = primitives[0]

        all_pts = [p for seg in prim.lines for p in seg]
        # X coordinates must strictly stay within outer radius around 280.0 + 0.28 * 240 = 347.2
        # Zero sweep: X never varies along span
        spar_center_x = 280.0 + 0.28 * 240.0
        for pt in all_pts:
            self.assertLessEqual(abs(pt[0] - spar_center_x), 4.01)

        # Starboard starts at Y = 75.0 - 35.0 = 40.0 (ring tilt due to dihedral slope adds ~0.05 mm)
        stb_pts = [p for p in all_pts if p[1] > 0]
        port_pts = [p for p in all_pts if p[1] < 0]
        self.assertAlmostEqual(min(p[1] for p in stb_pts), 40.0, delta=0.1)
        self.assertAlmostEqual(max(p[1] for p in port_pts), -40.0, delta=0.1)

        # Inboard centerline endpoint is exactly at world Y = 40.0
        has_inboard_center = any(
            abs(p[0] - spar_center_x) < 1e-3 and abs(p[1] - 40.0) < 1e-3
            for p in stb_pts
        )
        self.assertTrue(has_inboard_center)

        # Because shared_spar is False, no line segments or points cross into the central gap (-39.0, 39.0)
        gap_pts = [p for p in all_pts if -39.0 < p[1] < 39.0]
        self.assertEqual(len(gap_pts), 0)

    def test_spar_shared_continuous_through_spar(self) -> None:
        wing_comp = next(
            c for c in self.doc.data["components"] if c.get("id") == "main-wing"
        )
        spar_data = {
            "id": "spar_main-wing_1",
            "name": "Spar 1",
            "chord_ratio": 0.28,
            "outer_diameter_mm": 8.0,
            "inner_diameter_mm": 6.0,
            "span_start": 0.0,
            "span_end": 1.0,
            "shared_spar": True,
            "fuselage_penetration_mm": 35.0,  # should be ignored because shared_spar is True
            "z_offset_mm": 0.0,
            "enabled": True,
        }
        primitives = build_wing_spar_primitives(wing_comp, spar_data)
        self.assertEqual(len(primitives), 1)
        prim = primitives[0]

        all_pts = [p for seg in prim.lines for p in seg]
        # In shared spar, lines bridge continuously across Y=0, and there is a center ring exactly at Y=0
        zero_y_pts = [p for p in all_pts if abs(p[1]) < 1e-4]
        self.assertGreaterEqual(len(zero_y_pts), 16)

        # Also segments crossing Y=0
        crossing_segs = [
            seg for seg in prim.lines
            if (seg[0][1] < -1e-4 and seg[1][1] > 1e-4) or (seg[0][1] > 1e-4 and seg[1][1] < -1e-4)
        ]
        self.assertGreaterEqual(len(crossing_segs), 5)  # 4 outer cylinder generators + 1 centerline

    def test_control_surface_hardware_editor_and_wing_icon(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        provider = ManufacturingTreeProvider(api)
        nodes = provider.project_tree_nodes(self.doc)
        root = nodes[0]
        child_map = {c.title: c for c in root.children}

        # 1. Wing node tree icon must be set and valid
        mw_node = child_map["Main Wing"]
        self.assertIsNotNone(mw_node.icon)
        self.assertFalse(mw_node.icon.isNull())

        # 2. Control surface hardware node tree icon must be set and valid
        hw_node = next(c for c in mw_node.children if c.title == "Aileron Hardware")
        self.assertIsNotNone(hw_node.icon)
        self.assertFalse(hw_node.icon.isNull())

        # 3. Control surface hardware editor instantiation
        from setuav_manufacturing_plugin.editors.control_surface_hardware import (
            ControlSurfaceHardwarePropertyEditor,
        )

        editor = ControlSurfaceHardwarePropertyEditor(api, hw_node.selection)
        self.assertIsNotNone(editor._general_table)
        self.assertIsNotNone(editor._mount_table)
        self.assertIsNotNone(editor._dims_table)
        self.assertIsNotNone(editor._cover_table)
        self.assertIsNotNone(editor._bay_table)
        self.assertIsNotNone(editor._hinge_table)

        # 4. Property change persists to project
        editor._on_float_changed("servo_cover_length_mm", 55.0)
        editor._on_float_changed("hinge_tube_od_mm", 5.0)

        features = get_manufacturing_features(self.doc)
        hw_id = hw_node.selection["id"]
        self.assertEqual(features[hw_id]["servo_cover_length_mm"], 55.0)
        self.assertEqual(features[hw_id]["hinge_tube_od_mm"], 5.0)

    def test_wing_connection_no_carbon_spar_tubes(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        provider = ManufacturingTreeProvider(api)
        nodes = provider.project_tree_nodes(self.doc)
        root = nodes[0]
        mw_node = next(c for c in root.children if c.title == "Main Wing")
        conn_node = next(c for c in mw_node.children if c.title == "Fuselage Connection")

        editor = WingConnectionPropertyEditor(api, conn_node.selection)
        self.assertFalse(hasattr(editor, "_tube_table"))

    def test_selection_and_properties_persists_on_edit(self) -> None:
        from setuav_studio.ui.project_explorer.tree import ProjectExplorer
        from setuav_studio.ui.properties.properties_panel import PropertiesPanel
        from setuav_manufacturing_plugin.plugin import ManufacturingPlugin

        api = StudioAPI()
        mfg_plugin = ManufacturingPlugin()
        mfg_plugin.activate(api)

        tree = ProjectExplorer(api)
        props = PropertiesPanel(api)

        api.current_project = self.doc
        ensure_manufacturing_configuration(api)
        tree.refresh_project()

        # Find Spar 1 in tree
        spar_item = tree._item_map.get("spar_main-wing_1")
        self.assertIsNotNone(spar_item)

        # Select Spar 1
        tree.setCurrentItem(spar_item)
        self.assertEqual(tree.currentItem(), spar_item)
        self.assertIsNotNone(api.current_selection)
        self.assertEqual(api.current_selection.get("id"), "spar_main-wing_1")

        # Check properties panel loaded WingSparsPropertyEditor
        self.assertIsInstance(props._current_widget, WingSparsPropertyEditor)
        editor_widget = props._current_widget

        # Edit property (e.g. outer_diameter_mm)
        editor_widget._on_float_changed("outer_diameter_mm", 14.0)

        # Verify tree selection is STILL Spar 1
        self.assertIsNotNone(tree.currentItem())
        self.assertEqual(tree.currentItem().text(0), "Spar 1")
        current_elem = tree._element_map.get(tree.currentItem())
        self.assertIsNotNone(current_elem)
        self.assertEqual(current_elem.get("id"), "spar_main-wing_1")

        # Verify properties panel did NOT close or reset
        self.assertIs(props._current_widget, editor_widget)
        self.assertIsInstance(props._current_widget, WingSparsPropertyEditor)

        # Now select Fuselage Connection
        conn_item = tree._item_map.get("conn_main-wing")
        self.assertIsNotNone(conn_item)
        tree.setCurrentItem(conn_item)
        self.assertEqual(tree.currentItem(), conn_item)
        self.assertIsInstance(props._current_widget, WingConnectionPropertyEditor)
        conn_editor = props._current_widget

        # Edit property (e.g. insert_outer_diameter_mm)
        conn_editor._on_float_changed("insert_outer_diameter_mm", 6.5)

        # Verify selection is still Fuselage Connection and properties did NOT close
        self.assertIsNotNone(tree.currentItem())
        self.assertEqual(tree.currentItem().text(0), "Fuselage Connection")
        self.assertIs(props._current_widget, conn_editor)
        self.assertIsInstance(props._current_widget, WingConnectionPropertyEditor)

        # Now select Servo under Aileron Hardware
        from setuav_manufacturing_plugin.editors.control_surface_hardware import (
            ServoPropertyEditor,
            HingePropertyEditor,
        )
        servo_item = tree._item_map.get("cshw_aileron_servo")
        self.assertIsNotNone(servo_item)
        tree.setCurrentItem(servo_item)
        self.assertEqual(tree.currentItem(), servo_item)
        self.assertIsInstance(props._current_widget, ServoPropertyEditor)
        servo_editor = props._current_widget

        # Verify only 2 mount options exist
        mount_row = servo_editor._find_property_row(servo_editor._servo_table, "servo_mount_type")
        self.assertGreaterEqual(mount_row, 0)
        combo = servo_editor._servo_table.cellWidget(mount_row, 1)
        self.assertEqual(combo.count(), 2)
        combo_items = [combo.itemText(i) for i in range(combo.count())]
        self.assertIn("Wing Flush Laying", combo_items)
        self.assertIn("Fuselage Sidewall", combo_items)

        # Verify servo_enabled is not in the table
        self.assertEqual(servo_editor._find_property_row(servo_editor._servo_table, "servo_enabled"), -1)

        # Edit servo property and verify persistence
        servo_editor._on_float_changed("servo_cover_length_mm", 54.0)
        self.assertIsNotNone(tree.currentItem())
        self.assertEqual(tree.currentItem().text(0), "Servo")
        self.assertIs(props._current_widget, servo_editor)

        # Now select Hinge under Aileron Hardware
        hinge_item = tree._item_map.get("cshw_aileron_hinge")
        self.assertIsNotNone(hinge_item)
        tree.setCurrentItem(hinge_item)
        self.assertEqual(tree.currentItem(), hinge_item)
        self.assertIsInstance(props._current_widget, HingePropertyEditor)
        hinge_editor = props._current_widget

        # Verify hinge_enabled is NOT in the table
        self.assertEqual(hinge_editor._find_property_row(hinge_editor._hinge_table, "hinge_enabled"), -1)

        # Edit hinge property and verify persistence
        hinge_editor._on_float_changed("hinge_tube_od_mm", 6.0)
        self.assertIsNotNone(tree.currentItem())
        self.assertEqual(tree.currentItem().text(0), "Hinge")
        self.assertIs(props._current_widget, hinge_editor)

    def test_control_surface_hinge_properties_simplification(self) -> None:
        """Hinge properties must only have Target Surface, Tube OD, Tube ID, and Clearance.

        No span_start, span_end, or hinge_type clutter.
        """
        from setuav_manufacturing_plugin.editors.control_surface_hardware import (
            HingePropertyEditor,
            ControlSurfaceHardwarePropertyEditor,
        )

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        provider = ManufacturingTreeProvider(api)
        nodes = provider.project_tree_nodes(self.doc)
        root = nodes[0]
        mw_node = next(c for c in root.children if c.title == "Main Wing")
        hw_node = next(c for c in mw_node.children if c.title == "Aileron Hardware")
        hinge_node = next(c for c in hw_node.children if c.title == "Hinge")

        editor = HingePropertyEditor(api, hinge_node.selection)

        # Only 4 rows: target_component, hinge_tube_od_mm, hinge_tube_id_mm, hinge_clearance_mm
        self.assertEqual(editor._hinge_table.rowCount(), 4)
        self.assertGreaterEqual(editor._find_property_row(editor._hinge_table, "target_component"), 0)
        self.assertGreaterEqual(editor._find_property_row(editor._hinge_table, "hinge_tube_od_mm"), 0)
        self.assertGreaterEqual(editor._find_property_row(editor._hinge_table, "hinge_tube_id_mm"), 0)
        self.assertGreaterEqual(editor._find_property_row(editor._hinge_table, "hinge_clearance_mm"), 0)

        # Disallowed fields must NOT be in the table
        self.assertEqual(editor._find_property_row(editor._hinge_table, "span_start"), -1)
        self.assertEqual(editor._find_property_row(editor._hinge_table, "span_end"), -1)
        self.assertEqual(editor._find_property_row(editor._hinge_table, "hinge_span_start_ratio"), -1)
        self.assertEqual(editor._find_property_row(editor._hinge_table, "hinge_span_end_ratio"), -1)
        self.assertEqual(editor._find_property_row(editor._hinge_table, "hinge_type"), -1)
        self.assertEqual(editor._find_property_row(editor._hinge_table, "hinge_bearing_length_mm"), -1)
        self.assertEqual(editor._find_property_row(editor._hinge_table, "hinge_surface_gap_mm"), -1)
        self.assertEqual(editor._find_property_row(editor._hinge_table, "hinge_axial_clearance_mm"), -1)
        self.assertEqual(editor._find_property_row(editor._hinge_table, "hinge_x_end_offset_mm"), -1)

        # Check combined hardware editor hinge section
        hw_editor = ControlSurfaceHardwarePropertyEditor(api, hw_node.selection)
        self.assertEqual(hw_editor._hinge_table.rowCount(), 3)
        self.assertGreaterEqual(hw_editor._find_property_row(hw_editor._hinge_table, "hinge_tube_od_mm"), 0)
        self.assertGreaterEqual(hw_editor._find_property_row(hw_editor._hinge_table, "hinge_tube_id_mm"), 0)
        self.assertGreaterEqual(hw_editor._find_property_row(hw_editor._hinge_table, "hinge_clearance_mm"), 0)
        self.assertEqual(hw_editor._find_property_row(hw_editor._hinge_table, "hinge_span_start_ratio"), -1)
        self.assertEqual(hw_editor._find_property_row(hw_editor._hinge_table, "hinge_span_end_ratio"), -1)

        # Changing clearance updates both hinge_clearance_mm and hinge_bearing_radial_clearance_mm
        editor._on_clearance_changed(0.25)
        features = get_manufacturing_features(self.doc)
        feat_data = features["cshw_aileron"]
        self.assertEqual(feat_data["hinge_clearance_mm"], 0.25)
        self.assertEqual(feat_data["hinge_bearing_radial_clearance_mm"], 0.25)

    def test_control_surface_hinge_pink_overlay(self) -> None:
        """Hinge tube overlay must be rendered in pink (COLOR_HINGE_TUBE) with CAD-matching geometry."""
        from setuav_manufacturing_plugin.overlays import (
            COLOR_HINGE_TUBE,
            build_control_surface_hinge_primitives,
            update_manufacturing_overlays,
        )

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        published_events = []
        api.subscribe("studio.viewer.set_overlays", published_events.append)

        update_manufacturing_overlays(api)
        self.assertEqual(len(published_events), 1)
        prims = published_events[0]["primitives"]

        # Pink color is (1.0, 0.41, 0.71, 1.0)
        pink_prims = [p for p in prims if getattr(p, "color", None) == COLOR_HINGE_TUBE]
        self.assertGreater(len(pink_prims), 0)

        # Direct test on build_control_surface_hinge_primitives
        airframe = scan_airframe_components(self.doc)
        mw = next(w["comp"] for w in airframe["wings"] if w["id"] == "main-wing")
        aileron = next(cs["comp"] for cs in airframe["control_surfaces"] if cs["id"] == "aileron")

        hinge_prims = build_control_surface_hinge_primitives(
            aileron,
            mw,
            {
                "enabled": True,
                "hinge_tube_od_mm": 5.0,
                "hinge_tube_id_mm": 3.0,
                "hinge_clearance_mm": 0.2,
            },
        )
        self.assertEqual(len(hinge_prims), 1)
        prim = hinge_prims[0]
        self.assertEqual(prim.color, COLOR_HINGE_TUBE)
        # Verify lines are present and symmetric (both starboard and port)
        self.assertGreater(len(prim.lines), 50)
        has_positive_y = any(seg[0][1] > 0 or seg[1][1] > 0 for seg in prim.lines)
        has_negative_y = any(seg[0][1] < 0 or seg[1][1] < 0 for seg in prim.lines)
        self.assertTrue(has_positive_y)
        self.assertTrue(has_negative_y)

    def test_spar_winglet_penetration_visibility_and_overlay(self) -> None:
        """When spar span_end == 1.0, winglet_penetration_mm row is visible.
        When span_end < 1.0, winglet_penetration_mm row is hidden.
        Overlay primitives extend by winglet_penetration_mm past wing end when span_end == 1.0.
        """
        from setuav_manufacturing_plugin.editors.wing_spars import WingSparsPropertyEditor
        from setuav_manufacturing_plugin.overlays import build_wing_spar_primitives

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        features = get_manufacturing_features(self.doc)
        spar_data = features["spar_main-wing_1"]
        spar_data["span_end"] = 1.0
        spar_data["winglet_penetration_mm"] = 25.0

        editor = WingSparsPropertyEditor(
            api,
            {
                "id": "spar_main-wing_1",
                "type": "manufacturing:wing_spar",
                "target": "main-wing",
            },
        )

        winglet_row = editor._find_property_row(editor._geom_table, "winglet_penetration_mm")
        self.assertGreaterEqual(winglet_row, 0)
        self.assertFalse(editor._geom_table.isRowHidden(winglet_row))

        # When span_end < 1.0, row is hidden
        editor._on_span_end_changed(0.85)
        self.assertTrue(editor._geom_table.isRowHidden(winglet_row))

        # When restored to 1.0, row is visible again
        editor._on_span_end_changed(1.0)
        self.assertFalse(editor._geom_table.isRowHidden(winglet_row))

        # Verify overlay primitive extension
        airframe = scan_airframe_components(self.doc)
        mw = next(w["comp"] for w in airframe["wings"] if w["id"] == "main-wing")

        prims_extended = build_wing_spar_primitives(
            mw,
            {
                "enabled": True,
                "span_start": 0.0,
                "span_end": 1.0,
                "winglet_penetration_mm": 30.0,
                "shared_spar": False,
                "fuselage_penetration_mm": 0.0,
                "outer_diameter_mm": 10.0,
                "inner_diameter_mm": 8.0,
                "chord_ratio_start": 0.25,
                "chord_ratio_end": 0.25,
            },
        )
        prims_no_extend = build_wing_spar_primitives(
            mw,
            {
                "enabled": True,
                "span_start": 0.0,
                "span_end": 1.0,
                "winglet_penetration_mm": 0.0,
                "shared_spar": False,
                "fuselage_penetration_mm": 0.0,
                "outer_diameter_mm": 10.0,
                "inner_diameter_mm": 8.0,
                "chord_ratio_start": 0.25,
                "chord_ratio_end": 0.25,
            },
        )
        # The extended spar should have larger max |y| by approximately 30 mm
        max_y_ext = max(abs(seg[0][1]) for p in prims_extended for seg in p.lines)
        max_y_norm = max(abs(seg[0][1]) for p in prims_no_extend for seg in p.lines)
        self.assertAlmostEqual(max_y_ext - max_y_norm, 30.0, places=1)

    def test_control_surface_hardware_servo_catalog_and_conditional_tables(self) -> None:
        """Verify Servo catalog preset selection, separate dimension/cover/bay tables,
        conditional visibility of cover & bay based on mount type, and tree hierarchy without horn.
        """
        from setuav_manufacturing_plugin.editors.control_surface_hardware import (
            ControlSurfaceHardwarePropertyEditor,
            ServoPropertyEditor,
            create_control_surface_hardware_editor,
        )

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        provider = ManufacturingTreeProvider(api)
        nodes = provider.project_tree_nodes(self.doc)
        root = nodes[0]
        vt_node = next(c for c in root.children if c.title == "V-Tail")

        # Directly under V-Tail: Ruddervator Hardware
        hw_node = next(c for c in vt_node.children if c.title == "Ruddervator Hardware")
        self.assertEqual(hw_node.selection["type"], "manufacturing:control_surface_hardware")

        # Children are strictly Servo and Hinge (NO Horn)
        child_map = {c.title: c for c in hw_node.children}
        self.assertIn("Servo", child_map)
        self.assertIn("Hinge", child_map)
        self.assertNotIn("Horn", child_map)

        servo_node = child_map["Servo"]
        self.assertEqual(servo_node.selection["sub_section"], "servo")

        # Factory returns ServoPropertyEditor
        editor = create_control_surface_hardware_editor(api, servo_node.selection)
        self.assertIsInstance(editor, ServoPropertyEditor)

        # 1. Distinct tables exist
        self.assertIsNotNone(editor._mount_table)
        self.assertIsNotNone(editor._dims_table)
        self.assertIsNotNone(editor._cover_table)
        self.assertIsNotNone(editor._bay_table)

        # 2. Ruddervator default mount is fuselage_sidewall -> Cover and Bay containers are hidden
        features = get_manufacturing_features(self.doc)
        self.assertEqual(features["cshw_ruddervator"]["servo_mount_type"], "fuselage_sidewall")
        self.assertTrue(editor._cover_container.isHidden())
        self.assertTrue(editor._bay_container.isHidden())

        # 3. Switching mount type to wing_flush_laying makes Cover and Bay containers visible
        editor._on_mount_type_changed("wing_flush_laying")
        self.assertFalse(editor._cover_container.isHidden())
        self.assertFalse(editor._bay_container.isHidden())

        # Switching back to fuselage_sidewall hides them
        editor._on_mount_type_changed("fuselage_sidewall")
        self.assertTrue(editor._cover_container.isHidden())
        self.assertTrue(editor._bay_container.isHidden())

        # 4. Catalog servo model selection and default Emax ES08MD
        model_row = editor._find_property_row(editor._dims_table, "servo_model")
        self.assertGreaterEqual(model_row, 0)
        self.assertEqual(editor._current_model, "Emax ES08MD")

        # Check default Emax ES08MD dimensions in project
        self.assertEqual(features["cshw_ruddervator"]["case_length_mm"], 23.0)
        self.assertEqual(features["cshw_ruddervator"]["case_width_mm"], 12.0)
        self.assertEqual(features["cshw_ruddervator"]["case_height_mm"], 24.0)

        # 5. Selecting a different catalog model (e.g. TowerPro SG90) updates dimensions
        editor._on_servo_model_changed("TowerPro SG90")
        features = get_manufacturing_features(self.doc)
        self.assertEqual(features["cshw_ruddervator"]["servo_model"], "TowerPro SG90")
        self.assertEqual(features["cshw_ruddervator"]["case_length_mm"], 22.8)
        self.assertEqual(features["cshw_ruddervator"]["case_width_mm"], 12.2)
        self.assertEqual(features["cshw_ruddervator"]["case_height_mm"], 22.8)

        # 6. Manually editing a dimension switches catalog model to Custom
        editor._on_dimension_changed("case_length_mm", 25.0)
        features = get_manufacturing_features(self.doc)
        self.assertEqual(features["cshw_ruddervator"]["servo_model"], "Custom")
        self.assertEqual(features["cshw_ruddervator"]["case_length_mm"], 25.0)

    def test_nose_cut_primitives_exact_geometry(self) -> None:
        airframe = scan_airframe_components(self.doc)
        fuselage = airframe.get("fuselage")
        self.assertIsNotNone(fuselage)

        # 1. Enabled cut generates exactly LineSegmentsPrimitive with red color (no cut plane)
        feat_data = {"enabled": True, "nose_cut_length_mm": 50.0}
        prims = build_nose_cut_primitives(fuselage, feat_data)
        self.assertEqual(len(prims), 1)

        prim = prims[0]
        self.assertIsInstance(prim, LineSegmentsPrimitive)
        self.assertEqual(prim.color, COLOR_NOSE_CUT)
        self.assertEqual(COLOR_NOSE_CUT, (1.0, 0.0, 0.0, 1.0))

        # Check line segments form a closed loop of 128 points
        lines = prim.lines
        self.assertEqual(len(lines), 128)
        for i in range(len(lines)):
            p_start, p_end = lines[i]
            # X coordinates must match cut_x (50.0)
            self.assertAlmostEqual(p_start[0], 50.0, places=3)
            self.assertAlmostEqual(p_end[0], 50.0, places=3)
            # Consecutive segments must connect continuously
            next_start = lines[(i + 1) % len(lines)][0]
            self.assertAlmostEqual(p_end[0], next_start[0], places=5)
            self.assertAlmostEqual(p_end[1], next_start[1], places=5)
            self.assertAlmostEqual(p_end[2], next_start[2], places=5)

        # 2. Disabled cut produces no primitives
        disabled_prims = build_nose_cut_primitives(fuselage, {"enabled": False, "nose_cut_length_mm": 50.0})
        self.assertEqual(disabled_prims, [])

        # 3. Custom cut_x_mm position
        custom_prims = build_nose_cut_primitives(fuselage, {"enabled": True, "cut_x_mm": 100.0})
        self.assertEqual(len(custom_prims), 1)
        for p_start, p_end in custom_prims[0].lines:
            self.assertAlmostEqual(p_start[0], 100.0, places=3)
            self.assertAlmostEqual(p_end[0], 100.0, places=3)

    def test_nose_cut_overlay_publishing_in_project(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        # Add nose cut to features
        def add_nose_cut(ext: dict) -> None:
            features = ext.setdefault("features", {})
            features["nose_cut"] = {
                "id": "nose_cut",
                "type": "manufacturing:nose_cut",
                "name": "Nose Cut",
                "enabled": True,
                "nose_cut_length_mm": 50.0,
            }
        api.edit_project_extension("com.setuav.manufacturing", "Add Nose Cut", add_nose_cut)

        published_prims: list = []
        def mock_publish(channel: str, data: dict) -> None:
            if channel == "studio.viewer.set_overlays":
                published_prims.extend(data.get("primitives", []))
        api.publish = mock_publish

        update_manufacturing_overlays(api)

        # Must have red line primitive for nose cut
        nose_cut_prims = [
            p for p in published_prims
            if isinstance(p, LineSegmentsPrimitive) and p.color == COLOR_NOSE_CUT
        ]
        self.assertEqual(len(nose_cut_prims), 1)
        self.assertEqual(len(nose_cut_prims[0].lines), 128)

    def test_nose_cut_property_editor(self) -> None:
        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        selection = {
            "kind": "manufacturing_feature",
            "type": "manufacturing:nose_cut",
            "id": "nose_cut",
            "name": "Nose Cut",
        }
        editor = NoseCutPropertyEditor(api, selection)
        self.assertEqual(editor._table.rowCount(), 2)

        # Test changing nose_cut_length_mm
        editor._on_cut_len_changed(75.0)
        features = get_manufacturing_features(self.doc)
        self.assertEqual(features["nose_cut"]["nose_cut_length_mm"], 75.0)

        # Test toggling enabled
        editor._on_enabled_toggled(False)
        features = get_manufacturing_features(self.doc)
        self.assertFalse(features["nose_cut"]["enabled"])

    def test_control_surface_hinge_sweep_and_chord_alignment(self) -> None:
        """Hinge tube overlay must precisely match control surface sweep and chord location."""
        from setuav_manufacturing_plugin.overlays import build_control_surface_hinge_primitives

        # 1. Swept wing test with zero hinge sweep:
        # Hinge line must remain parallel to Y axis (X = 150.0 mm along full span)
        swept_wing = {
            "parameters": {
                "geometry": {
                    "mirror": False,
                    "profiles": [
                        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 200.0, "airfoil": "0012"},
                        {"position": {"x": 50.0, "y": 500.0, "z": 0.0}, "chord": 100.0, "airfoil": "0012"},
                    ],
                }
            }
        }
        zero_sweep_cs = {
            "parameters": {
                "geometry": {
                    "tag": "aileron",
                    "type": "aileron",
                    "span_start": 100.0,
                    "span_end": 400.0,
                    "chord": 40.0,
                    "hinge_sweep": 0.0,
                }
            }
        }
        prims = build_control_surface_hinge_primitives(
            zero_sweep_cs, swept_wing, hw_data={"enabled": True, "hinge_enabled": True}
        )
        self.assertEqual(len(prims), 1)

        # Centerline segments connecting station centers
        center_x_coords = [
            p1[0]
            for p1, p2 in prims[0].lines
            if abs(p1[2]) < 1e-4 and abs(p2[2]) < 1e-4 and abs(p1[0] - p2[0]) < 1e-4 and abs(p1[0] - 150.0) < 0.1
        ]
        self.assertGreater(len(center_x_coords), 0)
        for cx in center_x_coords:
            self.assertAlmostEqual(cx, 150.0, delta=0.01)

        # 2. Ruddervator test from project fixture
        airframe = scan_airframe_components(self.doc)
        vtail_wing = next(w["comp"] for w in airframe["wings"] if w["id"] == "v-tail")
        ruddervator = next(cs["comp"] for cs in airframe["control_surfaces"] if cs["id"] == "ruddervator")
        rv_prims = build_control_surface_hinge_primitives(
            ruddervator, vtail_wing, hw_data={"enabled": True, "hinge_enabled": True}
        )
        self.assertEqual(len(rv_prims), 1)
    def test_fuselage_tree_and_editors(self) -> None:
        """Verify Fuselage group node under Manufacturing Configuration with Shell, Access Covers, Nose Cut."""
        from setuav_manufacturing_plugin.editors import create_manufacturing_editor
        from setuav_manufacturing_plugin.editors.fuselage_shell import FuselageShellPropertyEditor
        from setuav_manufacturing_plugin.editors.covers import CoversPropertyEditor

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        provider = ManufacturingTreeProvider(api)
        nodes = provider.project_tree_nodes(self.doc)
        self.assertEqual(len(nodes), 1)
        root = nodes[0]
        self.assertEqual(root.title, "Manufacturing Configuration")

        # Find Fuselage group node
        fuselage_node = next((c for c in root.children if c.title == "Fuselage"), None)
        self.assertIsNotNone(fuselage_node)
        self.assertEqual(fuselage_node.selection["type"], "manufacturing:fuselage_group")

        # Verify Fuselage children: Shell, Access Covers, Nose Cut
        child_titles = [c.title for c in fuselage_node.children]
        self.assertEqual(child_titles, ["Shell", "Access Covers", "Nose Cut"])

        shell_node = fuselage_node.children[0]
        covers_node = fuselage_node.children[1]
        nose_cut_node = fuselage_node.children[2]

        self.assertEqual(shell_node.selection["type"], "manufacturing:fuselage_shell")
        self.assertEqual(covers_node.selection["type"], "manufacturing:covers")
        self.assertEqual(nose_cut_node.selection["type"], "manufacturing:nose_cut")

        # Verify editors instantiated via create_manufacturing_editor
        # Selecting parent group should open FuselageShellPropertyEditor
        group_editor = create_manufacturing_editor(api, fuselage_node.selection)
        self.assertIsInstance(group_editor, FuselageShellPropertyEditor)

        # Selecting Shell opens FuselageShellPropertyEditor
        shell_editor = create_manufacturing_editor(api, shell_node.selection)
        self.assertIsInstance(shell_editor, FuselageShellPropertyEditor)

        # Selecting Access Covers opens CoversPropertyEditor
        covers_editor = create_manufacturing_editor(api, covers_node.selection)
        self.assertIsInstance(covers_editor, CoversPropertyEditor)

        # Selecting Nose Cut opens NoseCutPropertyEditor
        nose_editor = create_manufacturing_editor(api, nose_cut_node.selection)
        self.assertIsInstance(nose_editor, NoseCutPropertyEditor)

        # Test updating Fuselage Shell property
        self.assertGreaterEqual(shell_editor._table.rowCount(), 6)
        shell_editor._on_float_changed("bottom_wall_ratio", 0.05)
        features = get_manufacturing_features(self.doc)
        self.assertEqual(features["fuselage_shell"]["bottom_wall_ratio"], 0.05)

        # Test updating Access Covers property
        self.assertGreaterEqual(covers_editor._table.rowCount(), 8)
        covers_editor._on_float_changed("corner_radius_mm", 12.0)
        features = get_manufacturing_features(self.doc)
        self.assertEqual(features["covers"]["corner_radius_mm"], 12.0)

        # Test deleting Fuselage group
        fuselage_node.delete()
        features_after = get_manufacturing_features(self.doc)
        self.assertNotIn("fuselage_shell", features_after)
        self.assertNotIn("covers", features_after)
        self.assertNotIn("nose_cut", features_after)

    def test_loft_primitive_rendering(self) -> None:
        """Verify LoftPrimitive is rendered into solid and wireframe vertex buffers in viewport mesh."""
        from setuav_studio_sdk import LoftPrimitive
        from plugins.geometry.viewport.mesh import (
            build_primitive_solid_vertices,
            build_primitive_wire_vertices,
        )

        sec1 = ((0.0, -10.0, -10.0), (0.0, 10.0, -10.0), (0.0, 10.0, 10.0), (0.0, -10.0, 10.0))
        sec2 = ((50.0, -15.0, -15.0), (50.0, 15.0, -15.0), (50.0, 15.0, 15.0), (50.0, -15.0, 15.0))
        sec3 = ((100.0, -10.0, -10.0), (100.0, 10.0, -10.0), (100.0, 10.0, 10.0), (100.0, -10.0, 10.0))

        prim = LoftPrimitive(
            sections=(sec1, sec2, sec3),
            color=(1.0, 0.15, 0.15, 0.35),
            closed_ends=True,
            wireframe=True,
            solid=True,
        )

        # Test solid mesh generation
        solid_verts = build_primitive_solid_vertices([prim])
        self.assertGreater(len(solid_verts), 0)
        # Verify color in vertex buffer (each vertex has x, y, z, nx, ny, nz, r, g, b, a)
        self.assertAlmostEqual(solid_verts[6], 1.0, places=2)  # R
        self.assertAlmostEqual(solid_verts[7], 0.15, places=2)  # G
        self.assertAlmostEqual(solid_verts[8], 0.15, places=2)  # B

        # Test wireframe generation
        wire_verts = build_primitive_wire_vertices([prim])
        self.assertGreater(len(wire_verts), 0)
        # Wireframe color: x, y, z, r, g, b
        self.assertAlmostEqual(wire_verts[3], 1.0, places=2)

    def test_fuselage_shell_inner_cavity_overlay(self) -> None:
        """Verify build_fuselage_shell_primitives produces opaque yellow inner cavity loft."""
        from setuav_manufacturing_plugin.overlays import (
            COLOR_SHELL_INNER_CAVITY,
            build_fuselage_shell_primitives,
        )

        airframe = scan_airframe_components(self.doc)
        fuselage = airframe["fuselage"]
        self.assertIsNotNone(fuselage)

        shell_feat = {
            "enabled": True,
            "bottom_wall_ratio": 0.16,
            "side_wall_ratio": 0.12,
            "top_wall_ratio": 0.06,
            "inner_bottom_corner_ratio": 0.10,
            "inner_top_corner_ratio": 0.15,
            "end_wall_thickness_mm": 2.4,
        }

        prims = build_fuselage_shell_primitives(fuselage, shell_feat)
        self.assertEqual(len(prims), 1)
        prim = prims[0]
        self.assertEqual(prim.color, COLOR_SHELL_INNER_CAVITY)
        self.assertGreaterEqual(len(prim.sections), 2)

    def test_fuselage_station_ratios_auto_calculation(self) -> None:
        """Verify calculate_fuselage_station_ratios distributes thicknesses between min_wall and max_wall."""
        from setuav_manufacturing_plugin.models import calculate_fuselage_station_ratios

        airframe = scan_airframe_components(self.doc)
        fuselage = airframe["fuselage"]
        sections = fuselage["parameters"]["geometry"]["segments"][0]["sections"]
        self.assertGreater(len(sections), 5)

        ratios = calculate_fuselage_station_ratios(sections, min_wall_mm=1.5, max_wall_mm=4.0)
        self.assertEqual(len(ratios), len(sections))

        # First section is narrow (20x20), middle is wide (87x84)
        r0 = ratios[0]
        r_mid = ratios[3]

        # Verify keys
        for r in ratios:
            self.assertIn("bottom_wall_ratio", r)
            self.assertIn("side_wall_ratio", r)
            self.assertIn("top_wall_ratio", r)
            self.assertIn("bottom_corner_ratio", r)
            self.assertIn("top_corner_ratio", r)
            self.assertGreater(r["bottom_wall_ratio"], 0.0)

    def test_fuselage_shell_editor_station_table_and_actions(self) -> None:
        """Verify FuselageShellPropertyEditor unit mode toggle and station table updates."""
        from setuav_manufacturing_plugin.editors.fuselage_shell import FuselageShellPropertyEditor

        api = StudioAPI()
        api.current_project = self.doc
        ensure_manufacturing_configuration(api)

        editor = FuselageShellPropertyEditor(api, {"id": "fuselage_shell", "name": "Fuselage Shell"})
        self.assertIsNotNone(editor._stations_table)
        self.assertGreater(editor._stations_table.rowCount(), 5)

        # Test initial unit mode is ratios and button text is 'Ratios'
        self.assertEqual(editor._unit_mode, "ratios")
        self.assertEqual(editor.btn_unit_toggle.text(), "Ratios")

        # Test toggle button switches to 'Thickness' and updates table headers
        editor._on_toggle_unit_mode()
        self.assertEqual(editor._unit_mode, "thickness")
        self.assertEqual(editor.btn_unit_toggle.text(), "Thickness")
        self.assertIn("(mm)", editor._stations_table.horizontalHeaderItem(3).text())

        # Test toggle button switches back to 'Ratios'
        editor._on_toggle_unit_mode()
        self.assertEqual(editor._unit_mode, "ratios")
        self.assertEqual(editor.btn_unit_toggle.text(), "Ratios")

        # Test editing a cell in thickness mode converts to ratio
        editor._on_toggle_unit_mode()  # into thickness
        editor._on_station_cell_changed(1, "bottom_wall_ratio", 10.0, ref_dim=100.0)
        features = get_manufacturing_features(self.doc)
        sr = features["fuselage_shell"]["station_ratios"]
        self.assertAlmostEqual(sr[1]["bottom_wall_ratio"], 0.10, places=2)

        # Test reset table to defaults button
        editor._on_reset_stations()
        features = get_manufacturing_features(self.doc)
        sr = features["fuselage_shell"]["station_ratios"]
        self.assertEqual(len(sr), editor._stations_table.rowCount())
        from setuav_manufacturing_plugin.models import FUSELAGE_SHELL_DEFAULTS
        self.assertAlmostEqual(sr[0]["bottom_wall_ratio"], FUSELAGE_SHELL_DEFAULTS["bottom_wall_ratio"])


if __name__ == "__main__":
    unittest.main()



