"""Verify the example plugin's registration lifecycle."""

import unittest

from setuav_example_plugin import HelloPlugin

from setuav_studio_sdk import PanelContribution, WorkspaceContribution


class _RecordingAPI:
    def __init__(self) -> None:
        self.added_workspaces: list[WorkspaceContribution] = []
        self.added_panels: list[PanelContribution] = []
        self.removed_workspaces: list[str] = []
        self.removed_panels: list[str] = []

    def add_workspace(self, contribution: WorkspaceContribution) -> None:
        self.added_workspaces.append(contribution)

    def add_panel(self, contribution: PanelContribution) -> None:
        self.added_panels.append(contribution)

    def remove_workspace(self, workspace_id: str) -> None:
        self.removed_workspaces.append(workspace_id)

    def remove_panel(self, panel_id: str) -> None:
        self.removed_panels.append(panel_id)


class ExamplePluginTests(unittest.TestCase):
    def test_plugin_lifecycle(self) -> None:
        api = _RecordingAPI()
        plugin = HelloPlugin()
        plugin.activate(api)  # type: ignore[arg-type]

        self.assertEqual(len(api.added_workspaces), 1)
        self.assertEqual(len(api.added_panels), 1)

        workspace = api.added_workspaces[0]
        panel = api.added_panels[0]
        self.assertEqual(workspace.id, "com.example.hello.workspace")
        self.assertEqual(workspace.title, "Hello")
        self.assertIsNotNone(workspace.default_layout)
        self.assertEqual(panel.id, "com.example.hello.panel")
        self.assertEqual(panel.workspace_id, workspace.id)

        plugin.deactivate(api)  # type: ignore[arg-type]

        self.assertEqual(api.removed_workspaces, ["com.example.hello.workspace"])
        self.assertEqual(api.removed_panels, ["com.example.hello.panel"])


if __name__ == "__main__":
    unittest.main()
