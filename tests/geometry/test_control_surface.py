"""Unit and integration tests for control surfaces, cutouts, deflection, and editor."""

from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import QComboBox

from plugins.geometry.engine.fuselage_geometry import build_fuselage_geometry
from plugins.geometry.engine.lifting_surface_geometry import (
    build_lifting_surface_geometry,
)
from plugins.geometry.engine.scene import GeometryProvider, build_project_geometry
from setuav_studio.project import ProjectDocument
from tests._common import cell_widget, get_qapp


class ControlSurfaceGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_control_surface_cutouts_and_deflection(self) -> None:
        from plugins.geometry.engine.lifting_surface_geometry import (
            build_lifting_surface_geometry,
        )

        wing_component = {
            "id": "test-wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "airfoil": "2412",
                        },
                        {
                            "position": {"x": 20.0, "y": 500.0, "z": 0.0},
                            "chord": 150.0,
                            "airfoil": "2412",
                        },
                    ],
                }
            },
        }
        cs_geom = {
            "id": "aileron_1",
            "type": "aileron",
            "span_start": 200.0,
            "span_end": 450.0,
            "chord": 40.0,
            "deflection": 20.0,
        }

        lofts = build_lifting_surface_geometry(wing_component, control_surfaces=[cs_geom])
        # Should produce:
        # 1. Inboard wing segment (0 - 200 mm)
        # 2. Main wing body at CS segment (200 - 450 mm)
        # 3. Deflected control surface flap (200 - 450 mm)
        # 4. Outboard wing segment (450 - 500 mm)
        self.assertEqual(len(lofts), 4)

        main_lofts = [loft for loft in lofts if loft.component_id == "test-wing"]
        cs_loft = next(loft for loft in lofts if "aileron_1" in loft.component_id)
        self.assertEqual(len(main_lofts), 3)
        self.assertIsNotNone(cs_loft)

        # All sections in all lofts must have exact 64 points
        for loft in lofts:
            for sec in loft.sections:
                self.assertEqual(len(sec.points), 64)

        # Compare neutral (deflection=0) vs deflected (deflection=20)
        cs_neutral_geom = deepcopy(cs_geom)
        cs_neutral_geom["deflection"] = 0.0
        lofts_neutral = build_lifting_surface_geometry(
            wing_component, control_surfaces=[cs_neutral_geom]
        )
        cs_neutral = next(loft for loft in lofts_neutral if "aileron_1" in loft.component_id)

        # Find trailing edge index (maximum X)
        te_idx = max(
            range(len(cs_neutral.sections[0].points)),
            key=lambda i: cs_neutral.sections[0].points[i][0],
        )
        te_neutral_z = cs_neutral.sections[0].points[te_idx][2]
        te_deflected_z = cs_loft.sections[0].points[te_idx][2]
        self.assertLess(te_deflected_z, te_neutral_z - 5.0)

        # Test Mirrored Instance (anti-symmetric roll deflection for aileron)
        proj_data = {
            "components": [
                wing_component,
                {
                    "kind": "component",
                    "id": "aileron_1",
                    "type": "org.setuav.core:control-surface",
                    "attach_to": "test-wing",
                    "parameters": {"geometry": cs_geom},
                },
                {
                    "kind": "instance",
                    "id": "test-wing-mirrored",
                    "source": "test-wing",
                    "derivation": {"type": "mirror", "plane": "XZ"},
                },
            ]
        }
        doc = ProjectDocument(Path("/tmp/test.json"), "json", proj_data)
        providers: dict[str, GeometryProvider] = {
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry
        }
        scene_geom = build_project_geometry(doc, providers)

        cs_source = next(
            loft for loft in scene_geom.lofts if loft.component_id == "test-wing:aileron_1"
        )
        cs_mirror = next(
            loft for loft in scene_geom.lofts if loft.component_id == "test-wing-mirrored:aileron_1"
        )

        te_src_z = max(cs_source.sections[0].points, key=lambda p: p[0])[2]
        te_mir_z = max(cs_mirror.sections[0].points, key=lambda p: p[0])[2]

        # Right deflects down, Left deflects up (anti-symmetric)
        self.assertLess(te_src_z, 0.0)
        self.assertGreater(te_mir_z, 0.0)

    def test_vtail_left_control_surfaces(self) -> None:
        v_tail_left = {
            "kind": "component",
            "type": "org.setuav.core:lifting-surface",
            "id": "v-tail-left",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 165.0,
                            "airfoil": "0012",
                        },
                        {
                            "position": {"x": 50.0, "y": -180.0, "z": 0.0},
                            "chord": 100.0,
                            "airfoil": "0012",
                        },
                    ],
                }
            },
        }
        cs_list = [
            {
                "id": "elevator",
                "type": "elevator",
                "span_start": 50.0,
                "span_end": 100.0,
                "chord": 30.0,
                "deflection": 10.0,
            }
        ]

        lofts = build_lifting_surface_geometry(v_tail_left, control_surfaces=cs_list)
        self.assertEqual(len(lofts), 4)
        cs_loft = next((loft for loft in lofts if "elevator" in loft.component_id), None)
        self.assertIsNotNone(cs_loft)
        assert cs_loft is not None
        self.assertEqual(len(cs_loft.sections), 2)
        for loft in lofts:
            for sec in loft.sections:
                self.assertEqual(len(sec.points), 64)

    def test_control_surface_hinge_sweep(self) -> None:
        wing_with_sweep = {
            "kind": "component",
            "type": "org.setuav.core:lifting-surface",
            "id": "swept-wing",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "airfoil": "0012",
                        },
                        {
                            "position": {"x": 50.0, "y": 500.0, "z": 0.0},
                            "chord": 100.0,
                            "airfoil": "0012",
                        },
                    ],
                }
            },
        }
        cs_list = [
            {
                "id": "aileron",
                "type": "aileron",
                "span_start": 100.0,
                "span_end": 400.0,
                "chord": 40.0,
                "hinge_sweep": 0.0,  # Parallel to Y axis (zero sweep)
                "deflection": 0.0,
            }
        ]

        lofts = build_lifting_surface_geometry(wing_with_sweep, control_surfaces=cs_list)
        cs_loft = next(loft for loft in lofts if "aileron" in loft.component_id)
        self.assertEqual(len(cs_loft.sections), 2)
        # Top hinge line X location should be exactly 150.0 mm at both section 0 and section 1
        hinge_sec0_x = cs_loft.sections[0].points[27][0]
        hinge_sec1_x = cs_loft.sections[1].points[27][0]
        self.assertAlmostEqual(hinge_sec0_x, 150.0, delta=0.1)
        self.assertAlmostEqual(hinge_sec1_x, 150.0, delta=0.1)

    def test_control_surface_editor(self) -> None:
        from plugins.geometry.editors.control_surface import ControlSurfaceEditor
        from setuav_studio.api import StudioAPI

        api = StudioAPI()
        cs_comp = {
            "kind": "component",
            "id": "aileron",
            "name": "Aileron",
            "type": "org.setuav.core:control-surface",
            "attach_to": "main-wing",
            "mass": 25.0,
            "parameters": {
                "geometry": {
                    "type": "aileron",
                    "span_start": 250.0,
                    "span_end": 500.0,
                    "chord": 70.0,
                    "deflection": 20.0,
                    "hinge_sweep": -1.0,
                },
            },
        }

        editor = ControlSurfaceEditor(api, cs_comp)
        self.assertEqual(editor._property_text(editor.general_table, 0), "Aileron")
        type_widget = cell_widget(editor.properties_table, 0, 1, QComboBox)
        self.assertEqual(type_widget.currentData(), "aileron")

        # Edit deflection
        editor._on_prop_spinbox_changed("deflection", -15.0)
        self.assertEqual(cs_comp["parameters"]["geometry"]["deflection"], -15.0)

        # Edit eta_start and chord_fraction
        editor._on_prop_spinbox_changed("eta_start", 0.35)
        self.assertAlmostEqual(cs_comp["parameters"]["geometry"]["eta_start"], 0.35)
        editor._on_prop_spinbox_changed("chord_fraction", 0.28)
        self.assertAlmostEqual(cs_comp["parameters"]["geometry"]["chord_fraction"], 0.28)

        # Edit type to elevon and symmetry_mode
        editor._on_prop_combo_changed("type", "elevon")
        self.assertEqual(cs_comp["parameters"]["geometry"]["type"], "elevon")
        editor._on_prop_combo_changed("symmetry_mode", "symmetric")
        self.assertEqual(cs_comp["parameters"]["geometry"]["symmetry_mode"], "symmetric")

    def test_control_surface_sizing_modes_and_live_sync(self) -> None:
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.api import StudioAPI

        wing_comp = {
            "kind": "component",
            "id": "main-wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "chord": 200.0,
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "airfoil": "2412",
                        },
                        {
                            "chord": 100.0,
                            "position": {"x": 50.0, "y": 1000.0, "z": 0.0},
                            "airfoil": "2412",
                        },
                    ],
                }
            },
        }
        cs0_comp = {
            "kind": "component",
            "id": "aileron_ratio",
            "type": "org.setuav.core:control-surface",
            "attach_to": "main-wing",
            "parameters": {
                "geometry": {
                    "type": "aileron",
                    "span_mode": "ratio",
                    "eta_start": 0.5,
                    "eta_end": 0.9,
                    "span_start": 500.0,
                    "span_end": 900.0,
                    "chord_mode": "ratio",
                    "chord_fraction": 0.25,
                    "chord": 50.0,
                }
            },
        }
        cs1_comp = {
            "kind": "component",
            "id": "flap_dim",
            "type": "org.setuav.core:control-surface",
            "attach_to": "main-wing",
            "parameters": {
                "geometry": {
                    "type": "flap",
                    "span_mode": "dimension",
                    "span_start": 100.0,
                    "span_end": 400.0,
                    "eta_start": 0.1,
                    "eta_end": 0.4,
                    "chord_mode": "dimension",
                    "chord": 45.0,
                    "chord_fraction": 0.225,
                }
            },
        }
        doc = ProjectDocument(
            Path("/tmp/test.json"), "json", {"components": [wing_comp, cs0_comp, cs1_comp]}
        )
        api = StudioAPI()
        api._host.set_project(doc)
        editor = LiftingSurfaceEditor(api, wing_comp)

        # 1. Test live spinbox sync when user edits eta_start on aileron (index 0)
        editor._load_control_surface(0)
        editor._on_cs_prop_spinbox_changed("eta_start", 0.6)
        geom0 = cs0_comp["parameters"]["geometry"]
        self.assertAlmostEqual(geom0["eta_start"], 0.6)
        self.assertAlmostEqual(geom0["span_start"], 600.0)  # 0.6 * 1000.0

        # 2. Scale the wing span from 1000 to 2000 mm
        wing_comp["parameters"]["geometry"]["profiles"][1]["position"]["y"] = 2000.0
        editor._sync_control_surfaces_with_surface()

        # Ratio aileron should scale its span_start from 600mm to 1200mm (0.6 * 2000)
        self.assertAlmostEqual(geom0["span_start"], 1200.0)
        self.assertAlmostEqual(geom0["span_end"], 1800.0)  # 0.9 * 2000

        # Dimension flap should keep its fixed 100-400mm span, but eta updates to 0.05 - 0.20
        geom1 = cs1_comp["parameters"]["geometry"]
        self.assertAlmostEqual(geom1["span_start"], 100.0)
        self.assertAlmostEqual(geom1["span_end"], 400.0)
        self.assertAlmostEqual(geom1["eta_start"], 0.05)
        self.assertAlmostEqual(geom1["eta_end"], 0.20)

    def test_control_surface_expression_error_and_atomic_undo(self) -> None:
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.api import StudioAPI
        from setuav_studio.model.expression import get_expression
        from setuav_studio.ui.widget.table import ExpressionPropertyCell

        wing_comp = {
            "kind": "component",
            "id": "main-wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "chord": 200.0,
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "airfoil": "2412",
                        },
                        {
                            "chord": 100.0,
                            "position": {"x": 50.0, "y": 1000.0, "z": 0.0},
                            "airfoil": "2412",
                        },
                    ],
                }
            },
        }
        cs_comp = {
            "kind": "component",
            "id": "aileron-1",
            "type": "org.setuav.core:control-surface",
            "attach_to": "main-wing",
            "parameters": {
                "geometry": {
                    "type": "aileron",
                    "span_mode": "ratio",
                    "eta_start": 0.5,
                    "eta_end": 0.9,
                    "chord_mode": "ratio",
                    "chord_fraction": 0.25,
                }
            },
        }
        doc = ProjectDocument(
            Path("/tmp/test-err.json"),
            "json",
            {"parameters": {"ref_eta": 0.5}, "components": [wing_comp, cs_comp]},
        )
        statuses: list[tuple[str, str, int]] = []
        api = StudioAPI()
        api._host.bind_status_handler(lambda msg, lvl, ms: statuses.append((msg, lvl, ms)))
        api._host.set_project(doc)
        editor = LiftingSurfaceEditor(api, wing_comp)
        self.addCleanup(editor.deleteLater)
        editor._load_control_surface(0)

        editor._on_cs_prop_spinbox_changed("eta_start", "=missing_symbol * 2")

        eta_cell = editor._property_cell(editor.cs_properties_table, "eta_start")
        assert isinstance(eta_cell, ExpressionPropertyCell)
        self.assertTrue(eta_cell._has_error)
        self.assertTrue(any(lvl == "error" and "missing_symbol" in msg for msg, lvl, _ in statuses))

        cs_geom = cs_comp["parameters"]["geometry"]
        self.assertAlmostEqual(cs_geom["eta_start"], 0.5)
        self.assertIsNone(get_expression(cs_geom, "eta_start"))
        self.assertFalse(api._host.undo_stack.canUndo())

        # Valid expression writes both numeric value and formula inside one undo step.
        editor._on_cs_prop_spinbox_changed("eta_start", "=ref_eta + 0.1")
        self.assertAlmostEqual(cs_geom["eta_start"], 0.6)
        self.assertEqual(get_expression(cs_geom, "eta_start"), "=ref_eta + 0.1")
        self.assertTrue(api._host.undo_stack.canUndo())

        api.undo()
        self.assertAlmostEqual(cs_geom["eta_start"], 0.5)
        self.assertIsNone(get_expression(cs_geom, "eta_start"))

    def test_control_surface_add_delete_no_duplication(self) -> None:
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from plugins.geometry.engine.lifting_surface_geometry import (
            build_lifting_surface_geometry,
        )
        from plugins.geometry.engine.scene import build_project_geometry
        from setuav_studio.api import StudioAPI
        from setuav_studio.project import ProjectDocument

        doc_data = {
            "components": [
                {
                    "kind": "component",
                    "id": "fuselage",
                    "type": "org.setuav.core:fuselage",
                },
                {
                    "kind": "component",
                    "id": "wing",
                    "type": "org.setuav.core:lifting-surface",
                    "attach_to": "fuselage",
                    "parameters": {
                        "geometry": {
                            "mirror": True,
                            "profiles": [
                                {
                                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "chord": 200.0,
                                    "airfoil": "2412",
                                },
                                {
                                    "position": {"x": 50.0, "y": 500.0, "z": 0.0},
                                    "chord": 100.0,
                                    "airfoil": "2412",
                                },
                            ],
                        }
                    },
                },
                {
                    "kind": "component",
                    "id": "aileron-1",
                    "name": "Aileron 1",
                    "type": "org.setuav.core:control-surface",
                    "attach_to": "wing",
                    "parameters": {
                        "geometry": {
                            "type": "aileron",
                            "span_start": 200.0,
                            "span_end": 450.0,
                            "chord": 40.0,
                            "hinge_sweep": 0.0,
                            "deflection": 0.0,
                        }
                    },
                },
            ]
        }

        doc = ProjectDocument(Path("/fake/path"), "json", doc_data)
        api = StudioAPI()
        api._host.set_project(doc)

        wing_comp = doc.data["components"][1]
        editor = LiftingSurfaceEditor(api, wing_comp)

        self.assertEqual(editor.control_surfaces_table.rowCount(), 1)
        self.assertEqual(len(doc.data["components"]), 3)

        # 1. Add 1st new control surface
        editor.add_cs_button.click()
        self.assertEqual(editor.control_surfaces_table.rowCount(), 2)
        self.assertEqual(len(doc.data["components"]), 4)

        # 2. Add 2nd new control surface
        editor.add_cs_button.click()
        self.assertEqual(editor.control_surfaces_table.rowCount(), 3)
        self.assertEqual(len(doc.data["components"]), 5)

        # 3. Verify scene generation produces exact lofts without duplicating in memory
        providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }
        for _ in range(5):
            scene_geom = build_project_geometry(doc, providers)
            wing_lofts = [loft for loft in scene_geom.lofts if "wing" in loft.component_id]
            self.assertEqual(len(wing_lofts), 12)

        # 4. Verify components in project remained exactly 5 (no exponential growth)
        self.assertEqual(len(doc.data["components"]), 5)
        self.assertEqual(editor.control_surfaces_table.rowCount(), 3)

        # 5. Delete one control surface; plugins remove the data that refers to it
        removed: list[frozenset[str]] = []
        api.register_component_removal_handler(
            "org.test.removal", lambda _data, ids: removed.append(ids)
        )
        deleted_id = doc.data["components"][4]["id"]
        editor._control_surface_index = 2
        editor.delete_cs_button.click()
        self.assertEqual(editor.control_surfaces_table.rowCount(), 2)
        self.assertEqual(len(doc.data["components"]), 4)
        self.assertEqual(removed, [frozenset({deleted_id})])


if __name__ == "__main__":
    unittest.main()
