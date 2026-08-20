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

from tests._common import TEST_PROJECT_PATH, get_qapp


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

        self.assertEqual(len(palette_names()), 3)
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
        from setuav_studio.plugin_system import StudioAPI
        from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor

        get_qapp()
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
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
        driver_mode_combo = editor.driver_groups_table.cellWidget(0, 1)
        self.assertIsNotNone(driver_mode_combo)
        driver_mode_combo.setCurrentIndex(1)  # Span, Root & Tip
        self.assertEqual(editor._driver_mode, "span_root_tip")
        span_spin = editor.planform_table.cellWidget(1, 1)
        if span_spin:
            span_spin.setValue(1200.0)
        else:
            editor._on_planform_spinbox_changed("span", 1200.0)
        # Profiles should scale such that total tip-to-tip wingspan = 2 * (y_offset + y_tip) = 1200.0 mm
        # With attachment y_offset = 75.0 mm, local tip position is at 525.0 mm
        self.assertAlmostEqual(
            float(wing_comp["parameters"]["geometry"]["profiles"][-1]["position"]["y"]),
            525.0,
            places=1,
        )

        # Check locking behavior in driver mode
        # Column 2 (Span Y) and Column 3 (Chord) should NOT have ItemIsEditable in driver mode
        self.assertFalse(bool(editor.profiles_table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable))
        self.assertFalse(bool(editor.profiles_table.item(0, 3).flags() & Qt.ItemFlag.ItemIsEditable))
        # Profile properties table should have chord, span_y, offset_x widgets disabled
        editor._load_profile(0)
        self.assertFalse(editor.profile_properties_table.cellWidget(1, 1).isEnabled())  # chord
        self.assertFalse(editor.profile_properties_table.cellWidget(3, 1).isEnabled())  # span_y
        self.assertFalse(editor.profile_properties_table.cellWidget(4, 1).isEnabled())  # offset_x
        self.assertFalse(editor.add_profile_button.isEnabled())
        self.assertFalse(editor.duplicate_profile_button.isEnabled())

        # Switch to manual mode: all columns and station properties become editable
        driver_mode_combo.setCurrentIndex(4)  # Manual
        self.assertEqual(editor._driver_mode, "manual")
        self.assertTrue(bool(editor.profiles_table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable))
        self.assertTrue(bool(editor.profiles_table.item(0, 3).flags() & Qt.ItemFlag.ItemIsEditable))
        editor._load_profile(0)
        self.assertTrue(editor.profile_properties_table.cellWidget(1, 1).isEnabled())  # chord
        self.assertTrue(editor.profile_properties_table.cellWidget(3, 1).isEnabled())  # span_y
        self.assertTrue(editor.profile_properties_table.cellWidget(4, 1).isEnabled())  # offset_x
        self.assertTrue(editor.add_profile_button.isEnabled())
        self.assertTrue(editor.duplicate_profile_button.isEnabled())

        # Add control surface
        init_cs = editor.control_surfaces_table.rowCount()
        editor.add_cs_button.click()
        self.assertEqual(editor.control_surfaces_table.rowCount(), init_cs + 1)
        # Edit control surface via cs_properties_table
        cs_idx = editor._control_surface_index
        spin_defl = editor.cs_properties_table.cellWidget(6, 1)
        if spin_defl:
            spin_defl.setValue(18.5)
        else:
            editor._on_cs_prop_spinbox_changed("deflection", 18.5)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["deflection"], 18.5)

        spin_chord = editor.cs_properties_table.cellWidget(4, 1)
        if spin_chord:
            spin_chord.setValue(55.0)
        else:
            editor._on_cs_prop_spinbox_changed("chord", 55.0)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["chord"], 55.0)

        spin_sweep = editor.cs_properties_table.cellWidget(5, 1)
        if spin_sweep:
            spin_sweep.setValue(5.0)
        else:
            editor._on_cs_prop_spinbox_changed("hinge_sweep", 5.0)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["hinge_sweep"], 5.0)

        # Edit tag inline via control_surfaces_table
        editor.control_surfaces_table.item(cs_idx, 0).setText("aileron_custom")
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["tag"], "aileron_custom")
        self.assertEqual(editor.cs_properties_table.item(0, 1).text(), "aileron_custom")

        # Section Selection in 3D Viewport
        editor.profiles_table.selectRow(1)
        self.assertEqual(api.current_section_selection, ("main-wing", 0, 1))

        # Check Attachment (Component Transform)
        self.assertAlmostEqual(editor.attachment_table.cellWidget(0, 0).value(), 305.00)
        self.assertAlmostEqual(editor.attachment_table.cellWidget(0, 1).value(), 75.00)
        self.assertAlmostEqual(editor.attachment_table.cellWidget(0, 2).value(), 40.00)

        # Edit Attachment Transform
        editor.attachment_table.cellWidget(0, 0).setValue(320.00)
        self.assertEqual(wing_comp["transform"]["position"]["x"], 320.0)

        # Edit height_z in profile_properties_table (Row 5)
        spin_z = editor.profile_properties_table.cellWidget(5, 1)
        if spin_z:
            spin_z.setValue(25.0)
        else:
            editor._on_profile_prop_spinbox_changed("height_z", 25.0)
        self.assertEqual(wing_comp["parameters"]["geometry"]["profiles"][1]["position"]["z"], 25.0)

        # Edit chord in profile_properties_table (Row 1)
        spin_chord = editor.profile_properties_table.cellWidget(1, 1)
        if spin_chord:
            spin_chord.setValue(180.0)
        else:
            editor._on_profile_prop_spinbox_changed("chord", 180.0)
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

        # Mode with y_offset = 100.0 mm and symmetric = True
        new_p3, m3 = solve_wing_planform(
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
        from setuav_studio.plugins.geometry.wing_planform_engine import compute_planform_metrics
        m_asym = compute_planform_metrics(profiles, symmetric=False)
        self.assertAlmostEqual(m_asym["span"], 540.0, places=1)

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
                        "position": {"x": 200.0, "y": 0.0, "z": 0.0},
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
        wing_lofts = [l for l in scene_geom.lofts if l.component_id == "wing"]
        self.assertEqual(len(wing_lofts), 1)
        wing_loft = wing_lofts[0]
        self.assertEqual(len(wing_loft.sections), 2)

        from setuav_studio.plugins.geometry.mesh import build_loft_solid_vertices, build_loft_wire_vertices
        solid_verts = build_loft_solid_vertices(scene_geom)
        wire_verts = build_loft_wire_vertices(scene_geom)
        self.assertGreater(len(solid_verts), 0)
        self.assertGreater(len(wire_verts), 0)

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
        self.assertEqual(editor.properties_table.cellWidget(0, 1).currentData(), "aileron")
        self.assertIn("250.0", editor._property_text(editor.properties_table, 1))
        self.assertIn("20.0", editor._property_text(editor.properties_table, 5))

        # Edit deflection
        editor.properties_table.item(5, 1).setText("-15.0")
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
        """Verify that lifting surface and empennage lofts and root stubs are properly generated in scene."""
        doc = open_project(TEST_PROJECT_PATH)
        providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }
        scene_geom = build_project_geometry(doc, providers)
        wing_lofts = [l for l in scene_geom.lofts if "wing" in l.component_id or "v-tail" in l.component_id]
        self.assertGreaterEqual(len(wing_lofts), 2)
        fuse_stubs = [l for l in scene_geom.lofts if l.component_id == "fuselage" and len(l.sections) == 2]
        self.assertGreaterEqual(len(fuse_stubs), 2)

    def test_twist_location_pivot_rotation(self) -> None:
        """Verify that section transform rotates exactly around the chosen twist_location chord fraction."""
        from setuav_studio.plugins.geometry.transforms import section_transform, transform_point

        pos = {"x": 100.0, "y": 200.0, "z": 50.0}
        chord = 200.0
        sec_0 = {"position": pos, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}}
        sec_w = {"position": pos, "rotation": {"x": 0.0, "y": -5.0, "z": 0.0}}  # -5 deg pitch (washout)

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
        from setuav_studio.plugins.geometry.wing_planform_engine import (
            compute_planform_metrics,
            solve_wing_planform,
        )

        profiles = [
            {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 200.0, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}},
            {"position": {"x": 0.0, "y": 250.0, "z": 0.0}, "chord": 150.0, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}},
            {"position": {"x": 0.0, "y": 500.0, "z": 0.0}, "chord": 100.0, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}},
        ]
        inputs = {
            "span": 1000.0,
            "root_chord": 200.0,
            "tip_chord": 100.0,
            "sweep": 5.0,
            "washout": -3.0,
        }
        new_profiles, metrics = solve_wing_planform("span_root_tip", inputs, profiles)
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
                        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 200.0, "airfoil": "0012"},
                        {"position": {"x": 0.0, "y": 500.0, "z": 0.0}, "chord": 100.0, "airfoil": "0012"},
                    ]
                }
            }
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
        from setuav_studio.plugin_system import StudioAPI
        from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor

        api = StudioAPI()
        wing_comp = {
            "id": "main-wing",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 200.0, "airfoil": "0012"},
                        {"position": {"x": 0.0, "y": 500.0, "z": 0.0}, "chord": 100.0, "airfoil": "0012"},
                    ]
                }
            }
        }
        mock_doc = type("Doc", (), {"data": {"components": [wing_comp]}})()
        api.current_project = mock_doc

        editor = LiftingSurfaceEditor(api, wing_comp)
        # Default tip cap is flat — table now has: tip_type, tip_length, tip_offset_x,
        # winglet_height, cant_angle, winglet_sweep, toe_angle, root_chord_scale, tip_chord_scale = 9 rows
        self.assertEqual(editor.tip_caps_table.rowCount(), 9)
        self.assertEqual(wing_comp["parameters"]["geometry"].get("tip_treatment", {}).get("type", "flat"), "flat")

        # Change tip cap type to round via UI
        editor._on_tip_cap_type_changed("round")
        self.assertEqual(wing_comp["parameters"]["geometry"]["tip_treatment"]["type"], "round")

        # Edit tip length
        for r in range(editor.tip_caps_table.rowCount()):
            if editor._property_key(editor.tip_caps_table, r) == "tip_length":
                spin = editor.tip_caps_table.cellWidget(r, 1)
                if spin:
                    spin.setValue(35.0)
                else:
                    editor._on_tip_cap_spinbox_changed("tip_length", 35.0)
                break
        self.assertAlmostEqual(wing_comp["parameters"]["geometry"]["tip_treatment"]["length"], 35.0)

    def test_winglet_geometry(self) -> None:
        """Verify _build_winglet_loft generates correct geometry."""
        from setuav_studio.plugins.geometry.lifting_surface_geometry import _build_winglet_loft

        tip_profile = {
            "chord": 100.0,
            "airfoil": "NACA 0012",
            "position": {"x": 0.0, "y": 500.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
        }

        # Basic vertical winglet (cant=90°)
        loft = _build_winglet_loft(
            comp_id="wing",
            tip_profile=tip_profile,
            span_dir=1.0,
            winglet_height=100.0,
            cant_angle_deg=90.0,
            sweep_deg=30.0,
            toe_angle_deg=0.0,
            root_chord_scale=1.0,
            tip_chord_scale=0.5,
        )
        self.assertIsNotNone(loft)
        self.assertEqual(loft.component_id, "wing:winglet")
        # Should have n_stations=12 sections
        self.assertEqual(len(loft.sections), 12)
        # All sections should have the same number of points
        pts_per_section = len(loft.sections[0].points)
        self.assertGreater(pts_per_section, 0)
        for sec in loft.sections:
            self.assertEqual(len(sec.points), pts_per_section)

        # Root section (s=0) should overlap tip profile Y position (y=500)
        root_ys = [p[1] for p in loft.sections[0].points]
        self.assertAlmostEqual(min(root_ys), 500.0, delta=2.0)

        # Tip section (s=100) fully vertical cant=90° → Y barely changes, Z increases
        tip_zs = [p[2] for p in loft.sections[-1].points]
        root_zs = [p[2] for p in loft.sections[0].points]
        self.assertGreater(max(tip_zs), max(root_zs))

        # Zero winglet_height → None
        none_loft = _build_winglet_loft(
            comp_id="wing", tip_profile=tip_profile, winglet_height=0.0
        )
        self.assertIsNone(none_loft)

        # Winglet with sweep should shift LE forward
        swept = _build_winglet_loft(
            comp_id="wing",
            tip_profile=tip_profile,
            winglet_height=100.0,
            cant_angle_deg=75.0,
            sweep_deg=30.0,
        )
        unswept = _build_winglet_loft(
            comp_id="wing",
            tip_profile=tip_profile,
            winglet_height=100.0,
            cant_angle_deg=75.0,
            sweep_deg=0.0,
        )
        # Swept tip section should have higher mean X
        swept_x = sum(p[0] for p in swept.sections[-1].points) / len(swept.sections[-1].points)
        unswept_x = sum(p[0] for p in unswept.sections[-1].points) / len(unswept.sections[-1].points)
        self.assertGreater(swept_x, unswept_x)

    def test_fuselage_section_dialog_and_metrics(self) -> None:
        """Verify 2D fuselage section metrics calculation and dialog functionality."""
        from setuav_studio.plugin_system import StudioAPI
        from setuav_studio.plugins.geometry.fuselage_geometry import sample_profile
        from setuav_studio.plugins.geometry.fuselage_section_dialog import (
            FuselageCanvasWidget,
            FuselageSectionDialog,
            compute_section_metrics,
        )

        # 1. Test geometric metrics calculation
        circle_pts = sample_profile({"type": "circle", "diameter": 100.0})
        m_circ = compute_section_metrics(circle_pts)
        self.assertAlmostEqual(m_circ["area"], math.pi * 50.0**2, delta=20.0)
        self.assertAlmostEqual(m_circ["perimeter"], math.pi * 100.0, delta=2.0)
        self.assertAlmostEqual(m_circ["width"], 100.0, places=1)
        self.assertAlmostEqual(m_circ["height"], 100.0, places=1)

        rect_pts = sample_profile({"type": "rectangle", "width": 120.0, "height": 80.0, "corner_radius": 10.0})
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
            "parameters": {
                "mass": 500.0,
                "geometry": {
                    "segments": [
                        {
                            "id": "seg_1",
                            "name": "Nose to Tail",
                            "sections": [
                                {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}, "profile": {"type": "circle", "diameter": 80.0}},
                                {"position": {"x": 300.0, "y": 0.0, "z": 0.0}, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}, "profile": {"type": "circle", "diameter": 120.0}},
                                {"position": {"x": 700.0, "y": 0.0, "z": 0.0}, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}, "profile": {"type": "circle", "diameter": 60.0}},
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
        if w_spin:
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

    def test_numeric_spinbox_and_table_widget(self) -> None:
        """Verify NumericSpinBox focused-only mouse wheel handling and set_table_spinbox integration."""
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtWidgets import QTableWidget
        from setuav_studio.ui.numeric_spinbox import (
            NumericSpinBox,
            set_table_spinbox,
        )

        # 1. Test NumericSpinBox widget
        spinbox = NumericSpinBox(decimals=1, step=1.0, suffix="mm")
        spinbox.setValue(100.0)
        self.assertEqual(spinbox.value(), 100.0)

        # Non-focused wheel event -> ignored so parent scroll area is not interrupted
        wheel_ev = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        spinbox.wheelEvent(wheel_ev)
        self.assertFalse(wheel_ev.isAccepted())
        self.assertEqual(spinbox.value(), 100.0)

        # Focused wheel event -> accepted and adjusts value
        spinbox.show()
        spinbox.setFocus()
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        if not spinbox._is_active_focus():
            spinbox.lineEdit().setFocus()
            QApplication.processEvents()
        wheel_ev.setAccepted(False)
        spinbox.wheelEvent(wheel_ev)
        if spinbox._is_active_focus():
            self.assertTrue(wheel_ev.isAccepted())
            self.assertEqual(spinbox.value(), 101.0)

        # 2. Test set_table_spinbox integration
        table = QTableWidget(3, 2)
        changed_vals = []
        sb = set_table_spinbox(
            table,
            0,
            1,
            50.0,
            step=2.0,
            decimals=1,
            suffix="mm",
            on_changed=lambda v: changed_vals.append(v),
        )
        self.assertIsNotNone(sb)
        self.assertEqual(table.cellWidget(0, 1), sb)
        self.assertEqual(sb.value(), 50.0)
        self.assertEqual(sb.suffix(), " mm")

        # Changing value triggers on_changed callback
        sb.setValue(54.0)
        self.assertIn(54.0, changed_vals)

    def test_nowheel_combobox_and_filter(self) -> None:
        """Verify NoWheelComboBox ignores mouse wheel events and ComboBoxWheelFilter intercepts them."""
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtWidgets import QApplication, QComboBox
        from setuav_studio.ui.numeric_spinbox import NoWheelComboBox
        from setuav_studio.ui.theme import ComboBoxWheelFilter

        # 1. Test NoWheelComboBox ignores wheelEvent
        combo = NoWheelComboBox()
        combo.addItems(["Option A", "Option B", "Option C"])
        combo.setCurrentIndex(0)

        wheel_ev = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        combo.wheelEvent(wheel_ev)
        self.assertFalse(wheel_ev.isAccepted())
        self.assertEqual(combo.currentIndex(), 0)

        # 2. Test ComboBoxWheelFilter intercepts standard QComboBox wheel events
        filter_obj = ComboBoxWheelFilter()
        std_combo = QComboBox()
        std_combo.addItems(["Option 1", "Option 2"])
        std_combo.setCurrentIndex(0)

        wheel_ev.setAccepted(True)
        res = filter_obj.eventFilter(std_combo, wheel_ev)
        self.assertTrue(res)
        self.assertFalse(wheel_ev.isAccepted())


if __name__ == "__main__":
    unittest.main()




