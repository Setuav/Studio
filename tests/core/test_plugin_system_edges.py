"""Boundary tests for StudioAPI registries and plugin lifecycle isolation."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QWidget

from setuav_studio.plugin_system import (
    ActionContribution,
    ComponentTreeNodeContribution,
    PanelContribution,
    PluginManager,
    ProjectTreeNodeContribution,
    SettingsPageContribution,
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    ToolContribution,
    WorkspaceContribution,
    _candidate_sort_key,
)
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class PluginSystemEdgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.project = ProjectDocument(Path("project.json"), "json", {"components": []})

    def test_host_services_are_not_exposed_as_plugin_api_methods(self) -> None:
        host_only_names = {
            "check_project_requirements",
            "mark_project_saved",
            "set_action_handler",
            "set_panel_handler",
            "set_progress_handler",
            "set_project",
            "set_project_requirement_checker",
            "set_status_handler",
            "set_toolbar_handler",
            "set_workspace_handler",
            "settings_pages",
            "undo_stack",
        }

        for name in host_only_names:
            with self.subTest(name=name):
                self.assertFalse(hasattr(self.api, name))

    def test_contributions_validate_actions_and_workspace_filters(self) -> None:
        panel = PanelContribution("panel", "Panel", QWidget, workspace_id=["design", "analysis"])
        self.assertTrue(panel.is_in_workspace("design"))
        self.assertFalse(panel.is_in_workspace("other"))
        self.assertTrue(PanelContribution("all", "All", QWidget).is_in_workspace(None))
        self.assertTrue(
            PanelContribution("one", "One", QWidget, workspace_id="design").is_in_workspace(
                "design"
            )
        )

        with self.assertRaises(ValueError):
            ToolbarContribution("invalid", "Invalid")
        with self.assertRaises(ValueError):
            ToolbarContribution("invalid", "Invalid", callback=lambda: None, command="run")
        with self.assertRaises(ValueError):
            ToolbarContribution(
                "invalid",
                "Invalid",
                callback=lambda: None,
                menu_items=(ToolbarMenuItemContribution("Item", lambda: None),),
            )
        with self.assertRaises(ValueError):
            ToolbarContribution(
                "invalid",
                "Invalid",
                command="run",
                menu_items=(ToolbarMenuItemContribution("Item", lambda: None),),
            )
        toolbar = ToolbarContribution("toolbar", "Toolbar", command="run", workspace_id=("design",))
        self.assertTrue(toolbar.is_in_workspace("design"))
        self.assertFalse(toolbar.is_in_workspace("other"))
        self.assertTrue(ToolbarContribution("all", "All", command="run").is_in_workspace(None))
        self.assertTrue(
            ToolbarContribution("one", "One", command="run", workspace_id="design").is_in_workspace(
                "design"
            )
        )

    def test_shell_handlers_queue_flush_remove_and_dispatch_contributions(self) -> None:
        self.api.add_panel(PanelContribution("panel", "Panel", QWidget))
        self.api.remove_panel("missing")
        panels: list[str] = []
        removed_panels: list[str] = []
        self.api._host.bind_panel_handlers(
            lambda item: panels.append(item.id), removed_panels.append
        )
        self.api.remove_panel("panel")
        self.assertEqual((panels, removed_panels), (["panel"], ["panel"]))

        workspace = WorkspaceContribution("design", "Design")
        self.api.add_workspace(workspace)
        workspaces: list[str] = []
        removed_workspaces: list[str] = []
        switched: list[str] = []
        self.api._host.bind_workspace_handlers(
            lambda item: workspaces.append(item.id), switched.append, removed_workspaces.append
        )
        self.api.set_workspace(WorkspaceContribution("analysis", "Analysis"))
        self.api.remove_workspace("design")
        changes: list[str] = []
        self.api.switch_workspace("design")
        self.api.on_workspace_changed(changes.append)
        self.assertEqual(workspaces, ["design", "analysis"])
        self.assertEqual(removed_workspaces, ["design"])
        self.assertEqual(switched, ["design"])
        self.assertEqual(changes, ["design"])

        first = ToolbarContribution("first", "First", command="first")
        removed_toolbar: list[str] = []
        self.api.add_toolbar_item(first)
        self.api.remove_toolbar_item("first")
        self.api.add_toolbar_item(first)
        toolbars: list[str] = []
        self.api._host.bind_toolbar_handlers(
            lambda item: toolbars.append(item.id), removed_toolbar.append
        )
        self.api.add_toolbar_item(ToolbarContribution("second", "Second", command="second"))
        self.api.remove_toolbar_item("second")
        self.assertEqual(toolbars, ["first", "second"])
        self.assertEqual(removed_toolbar, ["second"])

    def test_status_progress_events_and_actions_are_isolated(self) -> None:
        self.api.clear_status()
        statuses: list[tuple[str, str, int]] = []
        self.api._host.bind_status_handler(lambda *args: statuses.append(args))
        self.api.clear_status()
        self.assertEqual(statuses, [("", "info", 0)])

        self.api.report_progress(1, 2, "ignored")
        progress: list[tuple[int, int, str]] = []
        self.api._host.bind_progress_handler(lambda *args: progress.append(args))
        self.api.report_progress(1, 2, "running")
        self.api.clear_progress()
        self.assertEqual(progress, [(1, 2, "running"), (1, 1, "")])

        received: list[object] = []

        def broken(_payload: object) -> None:
            raise RuntimeError("subscriber failed")

        self.api.subscribe("event", broken)
        self.api.subscribe("event", received.append)
        with self.assertLogs("setuav_studio.plugin_system", level="ERROR"):
            self.api.publish("event", 42)
        self.api.unsubscribe("event", broken)
        self.api.unsubscribe("event", broken)
        self.api.unsubscribe("missing", broken)
        self.assertEqual(received, [42])

        pending = ActionContribution("File", "Pending", lambda: None)
        self.api.add_action(pending)
        actions: list[str] = []
        removed: list[tuple[str, str]] = []
        self.api._host.bind_action_handlers(
            lambda item: actions.append(item.title), lambda *args: removed.append(args)
        )
        self.api.add_action(ActionContribution("File", "Direct", lambda: None))
        self.api.remove_action("File", "Direct")
        self.assertEqual(actions, ["Pending", "Direct"])
        self.assertEqual(removed, [("File", "Direct")])

    def test_qobject_event_subscriber_is_removed_when_owner_is_destroyed(self) -> None:
        receiver = QWidget()
        self.api.subscribe("event", receiver.show)
        self.assertEqual(len(self.api._event_subscribers["event"]), 1)

        receiver.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

        self.assertEqual(self.api._event_subscribers.get("event"), [])

    def test_settings_and_tool_registries_sort_and_remove_entries(self) -> None:
        pages = (
            SettingsPageContribution("z", "Zulu", QWidget, order=10),
            SettingsPageContribution("b", "beta", QWidget, order=5),
            SettingsPageContribution("a", "Alpha", QWidget, order=5),
        )
        for page in pages:
            self.api.add_settings_page(page)
        with self.assertRaises(ValueError):
            self.api.add_settings_page(pages[0])
        self.assertEqual([page.id for page in self.api._host.settings_pages()], ["a", "b", "z"])
        self.api.remove_settings_page("a")
        self.api.remove_settings_page("missing")

        actions: list[ActionContribution] = []
        self.api._host.bind_action_handlers(actions.append)
        self.api.register_tool(ToolContribution("Plain", lambda: None))
        self.api.register_tool(ToolContribution("Grouped", lambda: None, group="Geometry"))
        self.assertEqual([action.menu for action in actions], ["Tools", "Tools/Geometry"])

    def test_project_and_selection_listeners_drop_deleted_qobjects(self) -> None:
        project_events: list[ProjectDocument] = []
        self.api.on_project_changed(project_events.append)

        def dead_project(_project: ProjectDocument) -> None:
            raise RuntimeError("deleted")

        self.api.on_project_changed(dead_project)
        self.api._host.set_project(self.project)
        self.assertEqual(project_events, [self.project])
        self.assertNotIn(dead_project, self.api._project_listeners)
        self.api.on_project_changed(project_events.append)
        self.api.remove_project_listener(project_events.append)

        content_events: list[ProjectDocument] = []

        def dead_content(_project: ProjectDocument) -> None:
            raise RuntimeError("deleted")

        self.api.on_project_content_changed(content_events.append)
        self.api.on_project_content_changed(dead_content)
        self.api.notify_project_content_changed()
        self.assertEqual(content_events, [self.project])
        self.assertNotIn(dead_content, self.api._project_content_listeners)
        self.api.remove_project_content_listener(content_events.append)
        self.api.remove_project_content_listener(content_events.append)

        selections: list[object] = []

        def dead_selection(_selection: object) -> None:
            raise RuntimeError("deleted")

        self.api.on_selection_changed(selections.append)
        self.api.on_selection_changed(dead_selection)
        self.api.set_selection("wing")
        self.assertEqual(selections, [None, "wing"])
        self.assertNotIn(dead_selection, self.api._selection_listeners)
        self.api.remove_selection_listener(selections.append)
        self.api.remove_selection_listener(selections.append)

    def test_modified_and_section_listeners_are_isolated_and_removable(self) -> None:
        modified: list[bool] = []

        def dead_modified(_value: bool) -> None:
            raise RuntimeError("deleted")

        self.api.on_modified_changed(modified.append)
        self.api.on_modified_changed(dead_modified)
        self.api._on_clean_changed(False)
        self.assertEqual(modified, [False, True])
        self.assertNotIn(dead_modified, self.api._modified_listeners)
        self.api.remove_modified_listener(modified.append)
        self.api.remove_modified_listener(modified.append)

        sections: list[tuple[str, int, int] | None] = []

        def dead_section(_value: tuple[str, int, int] | None) -> None:
            raise RuntimeError("deleted")

        self.api.on_section_selection_changed(sections.append)
        self.api.on_section_selection_changed(dead_section)
        self.api.set_section_selection(("wing", 0, 1))
        self.assertEqual(sections, [None, ("wing", 0, 1)])
        self.assertNotIn(dead_section, self.api._section_selection_listeners)
        self.api.remove_section_selection_listener(sections.append)
        self.api.remove_section_selection_listener(sections.append)

    def test_noop_edits_and_missing_projects_do_not_create_undo_commands(self) -> None:
        component = {"name": "Wing"}
        self.api.edit_component(component, "No-op", lambda: None)
        self.assertEqual(self.api._host.undo_stack.count(), 0)

        changes: list[str] = []
        self.api.edit_project("Without project", lambda: changes.append("changed"))
        self.assertEqual(changes, ["changed"])
        self.api.edit_project_extension("ext", "No project", lambda _ext: None)
        self.api.edit_component_extension("missing", "ext", "No project", lambda _ext: None)
        self.api.undo()
        self.api.redo()
        self.api._host.mark_project_saved()
        self.assertEqual(self.api._host.check_project_requirements({}), [])

        self.api._host.set_project(self.project)
        self.api.edit_project("No-op", lambda: None)
        self.api.edit_component_extension("missing", "ext", "Missing", lambda _ext: None)
        self.project.data["extensions"] = "invalid"
        self.api.edit_project_extension("ext", "Repair", lambda ext: ext.update({"x": 1}))
        self.assertEqual(self.project.data["extensions"]["ext"], {"x": 1})

    def test_editor_icon_and_geometry_registries_support_removal_and_duplicates(self) -> None:
        self.assertIsNone(self.api.create_component_editor({}))
        self.api.register_component_editor("wing", QWidget)
        self.api.remove_component_editor("wing")
        self.api.register_kind_editor("instance", QWidget)
        self.api.remove_kind_editor("instance")

        self.api.register_component_icon("wing", "component")
        self.api.remove_component_icon("wing")
        self.api.register_kind_icon("custom", "component")
        with self.assertRaises(ValueError):
            self.api.register_kind_icon("custom", "component")
        self.assertFalse(self.api.get_component_icon({"kind": "custom"}).isNull())
        self.api.remove_kind_icon("custom")

        def provider(component: dict[str, object]) -> dict[str, object]:
            return component

        self.api.register_geometry_provider("wing", provider)
        with self.assertRaises(ValueError):
            self.api.register_geometry_provider("wing", provider)
        self.api.remove_geometry_provider("wing")

    def test_tree_provider_registries_notify_and_resolve(self) -> None:
        component_node = ComponentTreeNodeContribution("node", "Node", {})
        self.api.register_component_tree_provider("one", lambda _component: (component_node,))
        with self.assertRaises(ValueError):
            self.api.register_component_tree_provider("one", lambda _component: ())
        self.assertEqual(self.api.component_tree_nodes({}), (component_node,))
        self.api.remove_component_tree_provider("one")

        events: list[ProjectDocument] = []
        self.api._host.set_project(self.project)
        self.api.on_project_content_changed(events.append)
        project_node = ProjectTreeNodeContribution("node", "Node", {})
        self.api.register_project_tree_provider("one", lambda _project: (project_node,))
        with self.assertRaises(ValueError):
            self.api.register_project_tree_provider("one", lambda _project: ())
        self.assertEqual(self.api.project_tree_nodes(self.project), (project_node,))
        self.api.remove_project_tree_provider("missing")
        self.api.remove_project_tree_provider("one")
        self.assertEqual(len(events), 2)

    def test_geometry_builder_handles_empty_and_explicit_projects(self) -> None:
        geometry = self.api.build_geometry_data()
        self.assertEqual(geometry.lofts, ())

        sentinel = object()
        with patch(
            "setuav_studio.plugins.geometry.viewport.scene.build_project_geometry",
            return_value=sentinel,
        ) as build:
            self.assertIs(self.api.build_geometry_data(self.project), sentinel)
        build.assert_called_once_with(self.project, self.api._geometry_providers)

    def test_plugin_requirements_handle_malformed_and_incompatible_entries(self) -> None:
        manager = PluginManager(self.api)
        manager._providers["known"] = "1.0.0"
        self.assertEqual(manager.check_project_requirements({"plugins": "invalid"}), [])
        issues = manager.check_project_requirements(
            {
                "plugins": [
                    "invalid",
                    {"id": 42},
                    {"id": "missing"},
                    {"id": "known", "version": "2.0.0"},
                    {"id": "known", "version": 1},
                ]
            }
        )
        self.assertEqual(
            issues,
            ["Missing plugin: missing", "Incompatible plugin: known 1.0.0 (requires 2.0.0)"],
        )

    def test_plugin_candidates_and_discovery_failures_are_isolated(self) -> None:
        manager = PluginManager(self.api)

        class GoodPlugin:
            id = "good"
            priority = 10
            provides: ClassVar[dict[str, str]] = {"capability": "1.0.0"}

            def activate(self, _api: StudioAPI) -> None: ...

        class BadPlugin:
            id = "bad"

            def activate(self, _api: StudioAPI) -> None:
                raise RuntimeError("activation failed")

        class OddPlugin:
            id = "odd"
            priority = "invalid"
            provides = "invalid"

            def activate(self, _api: StudioAPI) -> None: ...

        manager._activate_candidate(GoodPlugin)
        manager._activate_candidate(GoodPlugin)
        manager.activate(OddPlugin())  # type: ignore[arg-type]
        self.assertEqual(_candidate_sort_key(OddPlugin, "source")[0], 100)
        with self.assertRaises(TypeError):
            manager._activate_candidate(object())

        package = SimpleNamespace(__path__=["plugins"])
        modules = [SimpleNamespace(name="load-fail"), SimpleNamespace(name="bad")]

        def import_side_effect(name: str) -> object:
            if name == "setuav_studio.plugins":
                return package
            if name.endswith("load-fail"):
                raise ImportError("load failed")
            return SimpleNamespace(PLUGIN=BadPlugin())

        with (
            patch("setuav_studio.plugin_system.manager.pkgutil.iter_modules", return_value=modules),
            patch(
                "setuav_studio.plugin_system.manager.import_module",
                side_effect=import_side_effect,
            ),
            self.assertLogs("setuav_studio.plugin_system.manager", level="WARNING"),
        ):
            issues = manager._discover_bundled()
        self.assertEqual(len(issues), 2)

        load_error = Mock(name="load-error")
        load_error.name = "load-error"
        load_error.load.side_effect = ImportError("entry load failed")
        activation_error = Mock(name="activation-error")
        activation_error.name = "activation-error"
        activation_error.load.return_value = BadPlugin()
        with (
            patch(
                "setuav_studio.plugin_system.manager.metadata.entry_points",
                return_value=[load_error, activation_error],
            ),
            self.assertLogs("setuav_studio.plugin_system.manager", level="WARNING"),
        ):
            issues = manager._discover_entry_points()
        self.assertEqual(len(issues), 2)

        with (
            patch.object(
                manager,
                "_collect_bundled_candidates",
                return_value=([issues[0]], []),
            ),
            patch.object(
                manager,
                "_collect_entry_point_candidates",
                return_value=([issues[1]], []),
            ),
        ):
            self.assertEqual(len(manager.discover()), 2)

    def test_active_plugin_candidate_is_not_overwritten_by_duplicate(self) -> None:
        manager = PluginManager(self.api)

        class BundledPlugin:
            id = "com.example.duplicate"

            def activate(self, _api: StudioAPI) -> None: ...

        class EntryPointPlugin:
            id = "com.example.duplicate"

            def activate(self, _api: StudioAPI) -> None: ...

        bundled = BundledPlugin()
        manager.activate(bundled)
        manager._activate_candidate(EntryPointPlugin())

        self.assertIs(manager._candidates["com.example.duplicate"], bundled)

    def test_disabled_plugin_candidate_is_preserved_across_rediscovery(self) -> None:
        manager = PluginManager(self.api)
        manager._disabled_plugins.add("com.example.disabled")

        class BundledPlugin:
            id = "com.example.disabled"

            def activate(self, _api: StudioAPI) -> None: ...

        class EntryPointPlugin:
            id = "com.example.disabled"

            def activate(self, _api: StudioAPI) -> None: ...

        bundled = BundledPlugin()
        manager._activate_candidate(bundled)
        manager._activate_candidate(EntryPointPlugin())

        self.assertIs(manager._candidates["com.example.disabled"], bundled)

    def test_disabled_plugin_state_is_loaded_and_saved(self) -> None:
        settings = Mock()
        settings.value.return_value = ["com.example.persisted"]
        with patch("setuav_studio.plugin_system.manager.QSettings", return_value=settings):
            manager = PluginManager(self.api)

            self.assertTrue(manager.is_disabled("com.example.persisted"))

            class Plugin:
                id = "com.example.saved"

                def activate(self, _api: StudioAPI) -> None: ...

                def deactivate(self, _api: StudioAPI) -> None: ...

            manager.activate(Plugin())
            manager.deactivate("com.example.saved")

        settings.setValue.assert_called_once_with(
            "plugins/disabled", ["com.example.persisted", "com.example.saved"]
        )

    def test_discovery_uses_one_global_priority_order(self) -> None:
        manager = PluginManager(self.api)
        activation_order: list[str] = []

        class BundledPlugin:
            id = "bundled"
            priority = 100

            def activate(self, _api: StudioAPI) -> None:
                activation_order.append(self.id)

        class EntryPointPlugin:
            id = "entry-point"
            priority = 0

            def activate(self, _api: StudioAPI) -> None:
                activation_order.append(self.id)

        with (
            patch.object(
                manager,
                "_collect_bundled_candidates",
                return_value=([], [_candidate_sort_key(BundledPlugin, "bundled")]),
            ),
            patch.object(
                manager,
                "_collect_entry_point_candidates",
                return_value=([], [_candidate_sort_key(EntryPointPlugin, "entry-point")]),
            ),
        ):
            self.assertEqual(manager.discover(), [])

        self.assertEqual(activation_order, ["entry-point", "bundled"])

    def test_project_alias_schema_and_handler_absence_paths(self) -> None:
        self.assertIsNone(self.api.project)
        with self.assertRaises(AttributeError):
            self.api.project = self.project  # type: ignore[misc]
        self.api._host.set_project(self.project)
        self.assertIs(self.api.project, self.project)

        empty_api = StudioAPI()
        empty_api.remove_workspace("missing")
        empty_api.remove_action("File", "Missing")
        workspace_changes: list[str] = []
        empty_api.on_workspace_changed(workspace_changes.append)
        empty_api.switch_workspace("design")
        empty_api.notify_project_content_changed()
        empty_api.remove_project_listener(lambda _project: None)
        self.assertEqual(workspace_changes, ["design"])

        catalog = Mock()
        with patch("setuav_studio.schema_validation.get_catalog", return_value=catalog):
            empty_api.register_schema("example", {"type": "object"})
        catalog.register_schema.assert_called_once_with({"type": "object"}, "example")

    def test_workspace_listener_can_be_removed(self) -> None:
        api = StudioAPI()
        changes: list[str] = []

        def listener(workspace_id: str) -> None:
            changes.append(workspace_id)

        api.on_workspace_changed(listener)
        api.switch_workspace("one")
        api.remove_workspace_listener(listener)
        api.switch_workspace("two")

        self.assertEqual(changes, ["one"])

    def test_listeners_may_remove_themselves_before_raising(self) -> None:
        api = StudioAPI()
        calls = {"modified": 0, "selection": 0, "section": 0}

        def dead_project(_project: ProjectDocument) -> None:
            api.remove_project_listener(dead_project)
            raise RuntimeError("deleted")

        def dead_content(_project: ProjectDocument) -> None:
            api.remove_project_content_listener(dead_content)
            raise RuntimeError("deleted")

        def dead_modified(_value: bool) -> None:
            calls["modified"] += 1
            if calls["modified"] == 1:
                return
            api.remove_modified_listener(dead_modified)
            raise RuntimeError("deleted")

        def dead_selection(_value: object) -> None:
            calls["selection"] += 1
            if calls["selection"] == 1:
                return
            api.remove_selection_listener(dead_selection)
            raise RuntimeError("deleted")

        def dead_section(_value: tuple[str, int, int] | None) -> None:
            calls["section"] += 1
            if calls["section"] == 1:
                return
            api.remove_section_selection_listener(dead_section)
            raise RuntimeError("deleted")

        api.on_project_changed(dead_project)
        api.on_project_content_changed(dead_content)
        api.on_modified_changed(dead_modified)
        api.on_selection_changed(dead_selection)
        api.on_section_selection_changed(dead_section)
        api._host.set_project(self.project)
        api.on_project_content_changed(dead_content)
        api.notify_project_content_changed()
        api._on_clean_changed(False)
        api.set_selection("wing")
        api.set_section_selection(("wing", 0, 0))


if __name__ == "__main__":
    unittest.main()
