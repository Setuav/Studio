"""Tests for application settings persistence and dialog extension pages."""

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem, QWidget

from setuav_studio.api import SettingsPageContribution
from setuav_studio.ui.settings.settings_pages import SettingsDialog, StudioSettings, _as_bool
from tests._common import get_qapp


class _FakeSettings:
    values: ClassVar[dict[str, object]] = {}

    def value(self, key: str, fallback: object = None) -> object:
        return self.values.get(key, fallback)

    def setValue(self, key: str, value: object) -> None:
        self.values[key] = value


class CoreSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        _FakeSettings.values = {}

    def test_settings_load_save_and_normalize_values(self) -> None:
        _FakeSettings.values = {
            "general/reopen_last_project": "yes",
            "general/recent_project_limit": "14",
            "propulsion/pythrust_data_dir": "/data",
            "general/validation_strictness": "warn",
            "appearance/theme_mode": "NORD",
        }
        with patch("PySide6.QtCore.QSettings", _FakeSettings):
            values = StudioSettings.load()
            values.save()

        self.assertEqual(
            values,
            StudioSettings(True, 14, "/data", "warn", "nord"),
        )
        self.assertEqual(_FakeSettings.values["appearance/theme_mode"], "nord")
        self.assertTrue(_as_bool(True))
        self.assertTrue(_as_bool("1"))
        self.assertFalse(_as_bool("off"))

    def test_settings_load_rejects_unknown_modes(self) -> None:
        _FakeSettings.values = {
            "general/validation_strictness": "invalid",
            "appearance/theme_mode": "invalid",
        }
        with patch("PySide6.QtCore.QSettings", _FakeSettings):
            values = StudioSettings.load()

        self.assertEqual(values.validation_strictness, "strict")
        self.assertEqual(values.theme_mode, "blender")

    def test_dialog_round_trips_built_in_values(self) -> None:
        dialog = SettingsDialog(StudioSettings(True, 12, " /pythrust ", "off", "github_light"))
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.category_tree.topLevelItemCount(), 4)
        self.assertEqual(dialog.page_stack.currentIndex(), 0)
        self.assertEqual(
            dialog.values(),
            StudioSettings(True, 12, "/pythrust", "off", "github_light"),
        )

        invalid_values = StudioSettings(validation_strictness="invalid", theme_mode="invalid")
        invalid_dialog = SettingsDialog(invalid_values)
        self.addCleanup(invalid_dialog.deleteLater)
        self.assertEqual(invalid_dialog.validation_strictness_combo.currentData(), "strict")
        self.assertEqual(invalid_dialog.theme_combo.currentData(), "dark")

    def test_plugin_pages_are_grouped_sorted_and_applied_safely(self) -> None:
        applied: list[QWidget] = []

        def fail_factory() -> QWidget:
            raise RuntimeError("factory failed")

        def fail_apply(_page: QWidget) -> None:
            raise RuntimeError("apply failed")

        pages = (
            SettingsPageContribution("z", "Zulu", QWidget, order=20, group="Geometry"),
            SettingsPageContribution(
                "a",
                "Alpha",
                QWidget,
                order=10,
                apply=applied.append,
                group="Geometry",
            ),
            SettingsPageContribution("plain", "Plain", QWidget, order=30),
            SettingsPageContribution("bad", "Bad", fail_factory, order=40, apply=fail_apply),
            SettingsPageContribution("wrong", "Wrong", lambda: object(), order=50),
        )
        with self.assertLogs("setuav_studio.ui.settings.settings_pages", level="ERROR"):
            dialog = SettingsDialog(StudioSettings(), pages=pages)
            dialog.apply_plugin_pages()
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(
            [item[0].id for item in dialog._plugin_pages], ["a", "z", "plain", "bad", "wrong"]
        )
        self.assertEqual(len(applied), 1)
        self.assertIn("Geometry", dialog._group_items)
        self.assertEqual(dialog._group_items["Geometry"].childCount(), 2)

    def test_category_change_ignores_missing_or_invalid_page_indexes(self) -> None:
        dialog = SettingsDialog(StudioSettings())
        self.addCleanup(dialog.deleteLater)

        dialog._on_category_changed(None, None)
        item = QTreeWidgetItem(["Invalid"])
        dialog._on_category_changed(item, None)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, -1)
        dialog._on_category_changed(item, None)
        self.assertEqual(dialog.page_stack.currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
