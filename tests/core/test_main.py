import unittest

from PySide6.QtWidgets import QDockWidget, QWidget

from setuav_studio.__main__ import _parse_arguments
from setuav_studio.plugin_system import (
    PanelContribution,
    PluginManager,
    StudioAPI,
    WorkspaceContribution,
)
from setuav_studio.ui.shell import MainWindow
from tests._common import TEST_PROJECT_PATH, get_qapp

_app = get_qapp()


class MainTests(unittest.TestCase):
    def test_plugin_manager_action_is_bound_to_manager(self) -> None:
        api = StudioAPI()
        window = MainWindow(api)

        self.assertFalse(window._plugin_manager_action.isEnabled())
        window.bind_plugin_manager(PluginManager(api))
        self.assertTrue(window._plugin_manager_action.isEnabled())

    def test_accepts_optional_project_path(self) -> None:
        arguments = _parse_arguments(["example/project.json"])

        self.assertEqual(arguments.project, "example/project.json")

    def test_project_path_is_optional(self) -> None:
        arguments = _parse_arguments([])

        self.assertIsNone(arguments.project)

    def test_accepts_internal_desktop_commands(self) -> None:
        smoke_arguments = _parse_arguments(["--smoke-test"])

        self.assertTrue(smoke_arguments.smoke_test)

    def test_degraded_mode_badge_shown_for_missing_plugins(self) -> None:
        api = StudioAPI()
        api._host.bind_project_requirement_checker(lambda data: ["Missing plugin: com.example.foo"])
        window = MainWindow(api)
        window.show()
        window.open_project(TEST_PROJECT_PATH)
        get_qapp().processEvents()

        self.assertTrue(window._degraded_badge.isVisible())
        self.assertIn("com.example.foo", window._degraded_badge.toolTip())

        api._host.bind_project_requirement_checker(lambda data: [])
        if window._project is not None:
            window._project.modified = False
        window.open_project(TEST_PROJECT_PATH)
        self.assertFalse(window._degraded_badge.isVisible())

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
        view_action = window._panel_actions["test.panel"]
        self.assertIsNotNone(view_action)
        self.assertTrue(view_action.isCheckable())
        self.assertIn(view_action, window._view_menu.actions())
        self.assertEqual(window._view_menu.actions()[0].text(), "Theme")

        window._update_view_menu("test.workspace")
        self.assertEqual(window._view_menu.actions()[0].text(), "Theme")
        self.assertIn(view_action, window._view_menu.actions())
        """4.13: validation_strictness drives open/read_only/cancel outcomes."""
        from pathlib import Path
        from types import SimpleNamespace

        from setuav_studio.project import ProjectDocument
        from setuav_studio.ui.shell import apply_runtime_validation

        valid = ProjectDocument(path=Path("/tmp/x.json"), kind="json", data={})
        issues = [
            SimpleNamespace(path="$.components[0].id", message="Duplicate ID 'a'"),
            SimpleNamespace(path="$.components[1].id", message="Duplicate ID 'a'"),
        ]

        self.assertEqual(
            apply_runtime_validation(valid, [], "strict", interactive=True),
            "open",
        )
        self.assertEqual(
            apply_runtime_validation(valid, issues, "off", interactive=True),
            "open",
        )
        self.assertFalse(valid.read_only)

        self.assertEqual(
            apply_runtime_validation(valid, issues, "warn", interactive=True),
            "read_only",
        )
        self.assertTrue(valid.read_only)

        ro2 = ProjectDocument(path=Path("/tmp/y.json"), kind="json", data={})
        self.assertEqual(
            apply_runtime_validation(ro2, issues, "strict", interactive=False),
            "read_only",
        )
        self.assertTrue(ro2.read_only)

        ok = ProjectDocument(path=Path("/tmp/z.json"), kind="json", data={})
        self.assertEqual(
            apply_runtime_validation(ok, issues, "unexpected", interactive=True),
            "open",
        )


if __name__ == "__main__":
    unittest.main()
