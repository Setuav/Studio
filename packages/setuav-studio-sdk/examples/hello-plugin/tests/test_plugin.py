"""Verify the example plugin's registration lifecycle."""

import unittest

from setuav_example_plugin import HelloPlugin


class _RecordingAPI:
    def __init__(self) -> None:
        self.added_workspaces: list[object] = []
        self.added_panels: list[object] = []
        self.removed_workspaces: list[str] = []
        self.removed_panels: list[str] = []

    def add_workspace(self, contribution: object) -> None:
        self.added_workspaces.append(contribution)

    def add_panel(self, contribution: object) -> None:
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
        plugin.deactivate(api)  # type: ignore[arg-type]

        self.assertEqual(len(api.added_workspaces), 1)
        self.assertEqual(len(api.added_panels), 1)
        self.assertEqual(api.removed_workspaces, ["com.example.hello.workspace"])
        self.assertEqual(api.removed_panels, ["com.example.hello.panel"])


if __name__ == "__main__":
    unittest.main()
