import unittest

from setuav_studio.plugin_system import PanelContribution, PluginManager, StudioAPI
from setuav_studio.plugins.core import CorePlugin
from setuav_studio.plugins.geometry import GeometryPlugin
from setuav_studio.plugins.geometry.fuselage import FuselageEditor


class PluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = StudioAPI()
        self.panels: list[PanelContribution] = []
        self.api.set_panel_handler(self.panels.append)
        self.manager = PluginManager(self.api)

    def test_studio_api_publishes_selection_changes(self) -> None:
        selections: list[object | None] = []
        self.api.on_selection_changed(selections.append)

        component = {"name": "Wing"}
        self.api.set_selection(component)

        self.assertEqual(selections, [None, component])

    def test_studio_api_creates_registered_component_editor(self) -> None:
        component = {"type": "example:wing"}
        editor = object()
        self.api.register_component_editor("example:wing", lambda _component: editor)

        self.assertIs(self.api.create_component_editor(component), editor)

    def test_rejects_duplicate_component_editor_registration(self) -> None:
        self.api.register_component_editor("example:wing", lambda _component: object())

        with self.assertRaises(ValueError):
            self.api.register_component_editor("example:wing", lambda _component: object())

    def test_core_plugin_contributes_properties_panel(self) -> None:
        self.manager.activate(CorePlugin())

        self.assertEqual(
            [panel.id for panel in self.panels],
            ["project.explorer", "studio.properties"],
        )

    def test_geometry_plugin_registers_fuselage_editor(self) -> None:
        self.manager.activate(GeometryPlugin())

        factory = self.api._component_editors["org.setuav.core:fuselage"]
        self.assertIs(factory, FuselageEditor)

    def test_rejects_duplicate_plugin_activation(self) -> None:
        self.manager.activate(CorePlugin())

        with self.assertRaises(ValueError):
            self.manager.activate(CorePlugin())


if __name__ == "__main__":
    unittest.main()
