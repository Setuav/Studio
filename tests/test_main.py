import unittest

from PySide6.QtWidgets import QDockWidget, QWidget

from setuav_studio.__main__ import _parse_arguments
from setuav_studio.plugin_system import PanelContribution, StudioAPI, WorkspaceContribution
from setuav_studio.shell import MainWindow

from tests._common import get_qapp

_app = get_qapp()


class MainTests(unittest.TestCase):
    def test_accepts_optional_project_path(self) -> None:
        arguments = _parse_arguments(["example/project.json"])

        self.assertEqual(arguments.project, "example/project.json")

    def test_project_path_is_optional(self) -> None:
        arguments = _parse_arguments([])

        self.assertIsNone(arguments.project)

    def test_workspace_and_panel_contributions(self) -> None:
        api = StudioAPI()
        window = MainWindow(api)
        api.add_workspace(
            WorkspaceContribution(
                id="test.workspace",
                title="Test Workspace",
                factory=QWidget,
            )
        )
        self.assertIn("test.workspace", window._workspaces)

        api.add_panel(
            PanelContribution(
                id="test.panel",
                title="Test Panel",
                factory=QWidget,
            )
        )
        dock = window.findChild(QDockWidget, "test.panel")
        self.assertIsNotNone(dock)
        self.assertEqual(dock.windowTitle(), "Test Panel")
        self.assertIn(dock.toggleViewAction(), window._view_menu.actions())


if __name__ == "__main__":
    unittest.main()
