"""Tests for geometry plugin settings pages and persistence."""

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import patch

from PySide6.QtWidgets import QCheckBox, QComboBox

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

    def test_editor_page_loads_and_applies_all_values(self) -> None:
        _FakeSettings.values = {
            geometry_settings._EDITOR_AUTO_FIT_KEY: False,
            geometry_settings._EDITOR_GRID_KEY: False,
            geometry_settings._EDITOR_LOFT_METHOD_KEY: "ruled",
        }
        page = geometry_settings.create_editor_settings_page()
        self.addCleanup(page.deleteLater)

        auto_fit = page.findChild(QCheckBox, "autoFitSections")
        show_grid = page.findChild(QCheckBox, "showSectionGrid")
        loft_method = page.findChild(QComboBox, "defaultLoftMethod")
        assert auto_fit and show_grid and loft_method
        self.assertFalse(auto_fit.isChecked())
        self.assertFalse(show_grid.isChecked())
        self.assertEqual(loft_method.currentData(), "ruled")

        auto_fit.setChecked(True)
        show_grid.setChecked(True)
        loft_method.setCurrentIndex(1)  # Smooth
        geometry_settings.apply_editor_settings(page)
        self.assertEqual(_FakeSettings.values[geometry_settings._EDITOR_AUTO_FIT_KEY], True)
        self.assertEqual(_FakeSettings.values[geometry_settings._EDITOR_GRID_KEY], True)
        self.assertEqual(
            _FakeSettings.values[geometry_settings._EDITOR_LOFT_METHOD_KEY],
            loft_method.currentData(),
        )

    def test_setting_helpers(self) -> None:
        self.assertEqual(geometry_settings.editor_setting("missing", "fallback"), "fallback")


if __name__ == "__main__":
    unittest.main()
