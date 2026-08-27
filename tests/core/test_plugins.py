import unittest
from pathlib import Path
from typing import ClassVar

from PySide6.QtWidgets import QWidget
from setuav_studio.plugins.geometry.data import GeometryData, LoftGeometry, Section
from setuav_studio.plugins.geometry.fuselage import FuselageEditor
from setuav_studio.plugins.geometry.mesh import build_loft_wire_vertices

from setuav_studio.plugin_system import (
    PanelContribution,
    PluginManager,
    StudioAPI,
    WorkspaceContribution,
    _candidate_sort_key,
)
from setuav_studio.plugins.core import CorePlugin
from setuav_studio.plugins.core.envelope import PHYSICAL_EXTENSION_ID, EnvelopeEditor
from setuav_studio.plugins.core.project import ProjectExplorer
from setuav_studio.plugins.core.transform import TransformEditor
from setuav_studio.plugins.geometry import GeometryPlugin
from setuav_studio.plugins.view2d import (
    View2DCanvas,
    View2DGeometrySource,
    View2DPlugin,
    View2DScene,
)
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.panels: list[PanelContribution] = []
        self.workspaces: list[WorkspaceContribution] = []
        self.api._host.bind_panel_handlers(self.panels.append)
        self.api._host.bind_workspace_handlers(self.workspaces.append)
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

    def test_studio_api_registers_and_resolves_component_icon(self) -> None:
        self.api.register_component_icon("custom:sensor", "fa6s.camera")
        component = {"type": "custom:sensor", "kind": "component"}
        icon = self.api.get_component_icon(component)
        self.assertFalse(icon.isNull())

        # Fallback to default component icon
        unknown = {"type": "unknown:item", "kind": "component"}
        default_icon = self.api.get_component_icon(unknown)
        self.assertFalse(default_icon.isNull())

        # Instance kind fallback
        instance = {"kind": "instance", "source": "wing"}
        instance_icon = self.api.get_component_icon(instance)
        self.assertFalse(instance_icon.isNull())

    def test_rejects_duplicate_component_icon_registration(self) -> None:
        self.api.register_component_icon("custom:sensor", "fa6s.camera")
        with self.assertRaises(ValueError):
            self.api.register_component_icon("custom:sensor", "fa6s.camera")

    def test_core_plugin_contributes_properties_panel(self) -> None:
        self.manager.activate(CorePlugin())

        self.assertEqual(
            [panel.id for panel in self.panels],
            ["project.explorer", "studio.properties"],
        )

    def test_core_plugin_contributes_transform_tree_node_and_editor(self) -> None:
        self.manager.activate(CorePlugin())
        component = {
            "id": "motor",
            "name": "Motor",
            "transform": {
                "position": {"x": 100, "y": 20, "z": 5},
                "rotation": {"roll": 1, "pitch": 2, "yaw": 3},
            },
        }
        project = ProjectDocument(
            Path("project.json"),
            "json",
            {"components": [component]},
        )
        self.api._host.set_project(project)

        contribution = self.api.component_tree_nodes(component)[0]
        self.assertEqual(contribution.id, "motor:transform")
        self.assertEqual(contribution.icon, "mdi6.axis-arrow")
        envelope_contribution = self.api.component_tree_nodes(component)[1]
        self.assertEqual(envelope_contribution.id, "motor:physical-envelope")
        self.assertEqual(envelope_contribution.title, "Envelope")
        self.assertEqual(envelope_contribution.icon, "fa6s.ruler-combined")
        editor = self.api.create_component_editor(contribution.selection)
        self.assertIsInstance(editor, TransformEditor)
        self.assertEqual(editor.position_spins["x"].value(), 100.0)
        self.assertEqual(editor.rotation_spins["yaw"].value(), 3.0)

        editor.position_spins["x"].setValue(250)
        self.assertEqual(component["transform"]["position"]["x"], 250.0)
        self.api.undo()
        self.assertEqual(component["transform"]["position"]["x"], 100)

        envelope_editor = self.api.create_component_editor(envelope_contribution.selection)
        self.assertIsInstance(envelope_editor, EnvelopeEditor)
        envelope_editor.dimension_spins["x"].setValue(60)
        envelope_editor.dimension_spins["y"].setValue(30)
        envelope_editor.dimension_spins["z"].setValue(15)
        envelope = component["extensions"][PHYSICAL_EXTENSION_ID]["envelope"]
        self.assertEqual(envelope["size_mm"], {"x": 60.0, "y": 30.0, "z": 15.0})
        self.assertAlmostEqual(envelope_editor.volume_value(), 27_000.0)

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

    def test_geometry_plugin_contributes_workspace(self) -> None:
        self.manager.activate(GeometryPlugin())

        self.assertEqual(
            [workspace.id for workspace in self.workspaces],
            ["studio.workspace.design"],
        )
        self.assertEqual(self.workspaces[0].title, "Design")

    def test_viewer_builds_closed_loft_sections_and_connectors(self) -> None:
        data = GeometryData(
            lofts=(
                LoftGeometry(
                    component_id="fuselage",
                    sections=(
                        Section(((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))),
                        Section(((1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (1.0, 0.0, 1.0))),
                    ),
                    station_spacing=0.0,
                ),
            )
        )

        vertices = build_loft_wire_vertices(data)

        # 3 edges per loop and 3 longitudinal connectors, 2 vertices per line (12 floats per line).
        self.assertEqual(len(vertices) // 12, 18)

    def test_viewer_rejects_mismatched_loft_sections(self) -> None:
        data = GeometryData(
            lofts=(
                LoftGeometry(
                    component_id="fuselage",
                    sections=(
                        Section(((0.0, 0.0, 0.0),) * 3),
                        Section(((1.0, 0.0, 0.0),) * 4),
                    ),
                ),
            )
        )

        with self.assertRaisesRegex(ValueError, "equal point counts"):
            build_loft_wire_vertices(data)

    def test_new_fuselage_section_uses_available_longitudinal_space(self) -> None:
        sections = [
            {"position": {"x": 100}},
            {"position": {"x": 300}},
        ]

        self.assertEqual(FuselageEditor._new_section_x(sections, 1), 200)
        self.assertEqual(FuselageEditor._new_section_x(sections, 2), 400)

    def test_new_fuselage_segment_has_valid_defaults_and_unique_tag(self) -> None:
        segment = FuselageEditor._new_segment([{"tag": "segment"}, {"tag": "segment-2"}])

        self.assertEqual(segment["tag"], "segment-3")
        self.assertEqual(len(segment["sections"]), 2)
        self.assertEqual(segment["loft"]["method"], "smooth")

    def test_discovers_bundled_geometry_plugin(self) -> None:
        self.manager.activate(CorePlugin())

        issues = self.manager.discover()

        self.assertEqual(issues, [])
        self.assertIn("org.setuav.core:fuselage", self.api._component_editors)

    def test_view2d_plugin_provides_shared_scene_engine(self) -> None:
        self.manager.activate(View2DPlugin())

        scene = View2DScene(title="Top Projection", x_label="X", y_label="Y")
        scene.add_marker("battery", (120.0, 30.0), label="Battery")

        self.assertIn("org.setuav.studio.view2d", self.manager._providers)
        self.assertEqual(scene.markers[0].id, "battery")
        self.assertEqual(scene.markers[0].position, (120.0, 30.0))

    def test_view2d_canvas_injects_geometry_from_studio_api(self) -> None:
        geometry = GeometryData(
            (
                LoftGeometry(
                    component_id="fuselage",
                    sections=(
                        Section(((0.0, -20.0, 0.0), (0.0, 20.0, 0.0))),
                        Section(((100.0, -10.0, 0.0), (100.0, 10.0, 0.0))),
                    ),
                ),
            )
        )
        self.api.build_geometry_data = lambda _project=None: geometry
        canvas = View2DCanvas(api=self.api, axes=(0, 1))
        scene = View2DScene(title="Top")
        scene.add_marker("cg", (40.0, 0.0))
        canvas.set_scene(scene)

        self.assertEqual(len(canvas.scene.paths), 1)
        self.assertEqual(len(canvas.scene.markers), 1)
        self.assertEqual(canvas.scene.paths[0].id, "fuselage:envelope")

    def test_view2d_geometry_source_is_shared_and_invalidated(self) -> None:
        calls: list[object | None] = []
        geometry = GeometryData()
        self.api.build_geometry_data = lambda project=None: calls.append(project) or geometry
        source = View2DGeometrySource(self.api)

        self.assertIs(source.current(), geometry)
        self.assertIs(source.current(), geometry)
        self.assertEqual(len(calls), 1)

        source._invalidate(None)
        self.assertIs(source.current(), geometry)
        self.assertEqual(len(calls), 2)

    def test_view2d_canvas_letterboxes_to_preserve_model_aspect_ratio(self) -> None:
        canvas = View2DCanvas()
        canvas.resize(900, 420)
        scene = View2DScene(title="Top")
        scene.add_path(
            "airframe",
            [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)],
            closed=True,
        )
        canvas.set_scene(scene)

        bounds = canvas._bounds()
        self.assertIsNotNone(bounds)
        plot = canvas._plot_rect(bounds)
        data_ratio = (bounds[1] - bounds[0]) / (bounds[3] - bounds[2])
        self.assertAlmostEqual(plot.width() / plot.height(), data_ratio, places=6)

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

    def test_version_satisfies_pep440_pre_release_and_build_metadata(self) -> None:
        from setuav_studio.plugin_system import _version_satisfies

        self.assertTrue(_version_satisfies("1.2.3-rc1", "^1.2.0"))
        self.assertTrue(_version_satisfies("1.2.3.4", "^1.2.0"))
        self.assertFalse(_version_satisfies("1.2.3+build5", "1.2.3"))
        self.assertFalse(_version_satisfies("1.2.0-rc1", "^1.2.0"))
        self.assertFalse(_version_satisfies("2.0.0", "^1.2.3"))
        self.assertTrue(_version_satisfies("0.2.9", "^0.2.3"))
        self.assertFalse(_version_satisfies("0.3.0", "^0.2.3"))
        self.assertTrue(_version_satisfies("0.0.3", "^0.0.3"))
        self.assertFalse(_version_satisfies("0.0.4", "^0.0.3"))
        self.assertTrue(_version_satisfies("1.0.0", "1.0.0"))
        self.assertTrue(_version_satisfies("0.0.1", "*"))
        self.assertFalse(_version_satisfies("not-a-version", "1.0.0"))

    def test_component_edits_support_undo_and_redo(self) -> None:
        component = {"name": "Before"}
        project = ProjectDocument(
            Path("project.json"),
            "json",
            {"components": [component]},
        )
        self.api._host.set_project(project)

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

    def test_plugin_deactivate_and_reactivate(self) -> None:
        activated: list[str] = []
        deactivated: list[str] = []

        class ReversiblePlugin:
            id = "com.example.reversible"
            provides: ClassVar[dict[str, str]] = {"org.example.dep": "1.0.0"}

            def activate(self, api: StudioAPI) -> None:
                activated.append(self.id)
                api.register_component_editor("com.example:thing", lambda c: QWidget())

            def deactivate(self, api: StudioAPI) -> None:
                deactivated.append(self.id)
                api.remove_component_editor("com.example:thing")

        plugin = ReversiblePlugin()
        self.manager.activate(plugin)

        self.assertEqual(activated, ["com.example.reversible"])
        self.assertIn("com.example:thing", self.api._component_editors)
        self.assertIn("org.example.dep", self.manager._providers)

        self.manager.deactivate("com.example.reversible")

        self.assertEqual(deactivated, ["com.example.reversible"])
        self.assertNotIn("com.example:thing", self.api._component_editors)
        self.assertNotIn("org.example.dep", self.manager._providers)
        self.assertNotIn("com.example.reversible", self.manager._plugins)

        self.manager.activate(plugin)
        self.assertIn("com.example:thing", self.api._component_editors)

    def test_deactivate_without_deactivate_method_is_noop(self) -> None:
        class PlainPlugin:
            id = "com.example.plain"

            def activate(self, api: StudioAPI) -> None:
                api.register_component_editor("com.example:plain", lambda c: QWidget())

        plugin = PlainPlugin()
        self.manager.activate(plugin)
        self.manager.deactivate("com.example.plain")

        self.assertNotIn("com.example.plain", self.manager._plugins)
        self.assertIn("com.example:plain", self.api._component_editors)
        with self.assertRaises(ValueError):
            self.manager.deactivate("com.example.plain")

    def test_candidate_sort_key_orders_by_priority_then_id(self) -> None:
        class LowPriority:
            id = "z-low"
            priority = 10

            def activate(self, api: StudioAPI) -> None: ...

        class HighPriority:
            id = "a-high"
            priority = 90

            def activate(self, api: StudioAPI) -> None: ...

        class NoPriority:
            id = "b-plain"

            def activate(self, api: StudioAPI) -> None: ...

        keys = [
            _candidate_sort_key(HighPriority, "src-high"),
            _candidate_sort_key(LowPriority, "src-low"),
            _candidate_sort_key(NoPriority, "src-plain"),
        ]
        keys.sort(key=lambda item: (item[0], item[1]))

        self.assertEqual(
            [key[1] for key in keys],
            ["z-low", "a-high", "b-plain"],
        )
        self.assertEqual(keys[0][0], 10)
        self.assertEqual(keys[1][0], 90)
        self.assertEqual(keys[2][0], 100)

    def test_show_status_delivers_and_queues_messages(self) -> None:
        received: list[tuple[str, str, int]] = []
        self.api.show_status("queued", "warning", 0)
        self.assertEqual(received, [])
        self.assertEqual(self.api._pending_status, [("queued", "warning", 0)])

        self.api._host.bind_status_handler(
            lambda message, level, timeout_ms: received.append((message, level, timeout_ms))
        )
        self.assertEqual(received, [("queued", "warning", 0)])
        self.assertEqual(self.api._pending_status, [])

        self.api.show_status("done", "success", 3000)
        self.assertEqual(received[-1], ("done", "success", 3000))

        self.api.clear_status()
        self.assertEqual(received[-1], ("", "info", 0))

    def test_remove_panel_and_workspace_via_shell(self) -> None:
        from setuav_studio.shell import MainWindow

        get_qapp()
        api = StudioAPI()
        window = MainWindow(api)
        api.add_panel(
            PanelContribution(
                id="test.removable",
                title="Removable Panel",
                factory=QWidget,
            )
        )
        api.add_workspace(
            WorkspaceContribution(
                id="test.removable-ws",
                title="Removable Workspace",
            )
        )
        self.assertIn("test.removable", window._panels)
        self.assertIn("test.removable-ws", window._workspaces)

        api.remove_panel("test.removable")
        api.remove_workspace("test.removable-ws")

        self.assertNotIn("test.removable", window._panels)
        self.assertNotIn("test.removable-ws", window._workspaces)

    def test_dynamic_schema_registration_and_validation(self) -> None:
        """Verify 3rd party plugins can dynamically register schemas and validate component types."""
        from setuav_studio.schema_validation import validate_project

        api = StudioAPI()

        # 1. Custom 3rd-party component schema
        custom_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["frequency_ghz"],
            "properties": {
                "frequency_ghz": {"type": "number", "minimum": 1.0, "maximum": 100.0},
            },
        }

        # 2. Register via StudioAPI
        api.register_component_type_schema("com.custom:radar-sensor", custom_schema)

        # 3. Valid project with custom component
        valid_project = {
            "name": "Radar Drone",
            "plugins": [],
            "components": [
                {
                    "id": "radar_1",
                    "name": "Front Radar",
                    "type": "com.custom:radar-sensor",
                    "parameters": {"frequency_ghz": 77.0},
                }
            ],
        }
        issues = validate_project(valid_project)
        self.assertEqual(len(issues), 0)

        # 4. Invalid project (frequency out of bounds)
        invalid_project = {
            "name": "Radar Drone",
            "plugins": [],
            "components": [
                {
                    "id": "radar_1",
                    "name": "Front Radar",
                    "type": "com.custom:radar-sensor",
                    "parameters": {"frequency_ghz": 500.0},
                }
            ],
        }
        issues = validate_project(invalid_project)
        self.assertGreater(len(issues), 0)


if __name__ == "__main__":
    unittest.main()
