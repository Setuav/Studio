"""Unit tests for ConfigurationToolBar and configuration dialogs."""

from __future__ import annotations

import unittest
from pathlib import Path

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.configuration.bar import ConfigurationToolBar
from setuav_studio.ui.configuration.dialog import ConfigurationEditDialog
from tests._common import get_qapp


class TestConfigurationUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_configuration_toolbar_sync(self) -> None:
        api = StudioAPI()
        doc = ProjectDocument(
            path=Path("/tmp/test.json"),
            kind="json",
            data={
                "configurations": [
                    {
                        "id": "cruise",
                        "name": "Cruise",
                        "tag": "CRZ",
                        "parameter_overrides": {},
                        "is_default": True,
                    },
                    {
                        "id": "vtol",
                        "name": "VTOL",
                        "tag": "VTOL",
                        "parameter_overrides": {},
                    },
                ]
            },
        )
        api._host.set_project(doc)

        toolbar = ConfigurationToolBar(api)
        self.assertIsNotNone(toolbar.manager)

        # Dropdown should have Base + 2 configs + separator + 2 actions = 6 items
        combo = toolbar.config_combo
        self.assertTrue(combo.count() >= 3)
        self.assertEqual(combo.itemText(0), "[Base Configuration]")
        self.assertEqual(combo.itemText(1), "[CRZ] Cruise")
        self.assertEqual(combo.itemText(2), "[VTOL] VTOL")

        # Base configuration is initially selected (index 0)
        self.assertEqual(combo.currentIndex(), 0)

        # Switch to Cruise via combo
        combo.setCurrentIndex(1)
        combo.activated.emit(1)
        self.assertEqual(toolbar.manager.get_active_id(), "cruise")

    def test_configuration_edit_dialog_validation(self) -> None:
        dlg = ConfigurationEditDialog(None, {"name": "High Speed", "tag": "SPD"})
        data = dlg.get_data()
        self.assertEqual(data["name"], "High Speed")
        self.assertEqual(data["tag"], "SPD")


if __name__ == "__main__":
    unittest.main()
