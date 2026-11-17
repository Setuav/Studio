"""Unit and integration tests for lifting surface planform, sections, tips, and editor."""

from __future__ import annotations

import math
import unittest
from copy import deepcopy
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QComboBox

from plugins.geometry.engine.data import GeometryData, LoftGeometry, Section
from plugins.geometry.engine.fuselage_geometry import build_fuselage_geometry
from plugins.geometry.engine.lifting_surface_geometry import (
    build_lifting_surface_geometry,
)
from plugins.geometry.engine.lifting_surface_tips import (
    TIP_CAP_DEFAULTS,
    WINGLET_DEFAULTS,
    WingletParameters,
    build_winglet_loft,
    winglet_parameters,
    winglet_sweep_angles,
)
from plugins.geometry.engine.scene import build_project_geometry
from setuav_studio.project import ProjectDocument, open_project
from setuav_studio.ui.viewport.mesh import build_loft_solid_vertices
from setuav_studio.ui.widget.table import ExpressionPropertyCell
from tests._common import TEST_PROJECT_PATH, cell_widget, get_qapp, table_item


class LiftingSurfaceGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_naca_wing_profiles_build_matching_loops(self) -> None:
        component = {
            "id": "wing-left",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {"position": {"x": 0, "y": 0}, "chord": 250, "airfoil": "4412"},
                        {
                            "position": {"x": 40, "y": -700},
                            "chord": 130,
                            "airfoil": "0012",
                        },
                    ]
                }
            },
        }
        lofts = build_lifting_surface_geometry(component)
        self.assertEqual(len(lofts), 1)
        self.assertEqual(len(lofts[0].sections[0].points), 64)
        self.assertEqual(len(lofts[0].sections[0].points), len(lofts[0].sections[1].points))

    def test_mirror_instance_reflects_source_geometry(self) -> None:
        project = ProjectDocument(
            Path("project.json"),
            "json",
            {
                "components": [
                    {
                        "kind": "component",
                        "id": "wing-left",
                        "type": "example:wing",
                        "transform": {"position": {"x": 10}},
                    },
                    {
                        "kind": "instance",
                        "id": "wing-right",
                        "source": "wing-left",
                        "derivation": {"type": "mirror", "plane": "XZ"},
                    },
                ]
            },
        )

        def provider(_component, _controls):
            return (
                LoftGeometry(
                    "wing-left",
                    (
                        Section(((0, -1, 0), (0, -2, 0), (0, -1, 1))),
                        Section(((1, -1, 0), (1, -2, 0), (1, -1, 1))),
                    ),
                    station_spacing=0.0,
                ),
            )

        data = build_project_geometry(project, {"example:wing": provider})
        left = next(loft for loft in data.lofts if loft.component_id == "wing-left")
        right = next(loft for loft in data.lofts if loft.component_id == "wing-right")
        self.assertEqual(left.sections[0].points[0], (10.0, -1.0, 0.0))
        self.assertEqual(right.sections[0].points[0], (10.0, 1.0, 0.0))

    def test_lifting_surface_editor_population_and_metrics(self) -> None:
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.api import StudioAPI

        get_qapp()
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)

        wing_comp = next(c for c in doc.data["components"] if c.get("id") == "main-wing")
        editor = LiftingSurfaceEditor(api, wing_comp)

        self.assertEqual(editor.planform_table.rowCount(), 8)
        self.assertIn("span", editor.planform_table.get_current_values())

        # Test Wing Planform Sizing driver resize
        editor._on_planform_spinbox_changed("span", 1200.0)
        # Profiles should scale such that total tip-to-tip wingspan = 2 * (y_offset + y_tip) = 1200.0 mm
        # With attachment y_offset = 75.0 mm, local tip position is at 525.0 mm
        self.assertAlmostEqual(
            float(wing_comp["parameters"]["geometry"]["profiles"][-1]["position"]["y"]),
            525.0,
            places=1,
        )

        # Test Angles table
        self.assertEqual(editor.angles_table.rowCount(), 6)
        editor._on_angle_changed("dihedral", 3.0)
        self.assertGreater(
            float(wing_comp["parameters"]["geometry"]["profiles"][-1]["position"]["z"]), 0.0
        )
        editor._on_angle_changed("sweep_curvature", 25.0)
        self.assertEqual(wing_comp["parameters"]["geometry"].get("sweep_curvature"), 25.0)

        # Check sections table, section planform sizing, angles, and airfoils
        self.assertGreaterEqual(editor.sections_table.rowCount(), 1)
        editor._load_section(0)
        self.assertEqual(editor.section_planform_table.rowCount(), 8)
        self.assertEqual(editor.section_properties_table.rowCount(), 6)
        self.assertTrue(editor.insert_section_button.isEnabled())
        self.assertTrue(editor.split_section_button.isEnabled())

        # Test Wing Sections table direct cell editing
        table_item(editor.sections_table, 0, 1).setText("600.0")
        editor._update_sections_table_cell(0, 1)
        self.assertAlmostEqual(editor._get_sections()[0]["span"], 600.0)

        # Test Section Driver: when 3 drivers are active, checking a 4th is blocked
        init_drivers = list(editor.section_planform_table.get_active_drivers())
        self.assertEqual(len(init_drivers), 3)
        editor.section_planform_table._on_driver_toggled("area", True)
        self.assertEqual(editor.section_planform_table.get_active_drivers(), init_drivers)

        # Unchecking one frees up a slot
        editor.section_planform_table._on_driver_toggled("tip_chord", False)
        self.assertEqual(len(editor.section_planform_table.get_active_drivers()), 2)
        # Now checking area succeeds
        editor.section_planform_table._on_driver_toggled("area", True)
        self.assertIn("area", editor.section_planform_table.get_active_drivers())
        self.assertEqual(len(editor.section_planform_table.get_active_drivers()), 3)

        # Add control surface
        init_cs = editor.control_surfaces_table.rowCount()
        editor.add_cs_button.click()
        self.assertEqual(editor.control_surfaces_table.rowCount(), init_cs + 1)
        # Edit control surface via cs_properties_table
        cs_idx = editor._control_surface_index

        def _get_cs_spin(k: str):
            for r in range(editor.cs_properties_table.rowCount()):
                if editor._property_key(editor.cs_properties_table, r) == k:
                    return editor.cs_properties_table.cellWidget(r, 1)
            return None

        spin_defl = _get_cs_spin("deflection")
        if isinstance(spin_defl, ExpressionPropertyCell):
            spin_defl.setValue(18.5)
        else:
            editor._on_cs_prop_spinbox_changed("deflection", 18.5)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["deflection"], 18.5)

        spin_chord = _get_cs_spin("chord")
        if isinstance(spin_chord, ExpressionPropertyCell):
            spin_chord.setValue(55.0)
        else:
            editor._on_cs_prop_spinbox_changed("chord", 55.0)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["chord"], 55.0)

        spin_sweep = _get_cs_spin("hinge_sweep")
        if isinstance(spin_sweep, ExpressionPropertyCell):
            spin_sweep.setValue(5.0)
        else:
            editor._on_cs_prop_spinbox_changed("hinge_sweep", 5.0)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["hinge_sweep"], 5.0)

        # Edit name inline via control_surfaces_table
        table_item(editor.control_surfaces_table, cs_idx, 0).setText("aileron_custom")
        self.assertEqual(editor._control_surfaces()[cs_idx]["name"], "aileron_custom")
        self.assertEqual(table_item(editor.cs_properties_table, 0, 1).text(), "aileron_custom")

        # Section Selection in 3D Viewport
        editor._on_section_selected(0, 0)
        self.assertEqual(api.current_section_selection, ("main-wing", 0, 0))

        # Check Symmetry / Mirror in general_table
        mirror_combo = cell_widget(editor.general_table, 2, 1, QComboBox)
        self.assertIsNotNone(mirror_combo)
        self.assertEqual(mirror_combo.currentData(), "true")
        self.assertEqual(mirror_combo.currentText(), "Bilateral (Mirror XZ)")
        editor._update_mirror(False)
        self.assertNotIn("mirror", wing_comp["parameters"]["geometry"])
        self.assertFalse(editor._is_symmetric())
        editor._update_mirror(True)
        self.assertTrue(wing_comp["parameters"]["geometry"]["mirror"])
        self.assertTrue(editor._is_symmetric())

        # Edit tip_chord in section_planform_table
        sec_values = editor.section_planform_table.get_current_values()
        sec_values["tip_chord"] = 180.0
        editor._on_section_planform_changed(sec_values)
        self.assertEqual(wing_comp["parameters"]["geometry"]["profiles"][1]["chord"], 180.0)

        # Edit dihedral in section_angles_table
        editor._on_section_angle_changed("dihedral", 5.0)
        self.assertIn("5.0", table_item(editor.sections_table, 0, 3).text())

        # Split section
        init_secs = editor.sections_table.rowCount()
        editor._load_section(0)
        editor._split_section()
        self.assertEqual(editor.sections_table.rowCount(), init_secs + 1)

        # Delete section
        editor._delete_section()
        self.assertEqual(editor.sections_table.rowCount(), init_secs)

    def test_wing_planform_engine_modes(self) -> None:
        from plugins.geometry.engine.lifting_surface_planform_engine import (
            calc_tan_sweep_at,
            compute_planform_metrics,
            solve_planform,
        )

        profiles = [
            {"position": {"x": 0, "y": 0, "z": 0}, "chord": 240.0},
            {"position": {"x": 20, "y": 240, "z": 0}, "chord": 180.0},
            {"position": {"x": 50, "y": 540, "z": 0}, "chord": 120.0},
        ]

        # Mode: area_ar_taper with sweep
        new_p, m = solve_planform(
            "area_ar_taper",
            {"area": 200000.0, "aspect_ratio": 8.0, "taper_ratio": 0.5, "sweep": 10.0},
            profiles,
            sweep_loc=0.25,
        )
        self.assertAlmostEqual(m["span"], math.sqrt(200000.0 * 8.0), places=1)
        self.assertAlmostEqual(new_p[-1]["position"]["y"], m["span"] / 2.0, places=1)
        self.assertEqual(m["sweep"], 10.0)

        # Mode: span_root_tip with multi-station morphing (preserves intermediate relative chord)
        new_p2, m2 = solve_planform(
            "span_root_tip",
            {"span": 1400.0, "root_chord": 300.0, "tip_chord": 150.0, "sweep": 0.0},
            profiles,
            sweep_loc=0.25,
        )
        self.assertEqual(m2["span"], 1400.0)
        self.assertAlmostEqual(new_p2[-1]["position"]["y"], 700.0, places=1)
        self.assertAlmostEqual(new_p2[0]["chord"], 300.0, places=1)
        self.assertAlmostEqual(new_p2[-1]["chord"], 150.0, places=1)
        # Intermediate station preserves relative chord ratio (0.5 -> 225.0 mm)
        self.assertAlmostEqual(new_p2[1]["chord"], 225.0, places=1)
        self.assertAlmostEqual(m2["area"], 309166.67, places=0)
        # Tip X offset with 0 deg sweep at c/4 = -0.25 * (150 - 300) = 37.5
        self.assertAlmostEqual(new_p2[-1]["position"]["x"], 37.5, places=1)

        # Pure 2-station trapezoid solving
        profiles_2s = [
            {"position": {"x": 0, "y": 0, "z": 0}, "chord": 300.0},
            {"position": {"x": 0, "y": 500, "z": 0}, "chord": 150.0},
        ]
        _new_p_2s, m_2s = solve_planform(
            "span_root_tip",
            {"span": 1400.0, "root_chord": 300.0, "tip_chord": 150.0, "sweep": 0.0},
            profiles_2s,
            sweep_loc=0.25,
        )
        self.assertEqual(m_2s["span"], 1400.0)
        self.assertEqual(m_2s["area"], 1400.0 * (300.0 + 150.0) / 2.0)

        # Mode with y_offset = 100.0 mm and symmetric = True
        new_p3, m3 = solve_planform(
            "span_root_tip",
            {"span": 1400.0, "root_chord": 300.0, "tip_chord": 150.0, "sweep": 0.0},
            profiles,
            sweep_loc=0.25,
            symmetric=True,
            y_offset=100.0,
        )
        # Total span tip-to-tip is 1400.0 mm, local tip position is 700 - 100 = 600.0 mm
        self.assertEqual(m3["span"], 1400.0)
        self.assertAlmostEqual(new_p3[-1]["position"]["y"], 600.0, places=1)

        # Mode with symmetric = False (single panel / vertical fin)
        m_asym = compute_planform_metrics(profiles, symmetric=False)
        self.assertAlmostEqual(m_asym["span"], 540.0, places=1)

        # OpenVSP analytic sweep conversion formula test
        # Sweep 30 deg at LE (0.0), AR=6.0, taper=0.5 -> QC (0.25) sweep is ~27.55 deg
        sw_qc = calc_tan_sweep_at(0.25, 30.0, 0.0, aspect_ratio=6.0, taper_ratio=0.5)
        self.assertAlmostEqual(sw_qc, 27.55, places=1)

    def test_wing_sections_engine_kinematics(self) -> None:
        from plugins.geometry.engine.lifting_surface_sections_engine import (
            delete_section,
            insert_section,
            profiles_to_sections,
            sections_to_profiles,
            split_section,
        )

        profiles = [
            {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "chord": 240.0,
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                "airfoil": "2412",
            },
            {
                "position": {"x": 50.0, "y": 500.0, "z": 20.0},
                "chord": 120.0,
                "rotation": {"x": 0.0, "y": -2.0, "z": 0.0},
                "airfoil": "0012",
            },
        ]

        # 1. Convert to section
        sections = profiles_to_sections(profiles, sweep_loc=0.25)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["span"], 500.0)
        self.assertEqual(sections[0]["root_chord"], 240.0)
        self.assertEqual(sections[0]["tip_chord"], 120.0)
        self.assertEqual(sections[0]["twist"], -2.0)

        # 2. Round-trip conversion back to profiles
        reconstructed = sections_to_profiles(sections, profiles[0], sweep_loc=0.25)
        self.assertEqual(len(reconstructed), 2)
        self.assertAlmostEqual(reconstructed[1]["position"]["x"], 50.0, places=2)
        self.assertAlmostEqual(reconstructed[1]["position"]["y"], 500.0, places=2)
        self.assertAlmostEqual(reconstructed[1]["position"]["z"], 20.0, places=2)
        self.assertAlmostEqual(reconstructed[1]["chord"], 120.0, places=2)
        self.assertAlmostEqual(reconstructed[1]["rotation"]["y"], -2.0, places=2)

        # 3. Split section
        split_profs = split_section(profiles, 0, sweep_loc=0.25)
        self.assertEqual(len(split_profs), 3)
        split_secs = profiles_to_sections(split_profs, sweep_loc=0.25)
        self.assertEqual(len(split_secs), 2)
        # Midpoint chord is 180.0
        self.assertAlmostEqual(split_secs[0]["tip_chord"], 180.0, places=1)
        # Section 2 root chord automatically matches Section 1 tip chord
        self.assertAlmostEqual(split_secs[1]["root_chord"], 180.0, places=1)

        # 4. Insert section
        inserted_profs = insert_section(profiles, sweep_loc=0.25)
        self.assertEqual(len(inserted_profs), 3)

        # 5. Delete section
        del_profs = delete_section(split_profs, 1, sweep_loc=0.25)
        self.assertEqual(len(del_profs), 2)

    def test_wing_sections_engine_airfoils(self) -> None:
        from plugins.geometry.engine.lifting_surface_sections_engine import (
            insert_section,
            profiles_to_sections,
            split_section,
        )

        profiles = [
            {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 240.0, "airfoil": "2412"},
            {"position": {"x": 0.0, "y": 500.0, "z": 0.0}, "chord": 120.0, "airfoil": "0012"},
        ]

        # A split station takes the root airfoil of the section it divides
        split_profs = split_section(profiles, 0, sweep_loc=0.25)
        self.assertEqual([p["airfoil"] for p in split_profs], ["2412", "2412", "0012"])

        # A section added at the tip copies the tip airfoil
        inserted = insert_section(profiles, sweep_loc=0.25)
        self.assertEqual([p["airfoil"] for p in inserted], ["2412", "0012", "0012"])

        with self.assertRaises(ValueError):
            insert_section(profiles[:1], sweep_loc=0.25)

        without_airfoil = deepcopy(profiles)
        del without_airfoil[1]["airfoil"]
        with self.assertRaises(KeyError):
            profiles_to_sections(without_airfoil)

    def test_fuselage_wing_root_stub_geometry(self) -> None:
        from plugins.geometry.engine.fuselage_geometry import build_fuselage_geometry
        from plugins.geometry.engine.lifting_surface_geometry import (
            build_lifting_surface_geometry,
        )
        from plugins.geometry.engine.scene import build_project_geometry

        mock_project = {
            "components": [
                {
                    "kind": "component",
                    "type": "org.setuav.core:fuselage",
                    "id": "fuse",
                    "parameters": {
                        "geometry": {
                            "segments": [
                                {
                                    "sections": [
                                        {
                                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                            "profile": {"type": "circle", "diameter": 100.0},
                                        },
                                        {
                                            "position": {"x": 500.0, "y": 0.0, "z": 0.0},
                                            "profile": {"type": "circle", "diameter": 100.0},
                                        },
                                    ]
                                }
                            ]
                        }
                    },
                },
                {
                    "kind": "component",
                    "type": "org.setuav.core:lifting-surface",
                    "id": "wing",
                    "attach_to": "fuse",
                    "transform": {
                        "position": {"x": 200.0, "y": 0.0, "z": 0.0},
                    },
                    "parameters": {
                        "geometry": {
                            "profiles": [
                                {
                                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "chord": 150.0,
                                    "airfoil": "0012",
                                },
                                {
                                    "position": {"x": 0.0, "y": 300.0, "z": 0.0},
                                    "chord": 100.0,
                                    "airfoil": "0012",
                                },
                            ]
                        }
                    },
                },
            ]
        }

        providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }

        scene_geom = build_project_geometry(
            ProjectDocument(Path("mock.json"), "json", mock_project), providers
        )
        wing_lofts = [loft for loft in scene_geom.lofts if loft.component_id == "wing"]
        self.assertEqual(len(wing_lofts), 1)
        wing_loft = wing_lofts[0]
        self.assertEqual(len(wing_loft.sections), 2)

        from setuav_studio.ui.viewport.mesh import (
            WIRE_FEATURE,
            WIRE_FULL,
            build_loft_wire_vertices,
        )

        solid_verts = build_loft_solid_vertices(scene_geom)
        wire_feature_verts = build_loft_wire_vertices(scene_geom, wire_mode=WIRE_FEATURE)
        wire_full_verts = build_loft_wire_vertices(scene_geom, wire_mode=WIRE_FULL)
        self.assertGreater(len(solid_verts), 0)
        self.assertGreater(len(wire_feature_verts), 0)
        self.assertGreater(len(wire_full_verts), len(wire_feature_verts))

        # Test tip cap and fuselage feature wireframe lines
        fuse_comp = {
            "kind": "component",
            "id": "fuselage",
            "parameters": {
                "geometry": {
                    "segments": [
                        {
                            "sections": [
                                {
                                    "position": {"x": 0},
                                    "profile": {"type": "circle", "diameter": 100},
                                },
                                {
                                    "position": {"x": 200},
                                    "profile": {"type": "circle", "diameter": 200},
                                },
                                {
                                    "position": {"x": 500},
                                    "profile": {"type": "circle", "diameter": 200},
                                },
                                {
                                    "position": {"x": 800},
                                    "profile": {"type": "circle", "diameter": 50},
                                },
                            ]
                        }
                    ]
                }
            },
        }
        fuse_lofts = build_fuselage_geometry(fuse_comp)
        fuse_geom = GeometryData(fuse_lofts)
        fuse_wire_feature = build_loft_wire_vertices(fuse_geom, wire_mode=WIRE_FEATURE)
        self.assertGreater(len(fuse_wire_feature), 0)

        for tip_t in ("round", "sharp"):
            wing_with_cap = {
                "kind": "component",
                "id": "wing",
                "parameters": {
                    "geometry": {
                        "profiles": [
                            {
                                "chord": 200.0,
                                "position": {"x": 0, "y": 0, "z": 0},
                                "airfoil": "0012",
                            },
                            {
                                "chord": 100.0,
                                "position": {"x": 50, "y": 500, "z": 0},
                                "airfoil": "0012",
                            },
                        ],
                        "tip_treatment": {
                            "type": tip_t,
                            "length": 30.0,
                            "offset_x": 0.0,
                        },
                    }
                },
            }
            cap_lofts = build_lifting_surface_geometry(wing_with_cap)
            cap_geom = GeometryData(cap_lofts)
            cap_wire_feature = build_loft_wire_vertices(cap_geom, wire_mode=WIRE_FEATURE)
            self.assertGreater(len(cap_wire_feature), 0)

        # Test control surface vs wing selection matching
        from setuav_studio.ui.viewport.mesh import _is_matching_component

        # When aileron-1 is selected, only aileron-1 matches
        self.assertTrue(_is_matching_component("main-wing:aileron-1", "aileron-1"))
        self.assertTrue(_is_matching_component("main-wing:mirror:aileron-1", "aileron-1"))
        self.assertFalse(_is_matching_component("main-wing:flap-1", "aileron-1"))
        self.assertFalse(_is_matching_component("main-wing", "aileron-1"))
        self.assertFalse(_is_matching_component("main-wing:tip-cap", "aileron-1"))

        # When main wing is selected, main wing and all its child control surfaces match
        self.assertTrue(_is_matching_component("main-wing", "main-wing"))
        self.assertTrue(_is_matching_component("main-wing:mirror", "main-wing"))
        self.assertTrue(_is_matching_component("main-wing:tip-cap", "main-wing"))
        self.assertTrue(_is_matching_component("main-wing:aileron-1", "main-wing"))
        self.assertTrue(_is_matching_component("main-wing:mirror:aileron-1", "main-wing"))
        self.assertTrue(_is_matching_component("main-wing:flap-1", "main-wing"))
        self.assertFalse(_is_matching_component("h-stab", "main-wing"))
        self.assertFalse(_is_matching_component("fuselage", "main-wing"))

    def test_root_stub_reaches_only_fuselages_with_sections(self) -> None:
        from plugins.geometry.engine.fuselage_geometry import build_fuselage_geometry
        from plugins.geometry.engine.lifting_surface_geometry import (
            build_lifting_surface_geometry,
        )
        from plugins.geometry.engine.scene import build_project_geometry

        def project(fuselage_sections: list[dict[str, Any]]) -> ProjectDocument:
            fuselage = {
                "kind": "component",
                "type": "org.setuav.core:fuselage",
                "id": "fuse",
                "parameters": {"geometry": {"segments": [{"sections": fuselage_sections}]}},
            }
            wing = {
                "kind": "component",
                "type": "org.setuav.core:lifting-surface",
                "id": "wing",
                "attach_to": "fuse",
                # The wing root sits 100 mm out from the fuselage axis.
                "transform": {"position": {"x": 200.0, "y": 100.0, "z": 0.0}},
                "parameters": {
                    "geometry": {
                        "profiles": [
                            {
                                "position": {"x": 0, "y": 0, "z": 0},
                                "chord": 150.0,
                                "airfoil": "0012",
                            },
                            {
                                "position": {"x": 0, "y": 300, "z": 0},
                                "chord": 100.0,
                                "airfoil": "0012",
                            },
                        ]
                    }
                },
            }
            return ProjectDocument(Path("mock.json"), "json", {"components": [fuselage, wing]})

        providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }
        sections = [
            {"position": {"x": x, "y": 0, "z": 0}, "profile": {"type": "circle", "diameter": 100}}
            for x in (0.0, 500.0)
        ]
        with_body = build_project_geometry(project(sections), providers)
        without_body = build_project_geometry(project([]), providers)

        def stubs(geometry: Any) -> list[Any]:
            return [
                loft
                for loft in geometry.lofts
                if loft.component_id == "fuse" and not loft.closed_ends
            ]

        self.assertEqual(len(stubs(with_body)), 1)
        self.assertEqual(stubs(without_body), [])

    def test_conformal_wing_root_stubs_angled_and_flat(self) -> None:
        """Verify that lifting surface and empennage lofts and root stubs are properly generated in scene."""
        doc = open_project(TEST_PROJECT_PATH)
        providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }
        scene_geom = build_project_geometry(doc, providers)
        wing_lofts = [
            loft
            for loft in scene_geom.lofts
            if "wing" in loft.component_id or "v-tail" in loft.component_id
        ]
        self.assertGreaterEqual(len(wing_lofts), 2)
        fuse_stubs = [
            loft
            for loft in scene_geom.lofts
            if loft.component_id == "fuselage" and len(loft.sections) == 2
        ]
        self.assertGreaterEqual(len(fuse_stubs), 2)

    def test_twist_location_pivot_rotation(self) -> None:
        """Verify that section transform rotates exactly around the chosen twist_location chord fraction."""
        from plugins.geometry.engine.transforms import section_transform, transform_point

        pos = {"x": 100.0, "y": 200.0, "z": 50.0}
        chord = 200.0
        sec_0 = {"position": pos, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}}
        sec_w = {
            "position": pos,
            "rotation": {"x": 0.0, "y": -5.0, "z": 0.0},
        }  # -5 deg pitch (washout)

        # 1. Test Quarter-Chord pivot (0.25)
        mat0_qc = section_transform(sec_0, chord=chord, twist_location=0.25)
        matw_qc = section_transform(sec_w, chord=chord, twist_location=0.25)
        p0_qc = transform_point(mat0_qc, (50.0, 0.0, 0.0))  # 0.25 * 200 = 50 mm
        pw_qc = transform_point(matw_qc, (50.0, 0.0, 0.0))
        self.assertAlmostEqual(p0_qc[0], pw_qc[0], places=4)
        self.assertAlmostEqual(p0_qc[1], pw_qc[1], places=4)
        self.assertAlmostEqual(p0_qc[2], pw_qc[2], places=4)

        # 2. Test Leading-Edge pivot (0.0)
        mat0_le = section_transform(sec_0, chord=chord, twist_location=0.0)
        matw_le = section_transform(sec_w, chord=chord, twist_location=0.0)
        p0_le = transform_point(mat0_le, (0.0, 0.0, 0.0))
        pw_le = transform_point(matw_le, (0.0, 0.0, 0.0))
        self.assertAlmostEqual(p0_le[0], pw_le[0], places=4)
        self.assertAlmostEqual(p0_le[1], pw_le[1], places=4)
        self.assertAlmostEqual(p0_le[2], pw_le[2], places=4)

        # 3. Test Trailing-Edge pivot (1.0)
        mat0_te = section_transform(sec_0, chord=chord, twist_location=1.0)
        matw_te = section_transform(sec_w, chord=chord, twist_location=1.0)
        p0_te = transform_point(mat0_te, (200.0, 0.0, 0.0))
        pw_te = transform_point(matw_te, (200.0, 0.0, 0.0))
        self.assertAlmostEqual(p0_te[0], pw_te[0], places=4)
        self.assertAlmostEqual(p0_te[1], pw_te[1], places=4)
        self.assertAlmostEqual(p0_te[2], pw_te[2], places=4)

    def test_wing_planform_washout_and_twist_location(self) -> None:
        """Verify planform engine distributes washout linearly and computes metrics correctly."""
        from plugins.geometry.engine.lifting_surface_planform_engine import (
            compute_planform_metrics,
            solve_planform,
        )

        profiles = [
            {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "chord": 200.0,
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            {
                "position": {"x": 0.0, "y": 250.0, "z": 0.0},
                "chord": 150.0,
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            {
                "position": {"x": 0.0, "y": 500.0, "z": 0.0},
                "chord": 100.0,
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
        ]
        inputs = {
            "span": 1000.0,
            "root_chord": 200.0,
            "tip_chord": 100.0,
            "sweep": 5.0,
            "washout": -3.0,
        }
        new_profiles, metrics = solve_planform("span_root_tip", inputs, profiles)
        self.assertEqual(len(new_profiles), 3)
        self.assertAlmostEqual(metrics["washout"], -3.0, places=3)
        self.assertAlmostEqual(new_profiles[0]["rotation"]["y"], 0.0, places=3)
        self.assertAlmostEqual(new_profiles[1]["rotation"]["y"], -1.5, places=3)
        self.assertAlmostEqual(new_profiles[2]["rotation"]["y"], -3.0, places=3)

        computed = compute_planform_metrics(new_profiles)
        self.assertAlmostEqual(computed["washout"], -3.0, places=3)

    def test_wing_tip_caps_flat_round_sharp(self) -> None:
        """Verify that flat, round, and sharp wingtip caps generate correct 3D loft extensions."""
        wing_comp = {
            "id": "wing-test",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "airfoil": "0012",
                        },
                        {
                            "position": {"x": 0.0, "y": 500.0, "z": 0.0},
                            "chord": 100.0,
                            "airfoil": "0012",
                        },
                    ]
                }
            },
        }

        # 1. Default (flat) tip cap: exactly 1 loft with 2 sections
        lofts_flat = build_lifting_surface_geometry(wing_comp)
        self.assertEqual(len(lofts_flat), 1)
        self.assertEqual(len(lofts_flat[0].sections), 2)
        tip_flat_y = max(p[1] for p in lofts_flat[0].sections[-1].points)
        self.assertAlmostEqual(tip_flat_y, 500.0, places=2)

        # 2. Round tip cap with length 25 mm: returns main wing + dedicated bullnose tip cap loft
        wing_round = deepcopy(wing_comp)
        wing_round["parameters"]["geometry"]["tip_treatment"] = {
            "type": "round",
            "length": 25.0,
            "offset_x": 0.0,
        }
        lofts_round = build_lifting_surface_geometry(wing_round)
        self.assertEqual(len(lofts_round), 2)
        tip_cap_loft = lofts_round[1]
        self.assertEqual(tip_cap_loft.component_id, "wing-test:tip-cap")
        self.assertEqual(len(tip_cap_loft.sections), 17)
        all_y = [p[1] for sec in tip_cap_loft.sections for p in sec.points]
        self.assertAlmostEqual(min(all_y), 500.0, places=2)
        self.assertAlmostEqual(max(all_y), 525.0, places=2)

        # 3. Sharp tip cap with length 15 mm: returns main wing + dedicated sharp beveled tip cap loft
        wing_sharp = deepcopy(wing_comp)
        wing_sharp["parameters"]["geometry"]["tip_treatment"] = {
            "type": "sharp",
            "length": 15.0,
            "offset_x": 5.0,
        }
        lofts_sharp = build_lifting_surface_geometry(wing_sharp)
        self.assertEqual(len(lofts_sharp), 2)
        sharp_cap_loft = lofts_sharp[1]
        self.assertEqual(sharp_cap_loft.component_id, "wing-test:tip-cap")
        self.assertEqual(len(sharp_cap_loft.sections), 3)
        all_sharp_y = [p[1] for sec in sharp_cap_loft.sections for p in sec.points]
        self.assertAlmostEqual(min(all_sharp_y), 500.0, places=2)
        self.assertAlmostEqual(max(all_sharp_y), 515.0, places=2)

    def test_lifting_surface_editor_tip_caps_ui(self) -> None:
        """Verify LiftingSurfaceEditor tip caps table interactions and project mutation."""
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.api import StudioAPI

        api = StudioAPI()
        wing_comp = {
            "id": "main-wing",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "airfoil": "0012",
                        },
                        {
                            "position": {"x": 0.0, "y": 500.0, "z": 0.0},
                            "chord": 100.0,
                            "airfoil": "0012",
                        },
                    ]
                }
            },
        }
        doc = ProjectDocument(Path("/tmp/test_tip_caps.json"), "json", {"components": [wing_comp]})
        api._host.set_project(doc)

        editor = LiftingSurfaceEditor(api, wing_comp)
        # A wing without tip treatment has a flat tip — table has 1 row: tip_type
        self.assertEqual(editor.tip_caps_table.rowCount(), 1)
        self.assertNotIn("tip_treatment", wing_comp["parameters"]["geometry"])

        # Change tip cap type to round via UI (expands to 3 rows, writes every cap parameter)
        editor._on_tip_cap_type_changed("round")
        self.assertEqual(editor.tip_caps_table.rowCount(), 3)
        self.assertEqual(
            wing_comp["parameters"]["geometry"]["tip_treatment"],
            {"type": "round", **asdict(TIP_CAP_DEFAULTS)},
        )

        # Edit tip length
        length_row = self._tip_caps_rows(editor)["length"]
        cell_widget(editor.tip_caps_table, length_row, 1, ExpressionPropertyCell).setValue(35.0)
        self.assertAlmostEqual(wing_comp["parameters"]["geometry"]["tip_treatment"]["length"], 35.0)

        # Round and sharp share their parameters, so switching keeps the edited length
        editor._on_tip_cap_type_changed("sharp")
        self.assertEqual(
            wing_comp["parameters"]["geometry"]["tip_treatment"],
            {"type": "sharp", "length": 35.0, "offset_x": 0.0},
        )

        # Switch to winglet and edit winglet parameters directly via UI
        editor._on_tip_cap_type_changed("winglet")
        self.assertEqual(
            wing_comp["parameters"]["geometry"]["tip_treatment"],
            {"type": "winglet", **asdict(WINGLET_DEFAULTS)},
        )
        editor._on_tip_cap_spinbox_changed("le_sweep_root", 25.0)
        editor._on_tip_cap_spinbox_changed("le_sweep_tip", 55.0)
        editor._on_tip_cap_spinbox_changed("le_curvature", 10.0)
        editor._on_tip_cap_spinbox_changed("te_sweep_tip", -15.0)
        editor._on_tip_cap_spinbox_changed("tip_thickness_scale", 0.6)
        tt = wing_comp["parameters"]["geometry"]["tip_treatment"]
        self.assertEqual(tt["type"], "winglet")
        self.assertEqual(tt["le_sweep_root"], 25.0)
        self.assertEqual(tt["le_sweep_tip"], 55.0)
        self.assertEqual(tt["le_curvature"], 10.0)
        self.assertEqual(tt["te_sweep_tip"], -15.0)
        self.assertEqual(tt["tip_thickness_scale"], 0.6)

        # Check two-column single-row projected metrics live update widgets
        self.assertTrue(hasattr(editor, "metric_height_val"))
        self.assertTrue(hasattr(editor, "metric_span_val"))
        assert editor.metric_height_val is not None
        assert editor.metric_span_val is not None
        self.assertIn("mm", editor.metric_height_val.text())
        self.assertIn("mm", editor.metric_span_val.text())
        m_row = -1
        for r in range(editor.tip_caps_table.rowCount()):
            if editor._property_key(editor.tip_caps_table, r) == "winglet_projected_metrics":
                m_row = r
                break
        self.assertGreaterEqual(m_row, 0)
        self.assertEqual(editor.tip_caps_table.columnSpan(m_row, 0), 1)
        self.assertIsNotNone(editor.tip_caps_table.cellWidget(m_row, 0))
        self.assertIsNotNone(editor.tip_caps_table.cellWidget(m_row, 1))

    @staticmethod
    def _tip_caps_rows(editor: Any) -> dict[str, int]:
        table = editor.tip_caps_table
        return {editor._property_key(table, row): row for row in range(table.rowCount())}

    @staticmethod
    def _winglet_wing(tip_treatment: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": "main-wing",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "airfoil": "0012",
                        },
                        {
                            "position": {"x": 60.0, "y": 500.0, "z": 0.0},
                            "chord": 120.0,
                            "airfoil": "0012",
                        },
                    ],
                    "tip_treatment": tip_treatment,
                }
            },
        }

    @staticmethod
    def _winglet_loft(
        tip_profile: dict[str, Any],
        winglet: WingletParameters,
        incoming_le_sweep_deg: float = 0.0,
        incoming_te_sweep_deg: float = 0.0,
    ) -> LoftGeometry | None:
        return build_winglet_loft(
            comp_id="wing",
            tip_profile=tip_profile,
            winglet=winglet,
            span_dir=1.0,
            incoming_le_sweep_deg=incoming_le_sweep_deg,
            incoming_te_sweep_deg=incoming_te_sweep_deg,
            twist_location=0.25,
            te_thickness=0.0,
            thickness_scale=1.0,
            camber_scale=1.0,
        )

    def test_winglet_geometry(self) -> None:
        """Verify build_winglet_loft generates correct curved/scimitar geometry."""
        tip_profile = {
            "chord": 100.0,
            "airfoil": "0012",
            "position": {"x": 0.0, "y": 500.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
        }

        # Winglet canting from the wing plane to vertical (cant tip 90°)
        loft = self._winglet_loft(
            tip_profile,
            replace(
                WINGLET_DEFAULTS,
                winglet_height=100.0,
                cant_root=0.0,
                cant_tip=90.0,
                blend_radius=45.0,
                le_sweep_tip=30.0,
                te_sweep_tip=15.0,
                toe_root=0.0,
                toe_tip=0.0,
                root_chord_scale=1.0,
                tip_chord_scale=0.5,
            ),
        )
        self.assertIsNotNone(loft)
        assert loft is not None
        self.assertEqual(loft.component_id, "wing:winglet")
        self.assertEqual(len(loft.sections), 24)
        # All sections should have the same number of points
        pts_per_section = len(loft.sections[0].points)
        self.assertGreater(pts_per_section, 0)
        for sec in loft.sections:
            self.assertEqual(len(sec.points), pts_per_section)

        # Root section (s=0) should be centered on tip profile Y position (y=500)
        root_ys = [p[1] for p in loft.sections[0].points]
        root_mean_y = sum(root_ys) / len(root_ys)
        self.assertAlmostEqual(root_mean_y, 500.0, delta=1.0)

        # Tip section (s=100) fully vertical cant=90° → Y barely changes, Z increases
        tip_zs = [p[2] for p in loft.sections[-1].points]
        root_zs = [p[2] for p in loft.sections[0].points]
        self.assertGreater(max(tip_zs), max(root_zs))

        # Zero winglet_height → None
        none_loft = self._winglet_loft(tip_profile, replace(WINGLET_DEFAULTS, winglet_height=0.0))
        self.assertIsNone(none_loft)

        # Curved scimitar winglet with independent LE/TE curves and thickness taper
        scimitar_loft = self._winglet_loft(
            tip_profile,
            replace(
                WINGLET_DEFAULTS,
                winglet_height=140.0,
                cant_root=0.0,
                cant_tip=85.0,
                blend_radius=50.0,
                match_wing_tangent=True,
                le_sweep_tip=55.0,
                le_curvature=10.0,
                te_sweep_tip=-15.0,
                te_curvature=-8.0,
                toe_root=0.0,
                toe_tip=-2.0,
                tip_thickness_scale=0.6,
            ),
            incoming_le_sweep_deg=10.0,
            incoming_te_sweep_deg=5.0,
        )
        self.assertIsNotNone(scimitar_loft)
        assert scimitar_loft is not None
        self.assertEqual(len(scimitar_loft.sections), 24)

        # Blended cant check: root section should emerge in span direction (near Y=500)
        # Mid/tip sections should reach higher Z smoothly
        mid_z = max(p[2] for p in scimitar_loft.sections[len(scimitar_loft.sections) // 2].points)
        tip_scimitar_z = max(p[2] for p in scimitar_loft.sections[-1].points)
        self.assertGreater(tip_scimitar_z, mid_z)
        self.assertGreater(mid_z, max(root_zs))

        # Thickness check at root section (in Z since cant_root=0 is horizontal)
        root_thickness_z = max(p[2] for p in scimitar_loft.sections[0].points) - min(
            p[2] for p in scimitar_loft.sections[0].points
        )
        self.assertGreater(root_thickness_z, 5.0)

    def test_winglet_editor_shows_the_values_the_preview_draws(self) -> None:
        """Every winglet value the editor displays is the one the preview builds from."""
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.api import StudioAPI

        winglet = WingletParameters(
            winglet_height=110.0,
            match_wing_tangent=False,
            cant_root=10.0,
            cant_tip=70.0,
            blend_radius=35.0,
            le_sweep_root=25.0,
            le_sweep_tip=50.0,
            le_curvature=4.0,
            te_sweep_root=12.0,
            te_sweep_tip=18.0,
            te_curvature=-3.0,
            toe_root=1.0,
            toe_tip=-2.5,
            root_chord_scale=0.9,
            tip_chord_scale=0.4,
            tip_thickness_scale=0.65,
        )
        wing_comp = self._winglet_wing({"type": "winglet", **asdict(winglet)})
        api = StudioAPI()
        doc = ProjectDocument(Path("/tmp/test_winglet.json"), "json", {"components": [wing_comp]})
        api._host.set_project(doc)
        editor = LiftingSurfaceEditor(api, wing_comp)
        table = editor.tip_caps_table

        rows = self._tip_caps_rows(editor)
        winglet_keys = {field.name for field in fields(WingletParameters)}
        self.assertEqual(
            set(rows) - {"tip_type", "winglet_projected_metrics"},
            winglet_keys,
        )
        displayed: dict[str, Any] = {
            key: cell_widget(table, row, 1, ExpressionPropertyCell).value()
            for key, row in rows.items()
            if key in winglet_keys - {"match_wing_tangent"}
        }
        displayed["match_wing_tangent"] = (
            cell_widget(table, rows["match_wing_tangent"], 1, QComboBox).currentData() == "true"
        )
        shown = WingletParameters(**displayed)
        self.assertEqual(shown, winglet_parameters(wing_comp["parameters"]["geometry"]))

        # The preview loft is exactly the winglet built from the displayed values
        preview = build_lifting_surface_geometry(wing_comp)[-1]
        tip_profile = wing_comp["parameters"]["geometry"]["profiles"][-1]
        from_editor = self._winglet_loft(tip_profile, shown)
        assert from_editor is not None
        self.assertEqual(preview.component_id, "main-wing:winglet")
        self.assertEqual(preview.sections, from_editor.sections)

    def test_switching_to_winglet_writes_every_parameter_in_one_undo_step(self) -> None:
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.api import StudioAPI

        wing_comp = self._winglet_wing({"type": "round", "length": 30.0, "offset_x": 2.0})
        api = StudioAPI()
        doc = ProjectDocument(Path("/tmp/test_winglet.json"), "json", {"components": [wing_comp]})
        api._host.set_project(doc)
        editor = LiftingSurfaceEditor(api, wing_comp)
        geometry = wing_comp["parameters"]["geometry"]

        editor._on_tip_cap_type_changed("winglet")
        tip_treatment = geometry["tip_treatment"]
        self.assertEqual(
            set(tip_treatment), {"type"} | {field.name for field in fields(WingletParameters)}
        )
        self.assertEqual(tip_treatment, {"type": "winglet", **asdict(WINGLET_DEFAULTS)})

        api.undo()
        self.assertEqual(
            geometry["tip_treatment"], {"type": "round", "length": 30.0, "offset_x": 2.0}
        )
        api.redo()
        self.assertEqual(geometry["tip_treatment"], {"type": "winglet", **asdict(WINGLET_DEFAULTS)})

    def test_winglet_match_wing_tangent(self) -> None:
        """Matched winglets continue the wing edges; unmatched ones use their root sweeps."""
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.api import StudioAPI

        winglet = replace(
            WINGLET_DEFAULTS,
            le_sweep_root=30.0,
            le_sweep_tip=50.0,
            te_sweep_root=-10.0,
            te_sweep_tip=20.0,
        )
        self.assertEqual(
            winglet_sweep_angles(replace(winglet, match_wing_tangent=True), 7.0, 3.0),
            (7.0, 50.0, 3.0, 20.0),
        )
        self.assertEqual(
            winglet_sweep_angles(replace(winglet, match_wing_tangent=False), 7.0, 3.0),
            (30.0, 50.0, -10.0, 20.0),
        )

        def winglet_sections(match: bool, le_root: float, te_root: float) -> Any:
            tip_treatment = {
                "type": "winglet",
                **asdict(winglet),
                "match_wing_tangent": match,
                "le_sweep_root": le_root,
                "te_sweep_root": te_root,
            }
            return build_lifting_surface_geometry(self._winglet_wing(tip_treatment))[-1].sections

        # Matched: the root sweeps are not used
        self.assertEqual(winglet_sections(True, 30.0, -10.0), winglet_sections(True, 0.0, 15.0))
        # Unmatched: the root sweeps shape the winglet
        self.assertNotEqual(
            winglet_sections(False, 30.0, -10.0), winglet_sections(False, 0.0, 15.0)
        )

        # The editor hides the root sweeps while the winglet matches the wing tangent
        wing_comp = self._winglet_wing({"type": "winglet", **asdict(winglet)})
        api = StudioAPI()
        doc = ProjectDocument(Path("/tmp/test_winglet.json"), "json", {"components": [wing_comp]})
        api._host.set_project(doc)
        editor = LiftingSurfaceEditor(api, wing_comp)
        self.assertNotIn("le_sweep_root", self._tip_caps_rows(editor))
        self.assertNotIn("te_sweep_root", self._tip_caps_rows(editor))

        editor._on_match_wing_tangent_changed("false")
        self.assertFalse(wing_comp["parameters"]["geometry"]["tip_treatment"]["match_wing_tangent"])
        rows = self._tip_caps_rows(editor)
        table = editor.tip_caps_table
        self.assertEqual(
            cell_widget(table, rows["le_sweep_root"], 1, ExpressionPropertyCell).value(), 30.0
        )
        self.assertEqual(
            cell_widget(table, rows["te_sweep_root"], 1, ExpressionPropertyCell).value(), -10.0
        )

    def test_tip_treatment_must_hold_exactly_its_parameters(self) -> None:
        winglet = {"type": "winglet", **asdict(WINGLET_DEFAULTS)}

        missing = {key: value for key, value in winglet.items() if key != "toe_tip"}
        with self.assertRaisesRegex(ValueError, "Winglet tip treatment is missing key 'toe_tip'"):
            build_lifting_surface_geometry(self._winglet_wing(missing))

        with self.assertRaisesRegex(
            ValueError, "Winglet tip treatment has unknown key 'cant_angle'"
        ):
            build_lifting_surface_geometry(self._winglet_wing({**winglet, "cant_angle": 50.0}))

        with self.assertRaisesRegex(ValueError, "'match_wing_tangent' must be true or false"):
            winglet_parameters({"tip_treatment": {**winglet, "match_wing_tangent": 1}})

        with self.assertRaisesRegex(ValueError, "Round tip treatment is missing key 'offset_x'"):
            build_lifting_surface_geometry(self._winglet_wing({"type": "round", "length": 20.0}))

        with self.assertRaisesRegex(ValueError, "Unknown tip treatment type 'bevel'"):
            build_lifting_surface_geometry(self._winglet_wing({"type": "bevel"}))


if __name__ == "__main__":
    unittest.main()
