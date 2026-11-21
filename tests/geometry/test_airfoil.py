"""Unit and integration tests for airfoil definitions, generators, dat files, and dialog."""

from __future__ import annotations

import math
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from PySide6.QtCore import Qt

from plugins.geometry.editors.lifting_surface import AirfoilDialog
from plugins.geometry.engine.airfoil import (
    PRESET_AIRFOILS,
    _naca5_mean_line,
    airfoil_label,
    apply_airfoil_shaping,
    biconvex,
    compute_airfoil_metrics,
    naca4,
    naca5,
    parse_airfoil_dat,
    preset_airfoil_spec,
    sample_airfoil_points,
)
from plugins.geometry.models import LiftingSurfaceProfileModel
from tests._common import get_qapp

_CUSTOM_COORDINATES = {
    "type": "coordinates",
    "name": "My Custom Foil",
    "points": [[2.0, 0.0], [1.0, 0.1], [0.0, 0.0], [1.0, -0.1], [2.0, 0.0]],
}


def _thin_airfoil_coefficients(
    mean_line: Callable[[float], tuple[float, float]], stations: int = 4000
) -> tuple[float, float]:
    """Return the thin-airfoil ideal lift coefficient and quarter-chord moment of a mean line."""
    lift = moment = 0.0
    step = math.pi / stations
    for index in range(stations):
        theta = (index + 0.5) * step
        _, slope = mean_line(0.5 * (1.0 - math.cos(theta)))
        lift += 2.0 * slope * math.cos(theta) * step
        moment += 0.5 * slope * (math.cos(2.0 * theta) - math.cos(theta)) * step
    return lift, moment


class AirfoilTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_airfoil_generators_and_dat_parser(self) -> None:
        # NACA 4
        pts_4 = naca4("2412")
        m_4 = compute_airfoil_metrics(pts_4)
        self.assertAlmostEqual(m_4.max_thickness, 0.12, places=2)
        self.assertAlmostEqual(m_4.max_camber, 0.02, places=2)

        # NACA 5
        pts_5 = naca5("23012")
        m_5 = compute_airfoil_metrics(pts_5)
        self.assertAlmostEqual(m_5.max_thickness, 0.12, places=2)
        self.assertAlmostEqual(m_5.max_camber, 0.018, places=2)

        # Biconvex
        pts_bi = biconvex(0.08)
        m_bi = compute_airfoil_metrics(pts_bi)
        self.assertAlmostEqual(m_bi.max_thickness, 0.08, places=2)
        self.assertEqual(m_bi.max_camber, 0.0)

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

        with self.assertRaisesRegex(ValueError, "empty"):
            parse_airfoil_dat("")
        with self.assertRaisesRegex(ValueError, "fewer than 3"):
            parse_airfoil_dat("Broken\n1.0 0.0\n0.0 0.0\n")

        # Preset spec
        self.assertIn("Selig S1223", PRESET_AIRFOILS)
        pts_selig = sample_airfoil_points(preset_airfoil_spec("Selig S1223"))
        m_selig = compute_airfoil_metrics(pts_selig)
        self.assertGreater(m_selig.max_camber, 0.05)

        with self.assertRaisesRegex(ValueError, "at least 3 coordinate points, got 2"):
            compute_airfoil_metrics([(1.0, 0.0), (0.0, 0.0)])

    def test_naca4_cambered_code_requires_camber_position(self) -> None:
        with self.assertRaisesRegex(ValueError, "'2012' has 2% camber but camber-position digit 0"):
            naca4("2012")
        symmetric = compute_airfoil_metrics(naca4("0012"))
        self.assertEqual(symmetric.max_camber, 0.0)
        self.assertIsNone(symmetric.camber_x)
        self.assertAlmostEqual(symmetric.thickness_x, 0.30, delta=0.02)
        self.assertAlmostEqual(
            compute_airfoil_metrics(naca4("2412")).camber_x or 0.0, 0.4, delta=0.02
        )

    def test_naca5_design_lift_digit_scales_mean_line(self) -> None:
        standard = _naca5_mean_line("23012")
        doubled = _naca5_mean_line("43012")
        for x in (0.05, 0.15, 0.3, 0.6, 0.9):
            yc, slope = standard(x)
            doubled_yc, doubled_slope = doubled(x)
            self.assertAlmostEqual(doubled_yc, 2.0 * yc, places=12)
            self.assertAlmostEqual(doubled_slope, 2.0 * slope, places=12)

        # 23012: design CL 0.3, maximum camber of 1.84% at 15% chord.
        self.assertAlmostEqual(standard(0.15)[1], 0.0, places=3)
        self.assertAlmostEqual(standard(0.15)[0], 0.0184, places=4)
        self.assertAlmostEqual(_thin_airfoil_coefficients(standard)[0], 0.3, delta=0.001)
        self.assertAlmostEqual(_thin_airfoil_coefficients(doubled)[0], 0.6, delta=0.002)

        camber_23012 = compute_airfoil_metrics(naca5("23012")).max_camber
        camber_43012 = compute_airfoil_metrics(naca5("43012")).max_camber
        self.assertAlmostEqual(camber_43012, 2.0 * camber_23012, places=4)

    def test_naca5_reflexed_mean_line(self) -> None:
        reflexed = _naca5_mean_line("23112")
        standard = _naca5_mean_line("23012")
        self.assertAlmostEqual(reflexed(0.0)[0], 0.0, places=12)
        self.assertAlmostEqual(reflexed(1.0)[0], 0.0, places=12)

        # Aft of the camber peak the standard line is straight, the reflexed line curves up.
        aft = (0.4, 0.6, 0.8, 0.9, 1.0)
        reflexed_slopes = [reflexed(x)[1] for x in aft]
        self.assertEqual(reflexed_slopes, sorted(set(reflexed_slopes)))
        self.assertEqual(len({round(standard(x)[1], 12) for x in aft}), 1)
        self.assertGreater(reflexed(1.0)[1], 0.5 * standard(1.0)[1])

        # The reflex cancels the quarter-chord pitching moment at the same design CL.
        reflexed_cl, reflexed_cm = _thin_airfoil_coefficients(reflexed)
        _, standard_cm = _thin_airfoil_coefficients(standard)
        self.assertAlmostEqual(reflexed_cl, 0.3, delta=0.005)
        self.assertLess(abs(reflexed_cm), 0.002)
        self.assertLess(standard_cm, -0.01)

        self.assertNotEqual(naca5("23112"), naca5("23012"))
        with self.assertRaisesRegex(ValueError, "reflex digit 2"):
            naca5("23212")
        with self.assertRaisesRegex(ValueError, "reflexed mean lines expect 2-5"):
            naca5("21112")

    def test_generated_airfoils_keep_their_open_trailing_edge(self) -> None:
        """NACA loops run upper TE -> LE -> lower TE like every other airfoil source."""
        for code in ("0012", "2412", "23012"):
            with self.subTest(code=code):
                points = sample_airfoil_points(code)
                self.assertAlmostEqual(points[0][0], points[-1][0], delta=0.01)
                self.assertGreater(points[0][1], points[-1][1])
                expected_gap = 0.021 * int(code[-2:]) / 100.0
                self.assertAlmostEqual(
                    compute_airfoil_metrics(points).te_gap, expected_gap, delta=0.0005
                )

    def test_trailing_edge_thickness_adds_to_the_airfoil_own_gap(self) -> None:
        shaped = apply_airfoil_shaping(sample_airfoil_points("0012"), te_thickness=0.01)
        self.assertAlmostEqual(compute_airfoil_metrics(shaped).te_gap, 0.01252, delta=0.0003)

    def test_split_surfaces_end_at_their_own_trailing_edge(self) -> None:
        from plugins.geometry.engine.lifting_surface_math import split_airfoil_upper_lower

        upper, lower = split_airfoil_upper_lower(sample_airfoil_points("0012"))
        self.assertAlmostEqual(upper[-1][1] - lower[-1][1], 0.00252, delta=0.0001)

    def test_canonical_airfoil_specs_sample_and_label(self) -> None:
        self.assertEqual(sample_airfoil_points("2412"), naca4("2412"))
        self.assertEqual(sample_airfoil_points("23012"), naca5("23012"))
        self.assertEqual(airfoil_label("2412"), "NACA 2412")
        self.assertEqual(airfoil_label("4418"), "NACA 4418")
        self.assertEqual(airfoil_label("23012"), "NACA 23012")

        points = sample_airfoil_points(_CUSTOM_COORDINATES)
        self.assertEqual(points[0], (1.0, 0.0))
        self.assertEqual(points[2], (0.0, 0.0))
        self.assertEqual(points[1], (0.5, 0.05))
        self.assertEqual(airfoil_label(_CUSTOM_COORDINATES), "My Custom Foil")

        self.assertEqual(preset_airfoil_spec("NACA 23012"), "23012")
        clark_y = preset_airfoil_spec("Clark-Y")
        assert isinstance(clark_y, dict)
        self.assertEqual(clark_y["type"], "coordinates")
        self.assertEqual(airfoil_label(clark_y), "Clark-Y")
        self.assertEqual(len(sample_airfoil_points(clark_y)), len(clark_y["points"]))

    def test_non_canonical_airfoil_specs_raise(self) -> None:
        with self.assertRaises(ValueError) as raised:
            sample_airfoil_points("NACA 2412")
        self.assertEqual(
            str(raised.exception),
            "Airfoil spec 'NACA 2412' is not a NACA 4- or 5-digit code such as '2412' or '23012'",
        )
        invalid_specs: list[object] = [
            "naca2412",
            " 2412",
            "241",
            "Clark-Y",
            "clarky.dat",
            "20012",
            "2012",
            "23212",
            "21112",
            2412,
            None,
            {"type": "naca", "code": "2412"},
            {"type": "file", "path": "clarky.dat"},
            {"code": "0012"},
            {"type": "coordinates", "points": [[1.0, 0.0], [0.0, 0.0], [1.0, -0.1]]},
            {"type": "coordinates", "name": "Short", "points": [[1.0, 0.0], [0.0, 0.0]]},
            {"type": "coordinates", "name": "Bad", "points": [[1.0, 0.0, 0.0]] * 3},
        ]
        for spec in invalid_specs:
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    sample_airfoil_points(spec)
                with self.assertRaises(ValueError):
                    airfoil_label(spec)
        with self.assertRaisesRegex(ValueError, "Missing airfoil spec"):
            sample_airfoil_points(None)

    def test_profile_model_reads_canonical_twist_and_airfoil_label(self) -> None:
        profile = LiftingSurfaceProfileModel(
            {"chord": 200.0, "rotation": {"x": 4.0, "y": -2.0, "z": 0.0}, "airfoil": "0012"}
        )
        self.assertEqual(profile.twist, -2.0)
        self.assertEqual(profile.airfoil, "NACA 0012")
        self.assertEqual(LiftingSurfaceProfileModel({"airfoil": "4418"}).twist, 0.0)
        self.assertEqual(
            LiftingSurfaceProfileModel({"airfoil": _CUSTOM_COORDINATES}).airfoil,
            "My Custom Foil",
        )

    def test_airfoil_dialog_initial_selection(self) -> None:
        """Verify initial selection resolves presets, NACA codes, and coordinate specs."""

        # NACA code of a preset -> preset row selected on library tab
        dlg = AirfoilDialog("0012")
        self.assertEqual(dlg.tabs.currentIndex(), 0)
        self.assertEqual(dlg._selected_airfoil_data, "0012")
        current = dlg.preset_list.currentItem()
        self.assertEqual(str(current.data(Qt.ItemDataRole.UserRole)), "NACA 0012")

        # Coordinates of a preset -> preset row selected on library tab
        dlg_preset = AirfoilDialog(preset_airfoil_spec("Clark-Y"))
        self.assertEqual(dlg_preset.tabs.currentIndex(), 0)
        current = dlg_preset.preset_list.currentItem()
        self.assertEqual(str(current.data(Qt.ItemDataRole.UserRole)), "Clark-Y")

        # 4-digit code without a preset -> NACA generator tab
        dlg_code = AirfoilDialog("4418")
        self.assertEqual(dlg_code.tabs.currentIndex(), 1)
        self.assertTrue(dlg_code.naca4_radio.isChecked())
        self.assertEqual(dlg_code.naca_code_input.text(), "4418")
        self.assertEqual(dlg_code._selected_airfoil_data, "4418")

        # 5-digit code without a preset -> NACA generator tab in 5-digit mode
        dlg_code5 = AirfoilDialog("23015")
        self.assertEqual(dlg_code5.tabs.currentIndex(), 1)
        self.assertTrue(dlg_code5.naca5_radio.isChecked())
        self.assertEqual(dlg_code5.naca_code_input.text(), "23015")
        self.assertEqual(dlg_code5._selected_airfoil_data, "23015")

        # Custom coordinates -> import tab, spec kept as-is
        dlg_custom = AirfoilDialog(_CUSTOM_COORDINATES)
        self.assertEqual(dlg_custom.tabs.currentIndex(), 2)
        self.assertEqual(dlg_custom._selected_airfoil_data, _CUSTOM_COORDINATES)
        self.assertEqual(dlg_custom.coord_table.rowCount(), 5)
        self.assertIn("My Custom Foil (5 points)", dlg_custom.file_path_label.text())

        with self.assertRaises(ValueError):
            AirfoilDialog("NACA 0012")

    def test_airfoil_dialog_preset_selection_and_metrics(self) -> None:
        """Verify preset selection updates canvas, metrics, and selected spec."""
        from plugins.geometry.engine.airfoil import PRESET_AIRFOILS

        dialog = AirfoilDialog("2412")
        # naca-type preset selected -> spec is the code string
        self.assertEqual(dialog._selected_airfoil_data, "2412")
        self.assertIn("12.0%", dialog.max_thick_label.text())
        self.assertEqual(len(dialog.canvas._points), 129)  # 65 upper + 64 lower

        # coordinates-type preset (file-backed) -> dict spec with points
        clark_row = next(
            i
            for i in range(dialog.preset_list.count())
            if dialog.preset_list.item(i).data(Qt.ItemDataRole.UserRole) == "Clark-Y"
        )
        dialog.preset_list.setCurrentRow(clark_row)
        selected = dialog._selected_airfoil_data
        self.assertIsInstance(selected, dict)
        assert isinstance(selected, dict)
        self.assertEqual(selected["type"], "coordinates")
        self.assertEqual(selected["name"], "Clark-Y")
        self.assertGreater(len(selected["points"]), 0)
        self.assertEqual(len(dialog.canvas._points), len(selected["points"]))
        self.assertIsNotNone(dialog.canvas._metrics)
        self.assertIn("Points:", dialog.pts_count_label.text())

        # metrics reflect the new airfoil
        self.assertGreater(len(PRESET_AIRFOILS), 0)

    def test_airfoil_dialog_naca_generation(self) -> None:
        """Verify 4/5-digit NACA generation, radio swapping, and desc label."""

        dialog = AirfoilDialog("2418")
        self.assertEqual(dialog.tabs.currentIndex(), 1)
        self.assertIn("18% thickness", dialog.naca_desc_label.text())

        # Incomplete codes keep the last valid selection and explain the expected format
        dialog.naca_code_input.setText("44")
        self.assertEqual(dialog._selected_airfoil_data, "2418")
        self.assertIn("four digits", dialog.naca_desc_label.text())

        dialog.naca_code_input.setText("4415")
        self.assertEqual(dialog._selected_airfoil_data, "4415")
        self.assertEqual(len(dialog.canvas._points), 129)
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
            assert isinstance(selected, dict)
            self.assertEqual(selected["type"], "coordinates")
            self.assertEqual(selected["name"], "My Custom Foil")
            self.assertEqual(len(selected["points"]), 5)
            self.assertEqual(len(dialog.canvas._points), 5)
            # normalized coordinates: leading edge at x = 0
            self.assertAlmostEqual(min(p[0] for p in dialog.canvas._points), 0.0)

            empty_path = Path(tmp) / "empty.dat"
            empty_path.write_text("", encoding="utf-8")
            with (
                mock.patch.object(
                    QFileDialog,
                    "getOpenFileName",
                    return_value=(str(empty_path), ""),
                ),
                mock.patch(
                    "plugins.geometry.editors.lifting_surface.airfoil_dialog.QMessageBox.critical"
                ) as critical,
            ):
                dialog._browse_dat_file()
            critical.assert_called_once()
            self.assertIs(dialog._selected_airfoil_data, selected)

    def test_airfoil_dialog_category_filter_and_apply_semantics(self) -> None:
        """Verify category filtering and apply/apply-all result semantics."""
        from plugins.geometry.engine.airfoil import PRESET_AIRFOILS

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


if __name__ == "__main__":
    unittest.main()
