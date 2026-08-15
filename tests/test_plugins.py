import unittest

from setuav_studio.plugins import PanelContribution, PluginManager, StudioAPI
from setuav_studio.project_plugin import ProjectPlugin


class PluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = StudioAPI()
        self.panels: list[PanelContribution] = []
        self.api.set_panel_handler(self.panels.append)
        self.manager = PluginManager(self.api)

    def test_project_plugin_contributes_explorer_panel(self) -> None:
        self.manager.activate(ProjectPlugin())

        self.assertEqual(len(self.panels), 1)
        self.assertEqual(self.panels[0].id, "project.explorer")

    def test_rejects_duplicate_plugin_activation(self) -> None:
        self.manager.activate(ProjectPlugin())

        with self.assertRaises(ValueError):
            self.manager.activate(ProjectPlugin())


if __name__ == "__main__":
    unittest.main()
