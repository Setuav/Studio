"""Tests for geometry plugin settings pages and persistence."""

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import patch

from PySide6.QtWidgets import QCheckBox, QComboBox, QWidget

from plugins.geometry import settings as geometry_settings
from tests._common import get_qapp


class _FakeSettings:
    values: ClassVar[dict[str, object]] = {}

    def value(self, key: str, fallback: object = None) -> object:
        return self.values.get(key, fallback)

    def setValue(self, key: str, value: object) -> None:
        self.values[key] = value


class GeometrySettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        _FakeSettings.values = {}
        self.settings_patch = patch.object(geometry_settings, "QSettings", _FakeSettings)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)

    def test_boolean_and_combo_normalization(self) -> None:
        self.assertFalse(geometry_settings._as_bool(None, False))
        self.assertTrue(geometry_settings._as_bool(True, False))
        self.assertTrue(geometry_settings._as_bool("ON", False))
        self.assertFalse(geometry_settings._as_bool("off", True))

        combo = QComboBox()
        self.addCleanup(combo.deleteLater)
        combo.addItem("First", "first")
        combo.addItem("Second", "second")
        _FakeSettings.values["combo"] = "SECOND"
        geometry_settings._combo_value(combo, "combo", "first")
        self.assertEqual(combo.currentData(), "second")
        _FakeSettings.values["combo"] = "missing"
        geometry_settings._combo_value(combo, "combo", "first")
        self.assertEqual(combo.currentIndex(), 0)

    def test_viewer_page_loads_and_applies_all_values(self) -> None:
        _FakeSettings.values = {
            geometry_settings._VIEWER_PROJECTION_KEY: "perspective",
            geometry_settings._VIEWER_PALETTE_KEY: "invalid",
            geometry_settings._VIEWER_GRID_KEY: "false",
            geometry_settings._VIEWER_SOLID_KEY: False,
            geometry_settings._VIEWER_WIRE_KEY: "yes",
            geometry_settings._VIEWER_SCREENSHOT_TRANSPARENT_KEY: True,
        }
        page = geometry_settings.create_viewer_settings_page()
        self.addCleanup(page.deleteLater)

        projection = page.findChild(QComboBox, "defaultProjection")
        palette = page.findChild(QComboBox, "defaultPalette")
        show_grid = page.findChild(QCheckBox, "showGrid")
        show_solid = page.findChild(QCheckBox, "showSolid")
        show_wire = page.findChild(QCheckBox, "showWireframe")
        trans_screen = page.findChild(QCheckBox, "transparentScreenshot")
        assert projection and palette and show_grid and show_solid and show_wire and trans_screen
        self.assertEqual(projection.currentData(), "perspective")
        self.assertEqual(palette.currentIndex(), 0)
        self.assertFalse(show_grid.isChecked())
        self.assertFalse(show_solid.isChecked())
        self.assertTrue(show_wire.isChecked())
        self.assertTrue(trans_screen.isChecked())

        projection.setCurrentIndex(0)
        palette.setCurrentIndex(min(1, palette.count() - 1))
        show_grid.setChecked(True)
        show_solid.setChecked(True)
        show_wire.setChecked(False)
        trans_screen.setChecked(False)
        with patch.object(geometry_settings, "set_active_palette") as set_palette:
            geometry_settings.apply_viewer_settings(page)
        self.assertEqual(
            _FakeSettings.values[geometry_settings._VIEWER_PROJECTION_KEY], "orthographic"
        )
        self.assertEqual(_FakeSettings.values[geometry_settings._VIEWER_GRID_KEY], True)
        self.assertEqual(
            _FakeSettings.values[geometry_settings._VIEWER_SCREENSHOT_TRANSPARENT_KEY], False
        )
        set_palette.assert_called_once_with(str(palette.currentData()))

    def test_editor_page_loads_and_applies_all_values(self) -> None:
        _FakeSettings.values = {
            geometry_settings._EDITOR_AUTO_FIT_KEY: "no",
            geometry_settings._EDITOR_GRID_KEY: "true",
            geometry_settings._EDITOR_LOFT_METHOD_KEY: "ruled",
        }
        page = geometry_settings.create_editor_settings_page()
        self.addCleanup(page.deleteLater)

        auto_fit = page.findChild(QCheckBox, "autoFitSections")
        show_grid = page.findChild(QCheckBox, "showSectionGrid")
        loft = page.findChild(QComboBox, "defaultLoftMethod")
        assert auto_fit and show_grid and loft
        self.assertFalse(auto_fit.isChecked())
        self.assertTrue(show_grid.isChecked())
        self.assertEqual(loft.currentData(), "ruled")

        auto_fit.setChecked(True)
        show_grid.setChecked(False)
        loft.setCurrentIndex(0)
        geometry_settings.apply_editor_settings(page)
        self.assertEqual(_FakeSettings.values[geometry_settings._EDITOR_AUTO_FIT_KEY], True)
        self.assertEqual(_FakeSettings.values[geometry_settings._EDITOR_GRID_KEY], False)
        self.assertEqual(_FakeSettings.values[geometry_settings._EDITOR_LOFT_METHOD_KEY], "auto")

    def test_apply_functions_accept_pages_without_expected_controls(self) -> None:
        page = QWidget()
        self.addCleanup(page.deleteLater)

        geometry_settings.apply_viewer_settings(page)
        geometry_settings.apply_editor_settings(page)
        self.assertEqual(_FakeSettings.values, {})

    def test_setting_accessors_forward_fallbacks(self) -> None:
        _FakeSettings.values["viewer"] = 42
        self.assertEqual(geometry_settings.viewer_setting("viewer", 0), 42)
        self.assertEqual(geometry_settings.editor_setting("missing", "fallback"), "fallback")


if __name__ == "__main__":
    unittest.main()
