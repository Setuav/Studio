"""Unit tests for Multi-Workspace and Tool Contribution systems."""

from __future__ import annotations

import unittest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    ToolContribution,
    WorkspaceContribution,
)
from setuav_studio.shell import MainWindow


class TestWorkspacesAndTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_multi_workspace_and_dock_visibility(self) -> None:
        api = StudioAPI()
        win = MainWindow(api)

        # Register Design workspace
        api.add_workspace(
            WorkspaceContribution(
                id="studio.viewer.opengl",
                title="3D Viewer",
                factory=lambda: QLabel("Viewer Canvas"),
                order=0,
            )
        )

        # Register custom Workspace B
        api.add_workspace(
            WorkspaceContribution(
                id="studio.custom.workspace",
                title="Custom Workspace",
                factory=lambda: QLabel("Custom Canvas"),
                order=10,
            )
        )

        # Register workspace-specific dock
        api.add_panel(
            PanelContribution(
                id="custom.panel",
                title="Custom Panel",
                factory=lambda: QLabel("Custom Dock Widget"),
                workspace_id="studio.custom.workspace",
            )
        )

        # Design is active -> Custom Panel is hidden
        api.switch_workspace("studio.viewer.opengl")
        custom_dock = win._panels["custom.panel"][1]
        self.assertTrue(custom_dock.isHidden())

        # Switch to Custom Workspace -> Custom Panel is shown
        api.switch_workspace("studio.custom.workspace")
        self.assertFalse(custom_dock.isHidden())

    def test_tool_registration_in_tools_menu(self) -> None:
        api = StudioAPI()
        win = MainWindow(api)

        called = []

        # Register tool under "Propulsion" group
        api.register_tool(
            ToolContribution(
                title="Sample Tool",
                group="Propulsion",
                callback=lambda: called.append(True),
            )
        )

        # Find Tools menu in menuBar
        tools_action = next(a for a in win.menuBar().actions() if "tools" in a.text().lower())
        self.assertIsNotNone(tools_action)
        tools_menu = tools_action.menu()

        # Find Propulsion submenu
        prop_action = next(a for a in tools_menu.actions() if "propulsion" in a.text().lower())
        self.assertIsNotNone(prop_action)
        prop_menu = prop_action.menu()

        # Find and trigger the Sample Tool action
        sample_action = next(a for a in prop_menu.actions() if "sample tool" in a.text().lower())
        sample_action.trigger()
        self.assertEqual(called, [True])


if __name__ == "__main__":
    unittest.main()
