"""Contract tests that do not import the Setuav Studio application."""

import sys
import unittest
from pathlib import Path
from typing import Protocol

import setuav_studio_sdk as sdk
from PySide6.QtCore import Qt


class SDKContractTests(unittest.TestCase):
    def test_import_does_not_load_application_package(self) -> None:
        self.assertNotIn("setuav_studio", sys.modules)
        self.assertNotIn("setuav_studio.project", sys.modules)

    def test_project_document_is_a_structural_contract(self) -> None:
        self.assertTrue(issubclass(sdk.ProjectDocument, Protocol))
        self.assertEqual(sdk.ProjectDocument.__annotations__["path"], Path)

    def test_workspace_scope_matching(self) -> None:
        contribution = sdk.PanelContribution(
            id="com.example.panel",
            title="Panel",
            factory=lambda: None,  # type: ignore[return-value]
            workspace_id=("design", "analysis"),
        )
        self.assertTrue(contribution.is_in_workspace("design"))
        self.assertFalse(contribution.is_in_workspace("settings"))

    def test_toolbar_contribution_requires_one_action_form(self) -> None:
        with self.assertRaises(ValueError):
            sdk.ToolbarContribution(id="invalid", title="Invalid")

    def test_panel_uses_left_dock_by_default(self) -> None:
        contribution = sdk.PanelContribution(
            id="com.example.panel",
            title="Panel",
            factory=lambda: None,  # type: ignore[return-value]
        )
        self.assertEqual(contribution.area, Qt.DockWidgetArea.LeftDockWidgetArea)


if __name__ == "__main__":
    unittest.main()
