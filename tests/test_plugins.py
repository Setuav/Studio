import unittest
from pathlib import Path

from setuav_studio.plugin_system import PanelContribution, PluginManager, StudioAPI
from setuav_studio.plugins.core import CorePlugin
from setuav_studio.plugins.core.project import ProjectExplorer
from setuav_studio.plugins.geometry import GeometryPlugin
from setuav_studio.plugins.geometry.fuselage import FuselageEditor
from setuav_studio.project import ProjectDocument


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

    def test_studio_api_creates_registered_kind_editor(self) -> None:
        instance = {"kind": "instance", "source": "wing-left"}
        editor = object()
        self.api.register_kind_editor("instance", lambda _instance: editor)

        self.assertIs(self.api.create_component_editor(instance), editor)

    def test_rejects_duplicate_component_editor_registration(self) -> None:
        self.api.register_component_editor("example:wing", lambda _component: object())

        with self.assertRaises(ValueError):
            self.api.register_component_editor("example:wing", lambda _component: object())

    def test_rejects_duplicate_kind_editor_registration(self) -> None:
        self.api.register_kind_editor("instance", lambda _component: object())

        with self.assertRaises(ValueError):
            self.api.register_kind_editor("instance", lambda _component: object())

    def test_core_plugin_contributes_properties_panel(self) -> None:
        self.manager.activate(CorePlugin())

        self.assertEqual(
            [panel.id for panel in self.panels],
            ["project.explorer", "studio.properties"],
        )

    def test_project_explorer_describes_instance_source_by_name(self) -> None:
        components = [
            {"id": "wing-left", "name": "Left Main Wing", "kind": "component"},
            {
                "id": "wing-right",
                "kind": "instance",
                "source": "wing-left",
            },
        ]

        self.assertEqual(
            ProjectExplorer._component_type_text(components[1], components),
            "Instance of Left Main Wing",
        )

    def test_geometry_plugin_registers_fuselage_editor(self) -> None:
        self.manager.activate(GeometryPlugin())

        factory = self.api._component_editors["org.setuav.core:fuselage"]
        self.assertIsNotNone(factory)

    def test_new_fuselage_section_uses_available_longitudinal_space(self) -> None:
        sections = [
            {"position": {"x": 100}},
            {"position": {"x": 300}},
        ]

        self.assertEqual(FuselageEditor._new_section_x(sections, 1), 200)
        self.assertEqual(FuselageEditor._new_section_x(sections, 2), 400)

    def test_new_fuselage_segment_has_valid_defaults_and_unique_tag(self) -> None:
        segment = FuselageEditor._new_segment(
            [{"tag": "segment"}, {"tag": "segment-2"}]
        )

        self.assertEqual(segment["tag"], "segment-3")
        self.assertEqual(len(segment["sections"]), 2)
        self.assertEqual(segment["loft"]["method"], "smooth")

    def test_discovers_bundled_geometry_plugin(self) -> None:
        self.manager.activate(CorePlugin())

        issues = self.manager.discover()

        self.assertEqual(issues, [])
        self.assertIn("org.setuav.core:fuselage", self.api._component_editors)

    def test_checks_project_plugin_requirements(self) -> None:
        self.manager.activate(GeometryPlugin())

        compatible = self.manager.check_project_requirements(
            {"plugins": [{"id": "org.setuav.core", "version": "^1.0.0"}]}
        )
        missing = self.manager.check_project_requirements(
            {"plugins": [{"id": "example.missing", "version": "1.0.0"}]}
        )

        self.assertEqual(compatible, [])
        self.assertEqual(missing, ["Missing plugin: example.missing"])

    def test_component_edits_support_undo_and_redo(self) -> None:
        component = {"name": "Before"}
        project = ProjectDocument(
            Path("project.json"),
            "json",
            {"components": [component]},
        )
        self.api.set_project(project)

        self.api.edit_component(
            component,
            "Rename component",
            lambda: component.__setitem__("name", "After"),
        )

        self.assertEqual(component["name"], "After")
        self.assertTrue(project.modified)
        self.api.undo()
        self.assertEqual(component["name"], "Before")
        self.assertFalse(project.modified)
        self.api.redo()
        self.assertEqual(component["name"], "After")

    def test_rejects_duplicate_plugin_activation(self) -> None:
        self.manager.activate(CorePlugin())

        with self.assertRaises(ValueError):
            self.manager.activate(CorePlugin())


if __name__ == "__main__":
    unittest.main()
