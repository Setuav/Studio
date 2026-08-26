"""Headless tests for shell contributions, themes, and workspace layouts."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QDialog, QDockWidget, QWidget

from setuav_studio.plugin_system import (
    ActionContribution,
    PanelContribution,
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    WorkspaceContribution,
)
from setuav_studio.plugins.core.settings import StudioSettings
from setuav_studio.shell import MainWindow
from tests._common import get_qapp


class _FakeSettings:
    values: ClassVar[dict[str, object]] = {}

    def value(self, key: str, fallback: object = None) -> object:
        return self.values.get(key, fallback)

    def setValue(self, key: str, value: object) -> None:
        self.values[key] = value

    def remove(self, key: str) -> None:
        self.values.pop(key, None)


class ShellContributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        _FakeSettings.values = {}
        self.api = StudioAPI()
        self.window = MainWindow(self.api)
        self.addCleanup(self.window.deleteLater)

    def test_theme_switch_refreshes_actions_widgets_and_persistence(self) -> None:
        themed_widget = QWidget()
        themed_widget.update_theme_style = Mock()  # type: ignore[attr-defined]
        self.addCleanup(themed_widget.deleteLater)
        broken_widget = QWidget()
        broken_widget.update_theme_style = Mock(side_effect=RuntimeError("broken"))  # type: ignore[attr-defined]
        self.addCleanup(broken_widget.deleteLater)

        with (
            patch("setuav_studio.ui.theme.apply_theme") as apply_theme,
            patch("setuav_studio.ui.buttons.refresh_all_button_roles") as refresh_roles,
            patch.object(StudioSettings, "load", return_value=StudioSettings(theme_mode="dark")),
            patch.object(StudioSettings, "save") as save_settings,
        ):
            self.window._switch_theme("nord")

        apply_theme.assert_called_once_with(self.app, "nord")
        refresh_roles.assert_called_once_with(self.app)
        save_settings.assert_called_once()
        self.assertTrue(self.window._nord_theme_action.isChecked())
        themed_widget.update_theme_style.assert_called_once()  # type: ignore[attr-defined]

        with (
            patch("setuav_studio.ui.theme.apply_theme"),
            patch("setuav_studio.ui.buttons.refresh_all_button_roles"),
            patch.object(StudioSettings, "load", return_value=StudioSettings(theme_mode="nord")),
            patch.object(StudioSettings, "save") as unchanged_save,
        ):
            self.window._switch_theme("nord")
        unchanged_save.assert_not_called()

    def test_icon_refresh_updates_toolbar_and_isolates_failures(self) -> None:
        menu_item = ToolbarMenuItemContribution("Child", lambda: None, icon="child-icon")
        contribution = ToolbarContribution(
            "menu",
            "Menu",
            icon="menu-icon",
            menu_items=(menu_item,),
        )
        self.api.add_toolbar_item(contribution)
        self.window._update_main_toolbar_style()
        self.window._update_all_icons()

        action = self.window._toolbar_actions["menu"]
        self.assertFalse(action.icon().isNull())
        self.assertFalse(self.window._toolbar_menu_actions["menu"][0][1].icon().isNull())

        with (
            patch("setuav_studio.shell.get_icon", side_effect=RuntimeError("icon failed")),
            self.assertLogs("setuav_studio.shell", level="DEBUG"),
        ):
            self.window._update_all_icons()

    def test_dynamic_actions_support_nested_default_icon_and_removal_paths(self) -> None:
        called: list[str] = []
        nested = ActionContribution(
            "Tools/Geometry",
            "Nested",
            lambda: called.append("nested"),
            icon="component",
            shortcut="Ctrl+Alt+N",
        )
        self.window._add_action(nested)
        menu = self.window._menus["tools/geometry"]
        menu.actions()[0].trigger()
        self.assertEqual(called, ["nested"])
        self.assertFalse(menu.actions()[0].icon().isNull())

        self.window._add_action(ActionContribution("", "Default", lambda: None))
        self.assertIn("Default", [action.text() for action in self.window._tools_menu.actions()])
        self.window._remove_action("Tools/Geometry", "Nested")
        self.assertNotIn("Nested", [action.text() for action in menu.actions()])
        self.window._remove_action("Missing", "Unknown")
        self.window._remove_action("", "Default")

    def test_help_menu_opens_about_dialog(self) -> None:
        self.assertEqual(self.window._help_menu.title(), "&Help")
        self.assertEqual(self.window._about_action.text(), "About")

        with patch("setuav_studio.shell.AboutDialog") as dialog_type:
            self.window._about_action.trigger()

        dialog_type.assert_called_once_with(self.window)
        dialog_type.return_value.exec.assert_called_once_with()

    def test_toolbar_callbacks_commands_menus_and_state_failures(self) -> None:
        called: list[str] = []
        callback = ToolbarContribution(
            "callback",
            "Callback",
            callback=lambda: called.append("callback"),
            group="create",
            order=20,
        )
        command = ToolbarContribution(
            "save",
            "Save Alias",
            command="core.project.save",
            group="project",
            order=10,
        )
        missing_command = ToolbarContribution(
            "missing",
            "Missing",
            command="missing.command",
            group="project",
        )
        menu = ToolbarContribution(
            "menu",
            "Menu",
            menu_items=(
                ToolbarMenuItemContribution(
                    "Enabled",
                    lambda: called.append("menu"),
                    enabled_when=lambda: True,
                ),
                ToolbarMenuItemContribution(
                    "Broken",
                    lambda: None,
                    enabled_when=Mock(side_effect=RuntimeError("broken")),
                ),
            ),
            enabled_when=lambda: True,
            group="create",
        )
        for contribution in (callback, command, missing_command, menu):
            self.api.add_toolbar_item(contribution)

        self.window._toolbar_actions["callback"].trigger()
        self.window._toolbar_menu_actions["menu"][0][1].trigger()
        self.assertEqual(called, ["callback", "menu"])
        self.assertIs(self.window._toolbar_actions["save"], self.window._save_action)
        self.assertNotIn("missing", self.window._toolbar_actions)

        with self.assertLogs("setuav_studio.shell", level="ERROR"):
            self.window._refresh_toolbar_action_states()
        self.assertFalse(self.window._toolbar_menu_actions["menu"][1][1].isEnabled())

        broken = ToolbarContribution(
            "broken",
            "Broken",
            callback=lambda: None,
            enabled_when=Mock(side_effect=RuntimeError("broken")),
        )
        self.api.add_toolbar_item(broken)
        with self.assertLogs("setuav_studio.shell", level="ERROR"):
            self.window._refresh_toolbar_action_states()
        self.assertFalse(self.window._toolbar_actions["broken"].isEnabled())

        replacement = ToolbarContribution("callback", "Replacement", callback=lambda: None)
        self.api.add_toolbar_item(replacement)
        self.assertEqual(self.window._toolbar_actions["callback"].toolTip(), "Replacement")
        self.api.remove_toolbar_item("menu")
        self.api.remove_toolbar_item("save")

    def test_toolbar_groups_follow_workspace_and_remove_obsolete_bars(self) -> None:
        self.api.add_workspace(WorkspaceContribution("design", "Design"))
        self.api.add_workspace(WorkspaceContribution("analysis", "Analysis"))
        self.api.add_toolbar_item(
            ToolbarContribution(
                "design-tool",
                "Design Tool",
                callback=lambda: None,
                group="design",
                workspace_id="design",
            )
        )
        self.api.add_toolbar_item(
            ToolbarContribution(
                "analysis-tool",
                "Analysis Tool",
                callback=lambda: None,
                group="analysis",
                workspace_id="analysis",
            )
        )

        self.api.switch_workspace("design")
        self.assertFalse(self.window._toolset_bars["design"].isHidden())
        self.api.switch_workspace("analysis")
        self.assertFalse(self.window._toolset_bars["analysis"].isHidden())
        self.assertTrue(self.window._toolset_bars["design"].isHidden())

        self.api.remove_toolbar_item("design-tool")
        self.assertNotIn("design", self.window._toolset_bars)

    def test_late_command_registration_is_resolved_during_toolbar_rebuild(self) -> None:
        contribution = ToolbarContribution(
            "late",
            "Late Command",
            command="plugin.command",
            icon="component",
        )
        self.api.add_toolbar_item(contribution)
        self.assertNotIn("late", self.window._toolbar_actions)

        command = QAction("Command", self.window)
        self.window._command_actions["plugin.command"] = command
        self.window._rebuild_toolbar_tools()
        self.assertIs(self.window._toolbar_actions["late"], command)
        self.assertEqual(command.toolTip(), "Late Command")
        self.assertFalse(command.icon().isNull())

    def test_panels_sync_visibility_wrap_content_and_remove_safely(self) -> None:
        self.api.add_workspace(WorkspaceContribution("design", "Design"))
        self.api.switch_workspace("design")
        self.api.add_panel(
            PanelContribution(
                "analysis-panel",
                "Analysis",
                QWidget,
                workspace_id="analysis",
            )
        )
        dock = self.window._panels["analysis-panel"][1]
        self.assertTrue(dock.isHidden())
        self.assertEqual(dock.widget().objectName(), "studioDockPanel")

        self.window._sync_panel_action("missing")
        self.window._update_panel_action_icon("missing")
        self.window.show()
        dock.show()
        self.app.processEvents()
        self.window._sync_panel_action("analysis-panel")
        self.assertTrue(self.window._panel_actions["analysis-panel"].isChecked())
        self.window._panel_actions["analysis-panel"].setChecked(False)
        self.assertTrue(dock.isHidden())

        self.window._remove_panel("missing")
        self.api.remove_panel("analysis-panel")
        self.assertNotIn("analysis-panel", self.window._panels)

    def test_restore_layout_selects_saved_current_and_default_workspaces(self) -> None:
        self.api.add_workspace(WorkspaceContribution("saved", "Saved"))
        self.api.add_workspace(WorkspaceContribution("studio.workspace.design", "Design"))
        with (
            patch("setuav_studio.shell.QSettings", _FakeSettings),
            patch.object(self.window, "restoreGeometry") as restore_geometry,
            patch.object(self.window, "restore_workspace_layout") as restore_workspace,
        ):
            _FakeSettings.values["main_window/geometry"] = b"geometry"
            self.window.restore_window_layout()
        restore_geometry.assert_called_once_with(b"geometry")
        restore_workspace.assert_called_once()

        with patch("setuav_studio.shell.QSettings", _FakeSettings):
            _FakeSettings.values["active_workspace"] = "saved"
            self.window.restore_workspace_layout()
            self.assertEqual(self.api.current_workspace_id, "saved")
            _FakeSettings.values["active_workspace"] = "missing"
            self.api.current_workspace_id = "saved"
            self.window.restore_workspace_layout()
            self.api.current_workspace_id = None
            self.window.restore_workspace_layout()
            self.assertEqual(self.api.current_workspace_id, "studio.workspace.design")

    def test_workspace_switch_persists_previous_state_and_restores_or_defaults(self) -> None:
        self.api.add_workspace(WorkspaceContribution("one", "One", order=20))
        self.api.add_workspace(WorkspaceContribution("two", "Two", order=10))
        with (
            patch("setuav_studio.shell.QSettings", _FakeSettings),
            patch.object(self.window, "saveState", return_value=b"state"),
            patch.object(self.window, "restoreState") as restore_state,
            patch.object(self.window, "_apply_default_workspace_layout") as apply_default,
        ):
            self.window._switch_workspace("missing")
            self.api.switch_workspace("one")
            apply_default.assert_called_with("one")
            _FakeSettings.values["workspace_perspective/two"] = b"saved-two"
            self.api.switch_workspace("two")
        restore_state.assert_called_once_with(b"saved-two", self.window._LAYOUT_VERSION)
        self.assertEqual(self.window._workspace_states["one"], b"state")
        self.assertFalse(self.window._restoring_workspace_layout)

    def test_saved_workspace_restore_hides_panels_from_other_workspaces(self) -> None:
        self.api.add_workspace(WorkspaceContribution("one", "One"))
        self.api.add_panel(PanelContribution("other", "Other", QWidget, workspace_id="other"))
        self.window._workspace_states["one"] = b"state"
        with patch.object(self.window, "restoreState", return_value=True):
            self.window._switch_workspace("one")
        self.assertTrue(self.window._panels["other"][1].isHidden())

    def test_workspace_removal_cleans_string_and_list_scoped_panels(self) -> None:
        with patch("setuav_studio.shell.QSettings", _FakeSettings):
            self.api.add_workspace(WorkspaceContribution("remove", "Remove"))
            self.api.add_panel(
                PanelContribution("single", "Single", QWidget, workspace_id="remove")
            )
            self.api.add_panel(
                PanelContribution("multiple", "Multiple", QWidget, workspace_id=["remove", "keep"])
            )
            self.window._remove_workspace("missing")
            self.api.remove_workspace("remove")
        self.assertNotIn("single", self.window._panels)
        self.assertNotIn("multiple", self.window._panels)

    def test_layout_save_scheduling_and_dock_event_filter(self) -> None:
        self.window._schedule_workspace_layout_save()
        self.window._layout_persistence_enabled = True
        self.window._current_workspace_id = "design"
        self.window._restoring_workspace_layout = True
        self.window._schedule_workspace_layout_save()
        self.window._restoring_workspace_layout = False

        with patch("setuav_studio.shell.QTimer.singleShot") as single_shot:
            self.window._schedule_workspace_layout_save()
            self.window._schedule_workspace_layout_save()
        single_shot.assert_called_once()

        with (
            patch("setuav_studio.shell.QSettings", _FakeSettings),
            patch.object(self.window, "saveState", return_value=b"state"),
        ):
            self.window._save_current_workspace_layout()
            self.assertEqual(_FakeSettings.values["workspace_perspective/design"], b"state")
            self.window._current_workspace_id = None
            self.window._save_current_workspace_layout()

        dock = QDockWidget()
        self.addCleanup(dock.deleteLater)
        with patch.object(self.window, "_schedule_workspace_layout_save") as schedule:
            self.window.eventFilter(dock, QEvent(QEvent.Type.Resize))
            self.window.eventFilter(QWidget(), QEvent(QEvent.Type.User))
        schedule.assert_called_once()
        self.window._enable_layout_persistence()
        self.assertTrue(self.window._layout_persistence_enabled)

    def test_default_layout_branches_cover_all_builtin_workspaces(self) -> None:
        panel_ids = (
            "project.explorer",
            "studio.viewer.opengl",
            "studio.properties",
            "propulsion.controls_dock",
            "propulsion.results_dock",
            "propulsion.charts_dock",
            "aerodynamics.controls_dock",
            "aerodynamics.charts_dock",
            "aerodynamics.results_dock",
            "flight_performance.controls_dock",
            "flight_performance.charts_dock",
            "flight_performance.results_dock",
            "weight_balance.view_dock",
            "weight_balance.results_dock",
        )
        for panel_id in panel_ids:
            self.api.add_panel(PanelContribution(panel_id, panel_id, QWidget))
        self.api.add_panel(
            PanelContribution("other", "Other", QWidget, workspace_id="other-workspace")
        )

        for workspace_id in (
            "studio.workspace.design",
            "studio.workspace.propulsion",
            "studio.workspace.aerodynamics",
            "studio.workspace.flight_performance",
            "studio.workspace.weight_balance",
            "custom",
        ):
            self.window._apply_default_workspace_layout(workspace_id)
        self.assertTrue(self.window._panels["other"][1].isHidden())

        for panel_id in (
            "propulsion.charts_dock",
            "aerodynamics.charts_dock",
            "flight_performance.charts_dock",
        ):
            self.window._remove_panel(panel_id)
        for workspace_id in (
            "studio.workspace.propulsion",
            "studio.workspace.aerodynamics",
            "studio.workspace.flight_performance",
        ):
            self.window._apply_default_workspace_layout(workspace_id)

    def test_invalid_window_guards_and_rejected_close_event_are_safe(self) -> None:
        event = QCloseEvent()
        with patch.object(self.window, "_confirm_project_close", return_value=False):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())

        for callback, argument in (
            (self.window._update_window_title, None),
            (self.window._on_modified_changed, False),
            (self.window._on_project_content_changed, self._project()),
        ):
            with patch("setuav_studio.shell.shiboken6.isValid", return_value=False):
                callback() if argument is None else callback(argument)
            with (
                patch(
                    "setuav_studio.shell.shiboken6.isValid",
                    side_effect=RuntimeError("deleted"),
                ),
                self.assertLogs("setuav_studio.shell", level="DEBUG"),
            ):
                callback() if argument is None else callback(argument)

        self.window._on_project_content_changed(self._project())

    def test_settings_dialog_cancel_and_accept_apply_all_changes(self) -> None:
        cancelled = Mock()
        cancelled.exec.return_value = QDialog.DialogCode.Rejected
        accepted = Mock()
        accepted.exec.return_value = QDialog.DialogCode.Accepted
        accepted.values.return_value = StudioSettings(theme_mode="light", recent_project_limit=3)

        with patch("setuav_studio.shell.SettingsDialog", side_effect=[cancelled, accepted]):
            self.window._open_settings()
            with (
                patch.object(StudioSettings, "save") as save,
                patch.object(self.window, "_switch_theme") as switch_theme,
                patch.object(self.window, "_trim_recent_projects") as trim,
                patch.object(self.window, "_update_recent_menu") as update_recent,
            ):
                self.window._open_settings()
        save.assert_called_once()
        accepted.apply_plugin_pages.assert_called_once()
        switch_theme.assert_called_once_with("light")
        trim.assert_called_once_with(3)
        update_recent.assert_called_once()

    def test_undo_redo_labels_and_action_state_follow_project(self) -> None:
        self.window._set_undo_text("")
        self.window._set_redo_text("")
        self.assertEqual(self.window._undo_action.text(), "Undo")
        self.assertEqual(self.window._redo_action.text(), "Redo")
        self.window._set_undo_text("Rename")
        self.window._set_redo_text("Delete")
        self.assertEqual(self.window._undo_action.text(), "Undo Rename")
        self.assertEqual(self.window._redo_action.text(), "Redo Delete")

        self.window._project = None
        self.window._update_actions()
        self.assertFalse(self.window._save_action.isEnabled())
        self.window._project = self._project()
        self.window._update_actions()
        self.assertTrue(self.window._save_action.isEnabled())

    @staticmethod
    def _project() -> object:
        from setuav_studio.project import ProjectDocument

        return ProjectDocument(Path("project.json"), "json", {"name": "Demo"})


if __name__ == "__main__":
    unittest.main()
