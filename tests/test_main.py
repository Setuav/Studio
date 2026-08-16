import unittest

from PySide6.QtWidgets import QApplication, QDockWidget, QWidget

from setuav_studio.__main__ import _parse_arguments
from setuav_studio.plugin_system import StudioAPI, WorkspaceContribution
from setuav_studio.shell import MainWindow

_app = QApplication.instance() or QApplication([])


class MainTests(unittest.TestCase):
    def test_accepts_optional_project_path(self) -> None:
        arguments = _parse_arguments(["example/project.json"])

        self.assertEqual(arguments.project, "example/project.json")

    def test_project_path_is_optional(self) -> None:
        arguments = _parse_arguments([])

        self.assertIsNone(arguments.project)

    def test_workspace_contribution_creates_dock_and_view_action(self) -> None:
        api = StudioAPI()
        window = MainWindow(api)
        api.set_workspace(
            WorkspaceContribution(
                id="test.workspace",
                title="Test Workspace",
                factory=QWidget,
            )
        )
        dock = window.findChild(QDockWidget, "test.workspace")
        self.assertIsNotNone(dock)
        self.assertEqual(dock.windowTitle(), "Test Workspace")
        self.assertIn(dock.toggleViewAction(), window._view_menu.actions())


if __name__ == "__main__":
    unittest.main()
