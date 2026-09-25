"""Unit and integration tests for airfoil definitions, generators, dat files, and dialog."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import Qt

from plugins.geometry.editors.lifting_surface import AirfoilDialog
from plugins.geometry.engine.airfoil import PRESET_AIRFOILS
from tests._common import get_qapp


class AirfoilTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_airfoil_generators_and_dat_parser(self) -> None:
        from plugins.geometry.engine.airfoil import (
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

    def test_airfoil_dialog_initial_selection(self) -> None:
        """Verify initial selection resolves preset names, NACA codes, and dict specs."""

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
        from plugins.geometry.engine.airfoil import PRESET_AIRFOILS

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
