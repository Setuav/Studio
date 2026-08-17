from copy import deepcopy
import math
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from setuav_studio.plugins.geometry.data import GeometryData, LoftGeometry, Section
from setuav_studio.plugins.geometry.scene import build_project_geometry
from setuav_studio.plugins.geometry.fuselage_geometry import (
    SECTION_SAMPLES,
    build_fuselage_geometry,
    sample_profile,
)
from setuav_studio.plugins.geometry.lifting_surface_geometry import (
    build_lifting_surface_geometry,
    sample_airfoil,
)
from setuav_studio.plugins.geometry.mesh import build_loft_solid_vertices
from setuav_studio.project import ProjectDocument, open_project

TEST_PROJECT_PATH = "/home/huseyin/dev/setware/setuav-specification/examples/fixed-wing"


class GeometryTests(unittest.TestCase):
    def test_all_fuselage_profiles_use_matching_samples(self) -> None:
        profiles = (
            {"type": "circle", "diameter": 100},
            {"type": "ellipse", "width": 120, "height": 80},
            {"type": "rectangle", "width": 120, "height": 80, "corner_radius": 10},
            {"type": "trapezoid", "top_width": 80, "bottom_width": 120, "height": 90, "corner_radius": 5},
            {"type": "triangle", "base_width": 100, "height": 90, "orientation": "down", "corner_radius": 4},
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
                                {"position": {"x": 0}, "profile": {"type": "circle", "diameter": 0}},
                                {"position": {"x": 500}, "profile": {"type": "ellipse", "width": 200, "height": 150}},
                                {"position": {"x": 1000}, "profile": {"type": "circle", "diameter": 0}},
                            ],
                        }
                    ]
                }
            },
        }
        lofts = build_fuselage_geometry(component)
        self.assertEqual(len(lofts), 1)
        self.assertEqual(len(lofts[0].sections), 3)

    def test_palettes_are_complete_and_switchable(self) -> None:
        from setuav_studio.plugins.geometry.palettes import (
            DEFAULT_PALETTE,
            active_palette,
            palette_names,
            segment_colors,
            set_active_palette,
            wing_color,
        )

        self.assertGreaterEqual(len(palette_names()), 5)
        for name in palette_names():
            with self.subTest(palette=name):
                set_active_palette(name)
                self.assertEqual(active_palette(), name)
                self.assertEqual(len(segment_colors()), 5)
                self.assertEqual(len(wing_color()), 3)
                for color in (*segment_colors(), wing_color()):
                    self.assertTrue(all(0.0 <= channel <= 1.0 for channel in color))
        set_active_palette(DEFAULT_PALETTE)
        with self.assertRaises(ValueError):
            set_active_palette("nonexistent")

    def test_naca_wing_profiles_build_matching_loops(self) -> None:
        component = {
            "id": "wing-left",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {"position": {"x": 0, "y": 0}, "chord": 250, "airfoil": "naca4412"},
                        {"position": {"x": 40, "y": -700}, "chord": 130, "airfoil": {"type": "naca", "code": "0012"}},
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

        def provider(_component):
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

    def test_solid_mesh_contains_triangle_vertices(self) -> None:
        data = GeometryData(
            (
                LoftGeometry(
                    "body",
                    (
                        Section(((0, 0, 0), (0, 1, 0), (0, 0, 1))),
                        Section(((1, 0, 0), (1, 1, 0), (1, 0, 1))),
                    ),
                    station_spacing=0.0,
                ),
            )
        )
        vertices = build_loft_solid_vertices(data)
        self.assertGreater(len(vertices), 0)
        self.assertEqual(len(vertices) % 9, 0)
        self.assertEqual((len(vertices) // 9) % 3, 0)

    def test_lifting_surface_editor_population_and_metrics(self) -> None:
        from PySide6.QtWidgets import QApplication
        from setuav_studio.plugin_system import StudioAPI
        from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.project import open_project

        app = QApplication.instance() or QApplication([])
        api = StudioAPI()
        doc = open_project("/home/huseyin/dev/setware/setuav-specification/examples/fixed-wing")
        api.set_project(doc)

        wing_comp = next(c for c in doc.data["components"] if c.get("id") == "main-wing")
        editor = LiftingSurfaceEditor(api, wing_comp)

        self.assertIn("mm", editor._property_text(editor.planform_table, 1))
        self.assertGreater(float(editor._property_text(editor.planform_table, 2).replace("mm²", "").strip()), 1.0)

        # Check Parent combo selection
        parent_combo = editor.general_table.cellWidget(2, 1)
        self.assertIsNotNone(parent_combo)
        self.assertEqual(parent_combo.currentData(), "fuselage")
        self.assertGreaterEqual(parent_combo.count(), 2)

        # Test Driver Groups mode switch and parametric resizing
        editor.driver_mode_combo.setCurrentIndex(1)  # Span, Root & Tip
        self.assertEqual(editor._driver_mode, "span_root_tip")
        editor.planform_table.item(1, 1).setText("1200.0")  # Change span to 1200
        # Profiles should scale to 600.0 mm semi-span
        self.assertAlmostEqual(
            float(wing_comp["parameters"]["geometry"]["profiles"][-1]["position"]["y"]),
            600.0,
            places=1,
        )

        # Check locking behavior in driver mode
        # Column 2 (Span Y) should NOT have ItemIsEditable in driver mode
        self.assertFalse(bool(editor.profiles_table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable))
        self.assertFalse(bool(editor.profiles_table.item(0, 3).flags() & Qt.ItemFlag.ItemIsEditable))

        # Switch to manual mode: all columns become editable
        editor.driver_mode_combo.setCurrentIndex(4)  # Manual
        self.assertEqual(editor._driver_mode, "manual")
        self.assertTrue(bool(editor.profiles_table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable))
        self.assertTrue(bool(editor.profiles_table.item(0, 3).flags() & Qt.ItemFlag.ItemIsEditable))

        # Add control surface
        init_cs = editor.control_surfaces_table.rowCount()
        editor.add_cs_button.click()
        self.assertEqual(editor.control_surfaces_table.rowCount(), init_cs + 1)
        self.assertIn("control_", editor._property_text(editor.cs_properties_table, 0))

        # Edit control surface via cs_properties_table
        cs_idx = editor._control_surface_index
        editor.cs_properties_table.item(6, 1).setText("18.5")  # Deflection
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["deflection"], 18.5)

        editor.cs_properties_table.item(4, 1).setText("55.0")  # Chord
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["chord"], 55.0)

        editor.cs_properties_table.item(5, 1).setText("5.0")  # Hinge Sweep
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["hinge_sweep"], 5.0)

        # Edit tag inline via control_surfaces_table
        editor.control_surfaces_table.item(cs_idx, 0).setText("aileron_custom")
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["tag"], "aileron_custom")
        self.assertEqual(editor.cs_properties_table.item(0, 1).text(), "aileron_custom")

        # Section Selection in 3D Viewport
        editor.profiles_table.selectRow(1)
        self.assertEqual(api.current_section_selection, ("main-wing", 0, 1))

        # Check Attachment (Component Transform)
        self.assertEqual(editor.attachment_table.item(0, 0).text(), "305.00")
        self.assertEqual(editor.attachment_table.item(0, 1).text(), "75.00")
        self.assertEqual(editor.attachment_table.item(0, 2).text(), "40.00")

        # Edit Attachment Transform
        editor.attachment_table.item(0, 0).setText("320.00")
        self.assertEqual(wing_comp["transform"]["position"]["x"], 320.0)

        # Edit station local transform in station_transform_table
        editor.station_transform_table.item(0, 2).setText("25.00")
        self.assertEqual(wing_comp["parameters"]["geometry"]["profiles"][1]["position"]["z"], 25.0)

        # Edit property in profile_properties_table
        editor.profile_properties_table.item(1, 1).setText("180.0")
        self.assertEqual(wing_comp["parameters"]["geometry"]["profiles"][1]["chord"], 180.0)
        self.assertEqual(editor.profiles_table.item(1, 3).text(), "180.0")

        # Duplicate profile
        init_profs = editor.profiles_table.rowCount()
        editor._load_profile(0)
        editor._duplicate_profile()
        self.assertEqual(editor.profiles_table.rowCount(), init_profs + 1)

        # Delete profile
        editor._delete_profile()
        self.assertEqual(editor.profiles_table.rowCount(), init_profs)

    def test_wing_planform_engine_modes(self) -> None:
        from setuav_studio.plugins.geometry.wing_planform_engine import solve_wing_planform

        profiles = [
            {"position": {"x": 0, "y": 0, "z": 0}, "chord": 240.0},
            {"position": {"x": 20, "y": 240, "z": 0}, "chord": 180.0},
            {"position": {"x": 50, "y": 540, "z": 0}, "chord": 120.0},
        ]

        # Mode: area_ar_taper with sweep
        new_p, m = solve_wing_planform(
            "area_ar_taper",
            {"area": 200000.0, "aspect_ratio": 8.0, "taper_ratio": 0.5, "sweep": 10.0},
            profiles,
            sweep_loc=0.25,
        )
        self.assertAlmostEqual(m["span"], math.sqrt(200000.0 * 8.0), places=1)
        self.assertAlmostEqual(new_p[-1]["position"]["y"], m["span"] / 2.0, places=1)
        self.assertEqual(m["sweep"], 10.0)

        # Mode: span_root_tip with 0 sweep at c/4
        new_p2, m2 = solve_wing_planform(
            "span_root_tip",
            {"span": 1400.0, "root_chord": 300.0, "tip_chord": 150.0, "sweep": 0.0},
            profiles,
            sweep_loc=0.25,
        )
        self.assertEqual(m2["span"], 1400.0)
        self.assertEqual(m2["area"], 1400.0 * (300.0 + 150.0) / 2.0)
        self.assertAlmostEqual(new_p2[-1]["position"]["y"], 700.0, places=1)
        self.assertAlmostEqual(new_p2[0]["chord"], 300.0, places=1)
        self.assertAlmostEqual(new_p2[-1]["chord"], 150.0, places=1)
        # Tip X offset with 0 deg sweep at c/4 = -0.25 * (150 - 300) = 37.5
        self.assertAlmostEqual(new_p2[-1]["position"]["x"], 37.5, places=1)

    def test_airfoil_generators_and_dat_parser(self) -> None:
        from setuav_studio.plugins.geometry.airfoil import (
            naca4,
            naca5,
            biconvex,
            parse_airfoil_dat,
            compute_airfoil_metrics,
            sample_airfoil_points,
            PRESET_AIRFOILS,
        )

        # NACA 4
        pts_4 = naca4("2412")
        m_4 = compute_airfoil_metrics(pts_4)
        self.assertAlmostEqual(m_4["max_thickness"], 0.12, places=2)
        self.assertAlmostEqual(m_4["max_camber"], 0.02, places=2)

        # NACA 5
        pts_5 = naca5("23012")
        m_5 = compute_airfoil_metrics(pts_5)
        self.assertAlmostEqual(m_5["max_thickness"], 0.12, places=2)
        self.assertAlmostEqual(m_5["max_camber"], 0.018, places=2)

        # Biconvex
        pts_bi = biconvex(0.08)
        m_bi = compute_airfoil_metrics(pts_bi)
        self.assertAlmostEqual(m_bi["max_thickness"], 0.08, places=2)
        self.assertEqual(m_bi["max_camber"], 0.0)

        # DAT Parser
        dat_content = """CLARK Y
1.0000 0.0000
0.7000 0.0818
0.3000 0.1170
0.0000 0.0000
0.3000 -0.0380
0.7000 -0.0175
1.0000 0.0000"""
        name, dat_pts = parse_airfoil_dat(dat_content)
        self.assertEqual(name, "CLARK Y")
        self.assertEqual(len(dat_pts), 7)
        self.assertEqual(dat_pts[3], (0.0, 0.0))  # Exact LE preserved

        # Preset lookup
        self.assertIn("Selig S1223", PRESET_AIRFOILS)
        pts_selig = sample_airfoil_points("Selig S1223")
        m_selig = compute_airfoil_metrics(pts_selig)
        self.assertGreater(m_selig["max_camber"], 0.05)

    def test_control_surface_cutouts_and_deflection(self) -> None:
        from setuav_studio.plugins.geometry.lifting_surface_geometry import build_lifting_surface_geometry
        from setuav_studio.project import ProjectDocument

        wing_component = {
            "id": "test-wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 200.0, "airfoil": "2412"},
                        {"position": {"x": 20.0, "y": 500.0, "z": 0.0}, "chord": 150.0, "airfoil": "2412"},
                    ],
                    "control_surfaces": [
                        {
                            "tag": "aileron_1",
                            "type": "aileron",
                            "span_start": 200.0,
                            "span_end": 450.0,
                            "chord": 40.0,
                            "deflection": 20.0,
                        }
                    ],
                }
            },
        }

        lofts = build_lifting_surface_geometry(wing_component)
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
        wing_neutral = deepcopy(wing_component)
        wing_neutral["parameters"]["geometry"]["control_surfaces"][0]["deflection"] = 0.0
        lofts_neutral = build_lifting_surface_geometry(wing_neutral)
        cs_neutral = next(loft for loft in lofts_neutral if "aileron_1" in loft.component_id)

        # Find trailing edge index (maximum X)
        te_idx = max(range(len(cs_neutral.sections[0].points)), key=lambda i: cs_neutral.sections[0].points[i][0])
        te_neutral_z = cs_neutral.sections[0].points[te_idx][2]
        te_deflected_z = cs_loft.sections[0].points[te_idx][2]
        self.assertLess(te_deflected_z, te_neutral_z - 5.0)

        # Test Mirrored Instance (anti-symmetric roll deflection for aileron)
        proj_data = {
            "components": [
                wing_component,
                {
                    "kind": "instance",
                    "id": "test-wing-mirrored",
                    "source": "test-wing",
                    "derivation": {"type": "mirror", "plane": "XZ"},
                },
            ]
        }
        doc = ProjectDocument(Path("/tmp/test.json"), "json", proj_data)
        providers = {"org.setuav.core:lifting-surface": build_lifting_surface_geometry}
        scene_geom = build_project_geometry(doc, providers)

        cs_source = next(l for l in scene_geom.lofts if l.component_id == "test-wing:aileron_1")
        cs_mirror = next(l for l in scene_geom.lofts if l.component_id == "test-wing-mirrored:aileron_1")

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
                        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 165.0, "airfoil": "0012"},
                        {"position": {"x": 50.0, "y": -180.0, "z": 0.0}, "chord": 100.0, "airfoil": "0012"},
                    ],
                    "control_surfaces": [
                        {
                            "tag": "elevator",
                            "type": "elevator",
                            "span_start": 50.0,
                            "span_end": 100.0,
                            "chord": 30.0,
                            "deflection": 10.0,
                        }
                    ],
                }
            },
        }

        lofts = build_lifting_surface_geometry(v_tail_left)
        self.assertEqual(len(lofts), 4)
        cs_loft = next((l for l in lofts if "elevator" in l.component_id), None)
        self.assertIsNotNone(cs_loft)
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
                        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 200.0, "airfoil": "0012"},
                        {"position": {"x": 50.0, "y": 500.0, "z": 0.0}, "chord": 100.0, "airfoil": "0012"},
                    ],
                    "control_surfaces": [
                        {
                            "tag": "aileron",
                            "type": "aileron",
                            "span_start": 100.0,
                            "span_end": 400.0,
                            "chord": 40.0,
                            "hinge_sweep": 0.0,  # Parallel to Y axis (zero sweep)
                            "deflection": 0.0,
                        }
                    ],
                }
            },
        }

        lofts = build_lifting_surface_geometry(wing_with_sweep)
        cs_loft = next(l for l in lofts if "aileron" in l.component_id)
        self.assertEqual(len(cs_loft.sections), 2)
        # Top hinge line X location should be exactly 150.0 mm at both section 0 and section 1
        hinge_sec0_x = cs_loft.sections[0].points[27][0]
        hinge_sec1_x = cs_loft.sections[1].points[27][0]
        self.assertAlmostEqual(hinge_sec0_x, 150.0, delta=0.1)
        self.assertAlmostEqual(hinge_sec1_x, 150.0, delta=0.1)

    def test_fuselage_wing_root_stub_geometry(self) -> None:
        from setuav_studio.plugins.geometry.fuselage_geometry import build_fuselage_geometry
        from setuav_studio.plugins.geometry.scene import build_project_geometry

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
                                        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "profile": {"type": "circle", "diameter": 100.0}},
                                        {"position": {"x": 500.0, "y": 0.0, "z": 0.0}, "profile": {"type": "circle", "diameter": 100.0}},
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
                    "parent": "fuse",
                    "transform": {
                        "position": {"x": 200.0, "y": 70.0, "z": 0.0},
                    },
                    "parameters": {
                        "geometry": {
                            "profiles": [
                                {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 150.0, "airfoil": "0012"},
                                {"position": {"x": 0.0, "y": 300.0, "z": 0.0}, "chord": 100.0, "airfoil": "0012"},
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

        scene_geom = build_project_geometry(mock_project, providers)
        # Should contain fuselage loft, wing loft, and the fuselage wing root stub
        fuse_lofts = [l for l in scene_geom.lofts if l.component_id == "fuse"]
        self.assertEqual(len(fuse_lofts), 2)  # 1 main fuselage segment + 1 wing root stub
        stub_loft = fuse_lofts[1]
        self.assertEqual(len(stub_loft.sections), 2)
        # Inner section must be at fuselage skin Y = 50.0, outer section at wing joint Y = 70.0
        sec_inner = stub_loft.sections[0]
        sec_outer = stub_loft.sections[1]
        self.assertAlmostEqual(sec_inner.points[0][1], 50.0, delta=0.5)
        self.assertAlmostEqual(sec_outer.points[0][1], 70.0, delta=0.5)

    def test_control_surface_editor(self) -> None:
        from setuav_studio.plugin_system import StudioAPI
        from setuav_studio.plugins.geometry.control_surface import ControlSurfaceEditor

        api = StudioAPI()
        cs_comp = {
            "kind": "component",
            "id": "aileron",
            "name": "Aileron",
            "type": "org.setuav.core:control-surface",
            "parent": "main-wing",
            "parameters": {
                "mass": 25.0,
                "geometry": {
                    "tag": "aileron",
                    "type": "aileron",
                    "span_start": 250.0,
                    "span_end": 500.0,
                    "chord": 70.0,
                    "deflection": 20.0,
                    "hinge_sweep": -1.0,
                }
            }
        }

        editor = ControlSurfaceEditor(api, cs_comp)
        self.assertEqual(editor._property_text(editor.general_table, 0), "Aileron")
        self.assertEqual(editor._property_text(editor.properties_table, 0), "aileron")
        self.assertIn("250.0", editor._property_text(editor.properties_table, 2))
        self.assertIn("20.0", editor._property_text(editor.properties_table, 6))

        # Edit deflection
        editor.properties_table.item(6, 1).setText("-15.0")
        self.assertEqual(cs_comp["parameters"]["geometry"]["deflection"], -15.0)

    def test_control_surface_add_delete_no_duplication(self) -> None:
        from setuav_studio.plugin_system import StudioAPI
        from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.project import ProjectDocument
        from setuav_studio.plugins.geometry.scene import build_project_geometry
        from setuav_studio.plugins.geometry.lifting_surface_geometry import build_lifting_surface_geometry
        from setuav_studio.plugins.geometry.fuselage_geometry import build_fuselage_geometry

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
                    "parent": "fuselage",
                    "parameters": {
                        "geometry": {
                            "mirror": True,
                            "profiles": [
                                {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 200.0, "airfoil": "2412"},
                                {"position": {"x": 50.0, "y": 500.0, "z": 0.0}, "chord": 100.0, "airfoil": "2412"},
                            ]
                        }
                    }
                },
                {
                    "kind": "component",
                    "id": "aileron-1",
                    "name": "Aileron 1",
                    "type": "org.setuav.core:control-surface",
                    "parent": "wing",
                    "parameters": {
                        "geometry": {
                            "tag": "aileron_1",
                            "type": "aileron",
                            "span_start": 200.0,
                            "span_end": 450.0,
                            "chord": 40.0,
                            "hinge_sweep": 0.0,
                            "deflection": 0.0
                        }
                    }
                }
            ]
        }

        doc = ProjectDocument("/fake/path", {}, doc_data)
        api = StudioAPI()
        api.set_project(doc)

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
            wing_lofts = [l for l in scene_geom.lofts if "wing" in l.component_id]
            self.assertEqual(len(wing_lofts), 12)

        # 4. Verify components in project remained exactly 5 (no exponential growth)
        self.assertEqual(len(doc.data["components"]), 5)
        self.assertEqual(editor.control_surfaces_table.rowCount(), 3)

        # 5. Delete one control surface
        editor._control_surface_index = 2
        editor.delete_cs_button.click()
        self.assertEqual(editor.control_surfaces_table.rowCount(), 2)
        self.assertEqual(len(doc.data["components"]), 4)

    def test_conformal_wing_root_stubs_angled_and_flat(self) -> None:
        """Verify that root stubs for flat wings and angled V-tails conform to fuselage surface along their span axis."""
        doc = open_project(TEST_PROJECT_PATH)
        providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }
        scene_geom = build_project_geometry(doc, providers)
        fuse_stubs = [l for l in scene_geom.lofts if l.component_id == "fuselage" and len(l.sections) == 2]
        self.assertGreaterEqual(len(fuse_stubs), 2)

        # For each stub, inner section points must be closer to fuselage center than outer section points
        for stub in fuse_stubs:
            inner_sec, outer_sec = stub.sections[0], stub.sections[1]
            self.assertEqual(len(inner_sec.points), len(outer_sec.points))
            # Average distance from fuselage center axis (y=0, z=0) of inner points should be <= outer points
            avg_inner_r = sum(math.sqrt(p[1]**2 + p[2]**2) for p in inner_sec.points) / len(inner_sec.points)
            avg_outer_r = sum(math.sqrt(p[1]**2 + p[2]**2) for p in outer_sec.points) / len(outer_sec.points)
            self.assertLessEqual(avg_inner_r, avg_outer_r)


if __name__ == "__main__":
    unittest.main()
