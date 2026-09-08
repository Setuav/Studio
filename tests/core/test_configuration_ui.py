"""Unit tests for ConfigurationSelectorWidget and configuration dialogs."""

from __future__ import annotations

import unittest
from pathlib import Path

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.configuration.bar import ConfigurationSelectorWidget
from setuav_studio.ui.configuration.dialog import ConfigurationEditDialog
from setuav_studio.ui.project_explorer.panel import ProjectExplorerPanel
from tests._common import get_qapp


class TestConfigurationUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_configuration_selector_sync(self) -> None:
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

        selector = ConfigurationSelectorWidget(api)
        self.assertIsNotNone(selector.manager)

        # Dropdown should have Base + 2 configs + separator + 1 action = 5 items
        combo = selector.config_combo
        self.assertTrue(combo.count() >= 3)
        self.assertEqual(combo.itemText(0), "[Base Configuration]")
        self.assertEqual(combo.itemText(1), "[CRZ] Cruise")
        self.assertEqual(combo.itemText(2), "[VTOL] VTOL")

        # Base configuration is initially selected (index 0)
        self.assertEqual(combo.currentIndex(), 0)

        # Switch to Cruise via combo
        combo.setCurrentIndex(1)
        combo.activated.emit(1)
        self.assertEqual(selector.manager.get_active_id(), "cruise")

    def test_project_explorer_contains_configuration_selector(self) -> None:
        api = StudioAPI()
        panel = ProjectExplorerPanel(api)
        self.assertIsNotNone(panel.config_selector)
        self.assertIsInstance(panel.config_selector, ConfigurationSelectorWidget)

    def test_configuration_edit_dialog_validation(self) -> None:
        dlg = ConfigurationEditDialog(None, {"name": "High Speed", "tag": "SPD"})
        data = dlg.get_data()
        self.assertEqual(data["name"], "High Speed")
        self.assertEqual(data["tag"], "SPD")
        self.assertNotIn("color", data)


if __name__ == "__main__":
    unittest.main()
