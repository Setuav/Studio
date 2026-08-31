import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from PySide6.QtCore import Qt
from setuav_studio.plugins.geometry.data import GeometryData, LoftGeometry, Section
from setuav_studio.plugins.geometry.fuselage_geometry import (
    SECTION_SAMPLES,
    build_fuselage_geometry,
    sample_profile,
)
from setuav_studio.plugins.geometry.lifting_surface_geometry import (
    build_lifting_surface_geometry,
)
from setuav_studio.plugins.geometry.mesh import build_loft_solid_vertices
from setuav_studio.plugins.geometry.scene import build_project_geometry

from setuav_studio.project import ProjectDocument, open_project
from tests._common import TEST_PROJECT_PATH, get_qapp


class GeometryTests(unittest.TestCase):
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
                        {
                            "position": {"x": 40, "y": -700},
                            "chord": 130,
                            "airfoil": {"type": "naca", "code": "0012"},
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
        from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor

        from setuav_studio.plugin_system import StudioAPI

        get_qapp()
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)

        wing_comp = next(c for c in doc.data["components"] if c.get("id") == "main-wing")
        editor = LiftingSurfaceEditor(api, wing_comp)

        self.assertEqual(editor.planform_table.rowCount(), 8)
        self.assertIn("span", editor.planform_table.get_current_values())

        # Check Attach to combo selection
        parent_combo = editor.general_table.cellWidget(2, 1)
        self.assertIsNotNone(parent_combo)
        self.assertEqual(parent_combo.currentData(), "fuselage")
        self.assertGreaterEqual(parent_combo.count(), 2)

        # Test Wing Planform Sizing driver resize
        editor._on_planform_spinbox_changed("span", 1200.0)
        # Profiles should scale such that total tip-to-tip wingspan = 2 * (y_offset + y_tip) = 1200.0 mm
        # With attachment y_offset = 75.0 mm, local tip position is at 525.0 mm
        self.assertAlmostEqual(
            float(wing_comp["parameters"]["geometry"]["profiles"][-1]["position"]["y"]),
            525.0,
            places=1,
        )

        # Test Wing Angles table
        self.assertEqual(editor.wing_angles_table.rowCount(), 6)
        editor._on_wing_angle_changed("dihedral", 3.0)
        self.assertGreater(
            float(wing_comp["parameters"]["geometry"]["profiles"][-1]["position"]["z"]), 0.0
        )
        editor._on_wing_angle_changed("sweep_curvature", 25.0)
        self.assertEqual(wing_comp["parameters"]["geometry"].get("sweep_curvature"), 25.0)

        # Check sections table, section planform sizing, angles, and airfoils
        self.assertGreaterEqual(editor.sections_table.rowCount(), 1)
        editor._load_section(0)
        self.assertEqual(editor.section_planform_table.rowCount(), 8)
        self.assertEqual(editor.section_properties_table.rowCount(), 6)
        self.assertTrue(editor.insert_section_button.isEnabled())
        self.assertTrue(editor.split_section_button.isEnabled())

        # Test Wing Sections table direct cell editing
        editor.sections_table.item(0, 1).setText("600.0")
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
        if spin_defl:
            spin_defl.setValue(18.5)
        else:
            editor._on_cs_prop_spinbox_changed("deflection", 18.5)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["deflection"], 18.5)

        spin_chord = _get_cs_spin("chord")
        if spin_chord:
            spin_chord.setValue(55.0)
        else:
            editor._on_cs_prop_spinbox_changed("chord", 55.0)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["chord"], 55.0)

        spin_sweep = _get_cs_spin("hinge_sweep")
        if spin_sweep:
            spin_sweep.setValue(5.0)
        else:
            editor._on_cs_prop_spinbox_changed("hinge_sweep", 5.0)
        self.assertEqual(editor._cs_geom(editor._control_surfaces()[cs_idx])["hinge_sweep"], 5.0)

        # Edit tag inline via control_surfaces_table
        editor.control_surfaces_table.item(cs_idx, 0).setText("aileron_custom")
        self.assertEqual(
            editor._cs_geom(editor._control_surfaces()[cs_idx])["tag"], "aileron_custom"
        )
        self.assertEqual(editor.cs_properties_table.item(0, 1).text(), "aileron_custom")

        # Section Selection in 3D Viewport
        editor._on_section_selected(0, 0)
        self.assertEqual(api.current_section_selection, ("main-wing", 0, 0))

        # Check Attachment (Component Transform)
        self.assertAlmostEqual(
            editor.attachment_table.cellWidget(0, 0).value(),
            wing_comp["transform"]["position"]["x"],
        )
        self.assertAlmostEqual(editor.attachment_table.cellWidget(0, 1).value(), 75.00)
        self.assertAlmostEqual(editor.attachment_table.cellWidget(0, 2).value(), 40.00)

        # Edit Attachment Transform
        editor.attachment_table.cellWidget(0, 0).setValue(320.00)
        self.assertEqual(wing_comp["transform"]["position"]["x"], 320.0)

        # Edit tip_chord in section_planform_table
        sec_values = editor.section_planform_table.get_current_values()
        sec_values["tip_chord"] = 180.0
        editor._on_section_planform_changed(sec_values)
        self.assertEqual(wing_comp["parameters"]["geometry"]["profiles"][1]["chord"], 180.0)

        # Edit dihedral in section_angles_table
        editor._on_section_angle_changed("dihedral", 5.0)
        self.assertIn("5.0", editor.sections_table.item(0, 3).text())

        # Split section
        init_secs = editor.sections_table.rowCount()
        editor._load_section(0)
        editor._split_section()
        self.assertEqual(editor.sections_table.rowCount(), init_secs + 1)

        # Delete section
        editor._delete_section()
        self.assertEqual(editor.sections_table.rowCount(), init_secs)

    def test_wing_planform_engine_modes(self) -> None:
        from setuav_studio.plugins.geometry.wing_planform_engine import (
            calc_tan_sweep_at,
            compute_planform_metrics,
            solve_wing_planform,
        )

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

        # Mode: span_root_tip with multi-station morphing (preserves intermediate relative chord)
        new_p2, m2 = solve_wing_planform(
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
        _new_p_2s, m_2s = solve_wing_planform(
            "span_root_tip",
            {"span": 1400.0, "root_chord": 300.0, "tip_chord": 150.0, "sweep": 0.0},
            profiles_2s,
            sweep_loc=0.25,
        )
        self.assertEqual(m_2s["span"], 1400.0)
        self.assertEqual(m_2s["area"], 1400.0 * (300.0 + 150.0) / 2.0)

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
        m_asym = compute_planform_metrics(profiles, symmetric=False)
        self.assertAlmostEqual(m_asym["span"], 540.0, places=1)

        # OpenVSP analytic sweep conversion formula test
        # Sweep 30 deg at LE (0.0), AR=6.0, taper=0.5 -> QC (0.25) sweep is ~27.55 deg
        sw_qc = calc_tan_sweep_at(0.25, 30.0, 0.0, aspect_ratio=6.0, taper_ratio=0.5)
        self.assertAlmostEqual(sw_qc, 27.55, places=1)

    def test_wing_sections_engine_kinematics(self) -> None:
        from setuav_studio.plugins.geometry.wing_sections_engine import (
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

    def test_airfoil_generators_and_dat_parser(self) -> None:
        from setuav_studio.plugins.geometry.airfoil import (
            PRESET_AIRFOILS,
            biconvex,
            compute_airfoil_metrics,
            naca4,
            naca5,
            parse_airfoil_dat,
            sample_airfoil_points,
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
        from setuav_studio.plugins.geometry.lifting_surface_geometry import (
            build_lifting_surface_geometry,
        )

        from setuav_studio.project import ProjectDocument

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
        cs_loft = next((loft for loft in lofts if "elevator" in loft.component_id), None)
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
        cs_loft = next(loft for loft in lofts if "aileron" in loft.component_id)
        self.assertEqual(len(cs_loft.sections), 2)
        # Top hinge line X location should be exactly 150.0 mm at both section 0 and section 1
        hinge_sec0_x = cs_loft.sections[0].points[27][0]
        hinge_sec1_x = cs_loft.sections[1].points[27][0]
        self.assertAlmostEqual(hinge_sec0_x, 150.0, delta=0.1)
        self.assertAlmostEqual(hinge_sec1_x, 150.0, delta=0.1)

    def test_fuselage_wing_root_stub_geometry(self) -> None:
        from setuav_studio.plugins.geometry.fuselage_geometry import build_fuselage_geometry
        from setuav_studio.plugins.geometry.lifting_surface_geometry import (
            build_lifting_surface_geometry,
        )
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

        scene_geom = build_project_geometry(mock_project, providers)
        wing_lofts = [loft for loft in scene_geom.lofts if loft.component_id == "wing"]
        self.assertEqual(len(wing_lofts), 1)
        wing_loft = wing_lofts[0]
        self.assertEqual(len(wing_loft.sections), 2)

        from setuav_studio.plugins.geometry.mesh import (
            WIRE_FEATURE,
            WIRE_FULL,
            build_loft_solid_vertices,
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
                                "airfoil": {"spec": "0012"},
                            },
                            {
                                "chord": 100.0,
                                "position": {"x": 50, "y": 500, "z": 0},
                                "airfoil": {"spec": "0012"},
                            },
                        ],
                        "tip_treatment": {
                            "type": tip_t,
                            "length": 30.0,
                        },
                    }
                },
            }
            cap_lofts = build_lifting_surface_geometry(wing_with_cap)
            cap_geom = GeometryData(cap_lofts)
            cap_wire_feature = build_loft_wire_vertices(cap_geom, wire_mode=WIRE_FEATURE)
            self.assertGreater(len(cap_wire_feature), 0)

        # Test control surface vs wing selection matching
        from setuav_studio.plugins.geometry.mesh import _is_matching_component

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

    def test_control_surface_editor(self) -> None:
        from setuav_studio.plugins.geometry.control_surface import ControlSurfaceEditor

        from setuav_studio.plugin_system import StudioAPI

        api = StudioAPI()
        cs_comp = {
            "kind": "component",
            "id": "aileron",
            "name": "Aileron",
            "type": "org.setuav.core:control-surface",
            "parent": "main-wing",
            "attach_to": "main-wing",
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
                },
            },
        }

        editor = ControlSurfaceEditor(api, cs_comp)
        self.assertEqual(editor._property_text(editor.general_table, 0), "Aileron")
        type_widget = editor.properties_table.cellWidget(1, 1)
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
        from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor

        from setuav_studio.plugin_system import StudioAPI
        from setuav_studio.project import ProjectDocument

        wing_comp = {
            "kind": "component",
            "id": "main-wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {"chord": 200.0, "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
                        {"chord": 100.0, "position": {"x": 50.0, "y": 1000.0, "z": 0.0}},
                    ],
                    "control_surfaces": [
                        {
                            "tag": "aileron_ratio",
                            "type": "aileron",
                            "span_mode": "ratio",
                            "eta_start": 0.5,
                            "eta_end": 0.9,
                            "span_start": 500.0,
                            "span_end": 900.0,
                            "chord_mode": "ratio",
                            "chord_fraction": 0.25,
                            "chord": 50.0,
                        },
                        {
                            "tag": "flap_dim",
                            "type": "flap",
                            "span_mode": "dimension",
                            "span_start": 100.0,
                            "span_end": 400.0,
                            "eta_start": 0.1,
                            "eta_end": 0.4,
                            "chord_mode": "dimension",
                            "chord": 45.0,
                            "chord_fraction": 0.225,
                        },
                    ],
                }
            },
        }
        doc = ProjectDocument(Path("/tmp/test.json"), "json", {"components": [wing_comp]})
        api = StudioAPI()
        api._host.set_project(doc)
        editor = LiftingSurfaceEditor(api, wing_comp)

        # 1. Test live spinbox sync when user edits eta_start on aileron (index 0)
        editor._load_control_surface(0)
        editor._on_cs_prop_spinbox_changed("eta_start", 0.6)
        geom0 = editor._geometry()["control_surfaces"][0]
        self.assertAlmostEqual(geom0["eta_start"], 0.6)
        self.assertAlmostEqual(geom0["span_start"], 600.0)  # 0.6 * 1000.0

        # 2. Scale the wing span from 1000 to 2000 mm
        wing_comp["parameters"]["geometry"]["profiles"][1]["position"]["y"] = 2000.0
        editor._sync_control_surfaces_with_wing()

        # Ratio aileron should scale its span_start from 600mm to 1200mm (0.6 * 2000)
        self.assertAlmostEqual(geom0["span_start"], 1200.0)
        self.assertAlmostEqual(geom0["span_end"], 1800.0)  # 0.9 * 2000

        # Dimension flap should keep its fixed 100-400mm span, but eta updates to 0.05 - 0.20
        geom1 = editor._geometry()["control_surfaces"][1]
        self.assertAlmostEqual(geom1["span_start"], 100.0)
        self.assertAlmostEqual(geom1["span_end"], 400.0)
        self.assertAlmostEqual(geom1["eta_start"], 0.05)
        self.assertAlmostEqual(geom1["eta_end"], 0.20)

    def test_control_surface_add_delete_no_duplication(self) -> None:
        from setuav_studio.plugins.geometry.fuselage_geometry import build_fuselage_geometry
        from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.plugins.geometry.lifting_surface_geometry import (
            build_lifting_surface_geometry,
        )
        from setuav_studio.plugins.geometry.scene import build_project_geometry

        from setuav_studio.plugin_system import StudioAPI
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
                    "parent": "wing",
                    "attach_to": "wing",
                    "parameters": {
                        "geometry": {
                            "tag": "aileron_1",
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

        doc = ProjectDocument("/fake/path", {}, doc_data)
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
        from setuav_studio.plugins.geometry.transforms import section_transform, transform_point

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
        from setuav_studio.plugins.geometry.wing_planform_engine import (
            compute_planform_metrics,
            solve_wing_planform,
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
        from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor

        from setuav_studio.plugin_system import StudioAPI

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
        mock_doc = type("Doc", (), {"data": {"components": [wing_comp]}})()
        api.current_project = mock_doc

        editor = LiftingSurfaceEditor(api, wing_comp)
        # Default tip cap is flat — table has 1 row: tip_type
        self.assertEqual(editor.tip_caps_table.rowCount(), 1)
        self.assertEqual(
            wing_comp["parameters"]["geometry"].get("tip_treatment", {}).get("type", "flat"), "flat"
        )

        # Change tip cap type to round via UI (expands to 3 rows)
        editor._on_tip_cap_type_changed("round")
        self.assertEqual(editor.tip_caps_table.rowCount(), 3)
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

        # Switch to winglet and edit winglet parameters directly via UI
        editor._on_tip_cap_type_changed("winglet")
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

        # Check 4-cell projected metrics live update widget
        self.assertTrue(hasattr(editor, "metric_height_val"))
        self.assertTrue(hasattr(editor, "metric_span_val"))
        self.assertIn("mm", editor.metric_height_val.text())
        self.assertIn("mm", editor.metric_span_val.text())

    def test_winglet_geometry(self) -> None:
        """Verify _build_winglet_loft generates correct curved/scimitar geometry."""
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
            n_stations=24,
        )
        self.assertIsNotNone(loft)
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
        none_loft = _build_winglet_loft(comp_id="wing", tip_profile=tip_profile, winglet_height=0.0)
        self.assertIsNone(none_loft)

        # Curved scimitar winglet with independent LE/TE curves and thickness taper
        scimitar_loft = _build_winglet_loft(
            comp_id="wing",
            tip_profile=tip_profile,
            winglet_height=140.0,
            cant_root_deg=0.0,
            cant_tip_deg=85.0,
            blend_radius=50.0,
            match_wing_tangent=True,
            incoming_le_sweep_deg=10.0,
            incoming_te_sweep_deg=5.0,
            le_sweep_tip_deg=55.0,
            le_curvature=10.0,
            te_sweep_tip_deg=-15.0,
            te_curvature=-8.0,
            toe_root_deg=0.0,
            toe_tip_deg=-2.0,
            tip_thickness_scale=0.6,
            taper_curve=0.85,
            n_stations=24,
        )
        self.assertIsNotNone(scimitar_loft)
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

    def test_fuselage_section_dialog_and_metrics(self) -> None:
        """Verify 2D fuselage section metrics calculation and dialog functionality."""
        from setuav_studio.plugins.geometry.fuselage_geometry import sample_profile
        from setuav_studio.plugins.geometry.fuselage_section_dialog import (
            FuselageCanvasWidget,
            FuselageSectionDialog,
            compute_section_metrics,
        )

        from setuav_studio.plugin_system import StudioAPI

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
            "parameters": {
                "mass": 500.0,
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
        from PySide6.QtWidgets import QComboBox

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

    # -------------------------------------------------------------------------
    # AirfoilDialog coverage (Faz 3.11)
    # -------------------------------------------------------------------------

    def test_airfoil_dialog_initial_selection(self) -> None:
        """Verify initial selection resolves preset names, NACA codes, and dict specs."""
        from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog

        # Full preset name -> preset row selected on library tab
        dlg = AirfoilDialog("NACA 0012")
        self.assertEqual(dlg.tabs.currentIndex(), 0)
        self.assertEqual(dlg._selected_airfoil_data, "0012")
        current = dlg.preset_list.currentItem()
        self.assertEqual(str(current.data(Qt.ItemDataRole.UserRole)), "NACA 0012")

        # Raw code -> falls through to NACA generator tab
        dlg_code = AirfoilDialog("23012")
        self.assertEqual(dlg_code.tabs.currentIndex(), 1)
        self.assertEqual(dlg_code.naca_code_input.text(), "23012")
        self.assertEqual(dlg_code._selected_airfoil_data, "23012")

        # Dict spec with code -> NACA tab, code loaded
        dlg_dict = AirfoilDialog({"code": "0012"})
        self.assertEqual(dlg_dict.tabs.currentIndex(), 1)
        self.assertEqual(dlg_dict.naca_code_input.text(), "0012")
        self.assertEqual(dlg_dict._selected_airfoil_data, "0012")

    def test_airfoil_dialog_preset_selection_and_metrics(self) -> None:
        """Verify preset selection updates canvas, metrics, and selected spec."""
        from setuav_studio.plugins.geometry.airfoil import PRESET_AIRFOILS
        from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog

        dialog = AirfoilDialog("NACA 2412")
        # naca-type preset selected -> spec is the code string
        self.assertEqual(dialog._selected_airfoil_data, "2412")
        self.assertIn("12.0%", dialog.max_thick_label.text())
        self.assertEqual(len(dialog.canvas._points), 128)  # 65 upper + 63 lower

        # coordinates-type preset (file-backed) -> dict spec with points
        clark_row = next(
            i
            for i in range(dialog.preset_list.count())
            if dialog.preset_list.item(i).data(Qt.ItemDataRole.UserRole) == "Clark-Y"
        )
        dialog.preset_list.setCurrentRow(clark_row)
        selected = dialog._selected_airfoil_data
        self.assertIsInstance(selected, dict)
        self.assertEqual(selected["type"], "coordinates")
        self.assertEqual(selected["name"], "Clark-Y")
        self.assertGreater(len(selected["points"]), 0)
        self.assertEqual(len(dialog.canvas._points), len(selected["points"]))
        self.assertGreater(len(dialog.canvas._metrics), 0)
        self.assertIn("Points:", dialog.pts_count_label.text())

        # metrics reflect the new airfoil
        self.assertGreater(len(PRESET_AIRFOILS), 0)

    def test_airfoil_dialog_naca_generation(self) -> None:
        """Verify 4/5-digit NACA generation, radio swapping, and desc label."""
        from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog

        dialog = AirfoilDialog("2412")
        self.assertEqual(dialog.tabs.currentIndex(), 1)
        self.assertIn("12% thickness", dialog.naca_desc_label.text())

        dialog.naca_code_input.setText("4415")
        self.assertEqual(dialog._selected_airfoil_data, "4415")
        self.assertEqual(len(dialog.canvas._points), 128)
        self.assertIn("15.0%", dialog.max_thick_label.text())
        self.assertIn("4% camber at 40% chord", dialog.naca_desc_label.text())

        # Switch to 5-digit: 4-digit code is replaced with a 5-digit default
        dialog.naca5_radio.setChecked(True)
        self.assertEqual(dialog.naca_code_input.text(), "23012")
        self.assertEqual(dialog._selected_airfoil_data, "23012")
        self.assertIn("5-digit", dialog.naca_desc_label.text())

        # Back to 4-digit
        dialog.naca4_radio.setChecked(True)
        self.assertEqual(dialog.naca_code_input.text(), "2412")
        self.assertEqual(dialog._selected_airfoil_data, "2412")

    def test_airfoil_dialog_dat_import(self) -> None:
        """Verify .dat import populates coordinates table, canvas, and spec."""
        from PySide6.QtWidgets import QFileDialog
        from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog

        with tempfile.TemporaryDirectory() as tmp:
            dat_path = Path(tmp) / "custom.dat"
            dat_path.write_text(
                "My Custom Foil\n1.0   0.001\n0.5   0.05\n0.0   0.0\n0.5  -0.05\n1.0  -0.001\n",
                encoding="utf-8",
            )
            dialog = AirfoilDialog("2412")
            with mock.patch.object(
                QFileDialog,
                "getOpenFileName",
                return_value=(str(dat_path), ""),
            ):
                dialog._browse_dat_file()

            self.assertEqual(dialog.coord_table.rowCount(), 5)
            self.assertIn("custom.dat (5 points)", dialog.file_path_label.text())
            selected = dialog._selected_airfoil_data
            self.assertIsInstance(selected, dict)
            self.assertEqual(selected["type"], "coordinates")
            self.assertEqual(selected["name"], "My Custom Foil")
            self.assertEqual(len(selected["points"]), 5)
            self.assertEqual(len(dialog.canvas._points), 5)
            # normalized coordinates: leading edge at x = 0
            self.assertAlmostEqual(min(p[0] for p in dialog.canvas._points), 0.0)

    def test_airfoil_dialog_category_filter_and_apply_semantics(self) -> None:
        """Verify category filtering and apply/apply-all result semantics."""
        from setuav_studio.plugins.geometry.airfoil import PRESET_AIRFOILS
        from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog

        dialog = AirfoilDialog("2412")
        self.assertEqual(dialog.preset_list.count(), len(PRESET_AIRFOILS))

        dialog._filter_presets("Symmetric & Tail")
        self.assertGreater(dialog.preset_list.count(), 0)
        self.assertLess(dialog.preset_list.count(), len(PRESET_AIRFOILS))
        for i in range(dialog.preset_list.count()):
            name = dialog.preset_list.item(i).data(Qt.ItemDataRole.UserRole)
            self.assertEqual(PRESET_AIRFOILS[name]["category"], "Symmetric & Tail")
        # auto-selects first row -> canvas updated
        self.assertGreater(len(dialog.canvas._points), 0)

        dialog._filter_presets("All Categories")
        self.assertEqual(dialog.preset_list.count(), len(PRESET_AIRFOILS))

        # Apply semantics
        dialog._on_apply()
        _data, apply_all = dialog.get_selected_airfoil()
        self.assertFalse(apply_all)
        dialog._on_apply_all()
        _, apply_all = dialog.get_selected_airfoil()
        self.assertTrue(apply_all)

    # -------------------------------------------------------------------------
    # FuselageEditor coverage (Faz 3.11)
    # -------------------------------------------------------------------------

    def test_fuselage_editor_population(self) -> None:
        """Verify FuselageEditor loads general info, segments, sections, and transforms."""
        from setuav_studio.plugins.geometry.fuselage import FuselageEditor

        from setuav_studio.plugin_system import StudioAPI

        api = StudioAPI()
        comp = _build_fuselage_component()
        editor = FuselageEditor(api, comp)

        # General section
        self.assertEqual(editor.general_table.item(0, 1).text(), "Main Fuselage")
        self.assertEqual(editor.general_table.item(1, 1).text(), "org.setuav.core:fuselage")

        # Segments table: tags, method/parameterization combos
        self.assertEqual(editor.segments_table.rowCount(), 2)
        self.assertEqual(editor.segments_table.item(0, 0).text(), "nose")
        self.assertEqual(editor.segments_table.item(0, 1).text(), "3")
        self.assertEqual(editor.segments_table.cellWidget(0, 2).currentData(), "smooth")
        self.assertEqual(editor.segments_table.cellWidget(0, 3).currentData(), "centripetal")
        self.assertEqual(editor.segments_table.cellWidget(1, 2).currentData(), "ruled")

        # First segment auto-loaded -> sections populated
        self.assertEqual(editor._segment_index, 0)
        self.assertEqual(editor.sections_table.rowCount(), 3)
        self.assertEqual(editor.sections_table.item(0, 1).text(), "circle")
        self.assertIn("0", editor.sections_table.item(0, 2).text())

        # Section properties for circle: type + diameter
        self.assertEqual(editor.section_properties_table.rowCount(), 2)
        self.assertAlmostEqual(editor.section_properties_table.cellWidget(1, 1).value(), 80.0)

        # Transform spinboxes
        self.assertAlmostEqual(editor.transform_table.cellWidget(0, 0).value(), 0.0)
        self.assertAlmostEqual(editor.transform_table.cellWidget(1, 0).value(), 0.0)

        # Action states
        self.assertTrue(editor.add_segment_button.isEnabled())
        self.assertTrue(editor.delete_segment_button.isEnabled())  # 2 segments
        self.assertTrue(editor.add_section_button.isEnabled())
        self.assertTrue(editor.delete_section_button.isEnabled())  # 3 sections

    def test_fuselage_editor_segment_actions(self) -> None:
        """Verify add/duplicate/move/delete segment mutations."""
        from setuav_studio.plugins.geometry.fuselage import FuselageEditor

        from setuav_studio.plugin_system import StudioAPI

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
        from setuav_studio.plugins.geometry.fuselage import FuselageEditor

        from setuav_studio.plugin_system import StudioAPI

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
        from setuav_studio.plugins.geometry.fuselage import FuselageEditor

        from setuav_studio.plugin_system import StudioAPI

        api = StudioAPI()
        comp = _build_fuselage_component()
        editor = FuselageEditor(api, comp)

        # Profile type change circle -> ellipse
        editor._change_profile_type("ellipse")
        profile = comp["parameters"]["geometry"]["segments"][0]["sections"][0]["profile"]
        self.assertEqual(profile["type"], "ellipse")
        self.assertEqual(editor.section_properties_table.rowCount(), 3)  # type, width, height
        editor._on_property_spin_changed("width", 140.0)
        profile = comp["parameters"]["geometry"]["segments"][0]["sections"][0]["profile"]
        self.assertAlmostEqual(profile["width"], 140.0)
        self.assertIn("140", editor.sections_table.item(0, 3).text())
        self.assertIn("100", editor.sections_table.item(0, 3).text())

        # Transform edit through the spinbox -> position committed
        editor.transform_table.cellWidget(0, 0).setValue(25.0)
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
        self.assertAlmostEqual(editor.vertices_table.cellWidget(0, 0).value(), -50.0)
        editor._on_vertex_spin_changed(0, 0, 60.0)
        self.assertAlmostEqual(
            comp["parameters"]["geometry"]["segments"][1]["sections"][0]["profile"]["vertices"][0][
                "y"
            ],
            60.0,
        )

    def test_fuselage_editor_general_and_segment_edits(self) -> None:
        """Verify general name/mass edits and segment tag/loft choice edits."""
        from setuav_studio.plugins.geometry.fuselage import FuselageEditor

        from setuav_studio.plugin_system import StudioAPI

        api = StudioAPI()
        comp = _build_fuselage_component()
        editor = FuselageEditor(api, comp)

        # Name edit
        editor.general_table.item(0, 1).setText("Renamed Body")
        editor._update_general(0, 1)
        self.assertEqual(comp["name"], "Renamed Body")

        # Segment tag inline edit
        editor.segments_table.item(0, 0).setText("nose-renamed")
        editor._update_segment_cell(0, 0)
        self.assertEqual(comp["parameters"]["geometry"]["segments"][0]["tag"], "nose-renamed")

        # Segment loft choice edits
        editor._update_segment_choice(0, "method", "ruled")
        self.assertEqual(comp["parameters"]["geometry"]["segments"][0]["loft"]["method"], "ruled")
        self.assertEqual(
            comp["parameters"]["geometry"]["segments"][0]["loft"]["profile_correspondence"],
            "cardinal_quadrants",
        )
        editor._update_segment_choice(1, "parameterization", "chord_length")
        self.assertEqual(
            comp["parameters"]["geometry"]["segments"][1]["loft"]["parameterization"],
            "chord_length",
        )

    def test_3d_section_and_control_surface_selection_highlight(self) -> None:
        """Verify 3D section ring vertices highlight both bounding stations and control surfaces."""
        from setuav_studio.plugins.geometry.lifting_surface_geometry import (
            build_lifting_surface_geometry,
        )
        from setuav_studio.plugins.geometry.mesh import build_section_ring_vertices
        from setuav_studio.plugins.geometry.scene import build_project_geometry

        doc = open_project(TEST_PROJECT_PATH)
        providers = {"org.setuav.core:lifting-surface": build_lifting_surface_geometry}
        geom_data = build_project_geometry(doc, providers)

        # 1. Wing Section (Panel) Selection: highlights root station, tip station, and connecting rails
        panel_verts = build_section_ring_vertices(geom_data, "main-wing", 0, 0)
        self.assertGreater(len(panel_verts), 0)

        # 2. Control Surface Selection: highlights flap wireframe loops and hinge lines
        cs_verts = build_section_ring_vertices(geom_data, "main-wing", 1, 0)
        self.assertGreater(len(cs_verts), 0)

        # 3. Single Station / Airfoil Selection: highlights individual station ring and chord
        station_verts = build_section_ring_vertices(geom_data, "main-wing", 2, 0)
        self.assertGreater(len(station_verts), 0)


def _build_fuselage_component() -> dict:
    """Build a two-segment fuselage component for editor tests."""
    return {
        "id": "fuselage-1",
        "name": "Main Fuselage",
        "type": "org.setuav.core:fuselage",
        "parameters": {
            "mass": 500.0,
            "geometry": {
                "segments": [
                    {
                        "tag": "nose",
                        "loft": {"method": "smooth", "parameterization": "centripetal"},
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
                        "loft": {"method": "ruled", "parameterization": "uniform"},
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

    def test_fuselage_engine_helpers_and_metrics(self) -> None:
        """Verify fuselage engine calculation and data template helpers."""
        from setuav_studio.plugins.geometry.engine.fuselage_geometry import (
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

    def test_geometry_screenshot_transparent_background(self) -> None:
        """Verify screenshot transparent background action and capture parameter."""
        from setuav_studio.plugins.geometry.workspace import GeometryWorkspace
        from setuav_studio_sdk import StudioAPI

        api = StudioAPI()
        workspace = GeometryWorkspace(api)
        self.addCleanup(workspace.deleteLater)

        self.assertTrue(hasattr(workspace, "_action_transparent_bg"))
        self.assertTrue(workspace._action_transparent_bg.isCheckable())

        with (
            mock.patch.object(workspace.viewer, "capture_screenshot") as mock_capture,
            mock.patch(
                "setuav_studio.plugins.geometry.workspace.QMessageBox.warning"
            ) as mock_warning,
        ):
            mock_capture.return_value = None

            # 1. Capture with transparent bg unchecked
            workspace._action_transparent_bg.setChecked(False)
            workspace._take_screenshot(1920, 1080)
            mock_capture.assert_called_with(1920, 1080, transparent_background=False)

            # 2. Capture with transparent bg checked
            workspace._action_transparent_bg.setChecked(True)
            workspace._take_screenshot(1920, 1080)
            mock_capture.assert_called_with(1920, 1080, transparent_background=True)

        self.assertEqual(mock_warning.call_count, 2)


if __name__ == "__main__":
    unittest.main()
