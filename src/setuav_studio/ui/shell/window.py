from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QSettings
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from setuav_studio_sdk import PanelContribution

from .actions import ActionManager
from .layout_manager import LayoutManager
from .native_registrations import register_native_contributions
from .project_controller import ProjectController
from .status_bar import StatusBarManager
from .toolbar_manager import ToolbarManager

if TYPE_CHECKING:
    from pathlib import Path

    from setuav_studio.api import PluginManager, StudioAPI
    from setuav_studio.project import ProjectDocument
    from setuav_studio_sdk import (
        ActionContribution,
        ToolbarContribution,
        WorkspaceContribution,
    )

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application shell coordinating workspace, toolbar, project, and actions."""

    _LAYOUT_VERSION = LayoutManager.LAYOUT_VERSION
    _LAYOUT_DEFAULTS_KEY = LayoutManager.LAYOUT_DEFAULTS_KEY

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._host = api._host
        self._project: ProjectDocument | None = None
        self._panels: dict[str, tuple[PanelContribution, QDockWidget]] = {}
        self._current_workspace_id: str | None = None

        # Register built-in native UI contributions (Explorer, Properties, Parameters, Editors, Settings)
        register_native_contributions(api)

        self.setDockNestingEnabled(True)
        central_anchor = QWidget(self)
        central_anchor.setObjectName("studio.central-anchor")
        self.setCentralWidget(central_anchor)

        # Initialize sub-managers
        self._project_controller = ProjectController(self, api)
        self._toolbar_manager = ToolbarManager(self, api)
        self._layout_manager = LayoutManager(self, api)
        self._status_manager = StatusBarManager(self, api)
        self._action_manager = ActionManager(self, api)
        self._toolbar_manager.setup_standard_actions(
            self._action_manager.new_project_action,
            self._action_manager.open_folder_action,
            self._action_manager.save_action,
            self._action_manager.save_as_action,
            self._action_manager.undo_action,
            self._action_manager.redo_action,
        )

        # Expose sub-manager properties for backward-compatibility & inspection
        self._standard_toolbar = self._toolbar_manager.standard_toolbar
        self._workspaces = self._toolbar_manager.workspaces
        self._toolbar_contributions = self._toolbar_manager.toolbar_contributions
        self._toolbar_actions = self._toolbar_manager.toolbar_actions
        self._toolbar_menu_actions = self._toolbar_manager.toolbar_menu_actions
        self._owned_toolbar_actions = self._toolbar_manager.owned_toolbar_actions
        self._toolset_bars = self._toolbar_manager.toolset_bars
        self._workspace_toolbar = self._toolbar_manager.workspace_toolbar
        self._configuration_toolbar = self._toolbar_manager.configuration_toolbar

        self._menus = self._action_manager.menus
        self._command_actions = self._action_manager.command_actions
        self._panel_actions = self._action_manager.panel_actions
        self._file_menu = self._action_manager.file_menu
        self._view_menu = self._action_manager.view_menu
        self._tools_menu = self._action_manager.tools_menu
        self._help_menu = self._action_manager.help_menu
        self._recent_menu = self._action_manager.recent_menu
        self._new_project_action = self._action_manager.new_project_action
        self._open_folder_action = self._action_manager.open_folder_action
        self._save_action = self._action_manager.save_action
        self._save_as_action = self._action_manager.save_as_action
        self._exit_action = self._action_manager.exit_action
        self._undo_action = self._action_manager.undo_action
        self._redo_action = self._action_manager.redo_action
        self._settings_action = self._action_manager.settings_action
        self._constraints_action = self._action_manager.constraints_action
        self._plugin_manager_action = self._action_manager.plugin_manager_action
        self._about_action = self._action_manager.about_action
        self._dark_theme_action = self._action_manager.dark_theme_action
        self._light_theme_action = self._action_manager.light_theme_action
        self._blender_theme_action = self._action_manager.blender_theme_action
        self._github_dark_theme_action = self._action_manager.github_dark_theme_action
        self._github_light_theme_action = self._action_manager.github_light_theme_action
        self._monokai_theme_action = self._action_manager.monokai_theme_action
        self._nord_theme_action = self._action_manager.nord_theme_action

        self._workspace_states = self._layout_manager.workspace_states
        self._status_label = self._status_manager.status_label
        self._progress_bar = self._status_manager.progress_bar
        self._log_button = self._status_manager.log_button
        self._degraded_badge = self._status_manager.degraded_badge

        # Host bridge bindings
        self._host.bind_panel_handlers(self._add_panel, self._remove_panel)
        self._host.bind_workspace_handlers(
            self._add_workspace,
            self._switch_workspace,
            self._remove_workspace,
        )
        self._host.bind_toolbar_handlers(
            self._add_toolbar_item,
            self._remove_toolbar_item,
        )
        self._host.bind_action_handlers(self._add_action, self._remove_action)

        self.setWindowTitle("Setuav Studio")
        self.resize(1200, 800)
        self.setCentralWidget(None)

        self._api.on_modified_changed(self._on_modified_changed)
        self._api.on_project_content_changed(self._on_project_content_changed)
        self._api.on_selection_changed(self._on_toolbar_context_changed)
        self.destroyed.connect(self._detach_api_listeners)

    @property
    def _log_window(self) -> QDialog | None:
        return self._status_manager._log_window

    @_log_window.setter
    def _log_window(self, value: QDialog | None) -> None:
        self._status_manager._log_window = value

    @property
    def _restoring_workspace_layout(self) -> bool:
        return self._layout_manager.restoring_workspace_layout

    @_restoring_workspace_layout.setter
    def _restoring_workspace_layout(self, value: bool) -> None:
        self._layout_manager.restoring_workspace_layout = value

    @property
    def _layout_persistence_enabled(self) -> bool:
        return self._layout_manager.layout_persistence_enabled

    @_layout_persistence_enabled.setter
    def _layout_persistence_enabled(self, value: bool) -> None:
        self._layout_manager.layout_persistence_enabled = value

    @property
    def _layout_save_scheduled(self) -> bool:
        return self._layout_manager.layout_save_scheduled

    @_layout_save_scheduled.setter
    def _layout_save_scheduled(self, value: bool) -> None:
        self._layout_manager.layout_save_scheduled = value

    # Panel Management
    def _add_panel(self, contribution: PanelContribution) -> None:
        dock = QDockWidget(contribution.title, self)
        dock.setFont(QApplication.font())
        dock.setObjectName(contribution.id)
        dock.setWidget(self._wrap_panel(contribution.factory()))
        self.addDockWidget(contribution.area, dock)
        self._panels[contribution.id] = (contribution, dock)

        action = QAction(contribution.title, self)
        action.setCheckable(True)
        action.setChecked(dock.isVisible())
        action.toggled.connect(lambda checked, d=dock: d.setVisible(checked))
        action.toggled.connect(
            lambda _checked, pid=contribution.id: self._update_panel_action_icon(pid)
        )
        dock.visibilityChanged.connect(
            lambda _visible=False, pid=contribution.id: self._sync_panel_action(pid)
        )
        dock.dockLocationChanged.connect(self._schedule_workspace_layout_save)
        dock.topLevelChanged.connect(self._schedule_workspace_layout_save)
        dock.visibilityChanged.connect(self._schedule_workspace_layout_save)
        dock.installEventFilter(self)
        self._panel_actions[contribution.id] = action
        self._update_panel_action_icon(contribution.id)

        ws_id = self._current_workspace_id or self._api.current_workspace_id
        if not contribution.is_in_workspace(ws_id):
            dock.hide()

        self._update_view_menu(ws_id)

    def _remove_panel(self, panel_id: str) -> None:
        entry = self._panels.pop(panel_id, None)
        if entry is None:
            return
        _, dock = entry
        dock.close()
        dock.deleteLater()
        action = self._panel_actions.pop(panel_id, None)
        if action is not None:
            action.deleteLater()
        self._update_view_menu(self._current_workspace_id)

    @staticmethod
    def _wrap_panel(content: QWidget) -> QWidget:
        container = QWidget()
        container.setObjectName("studioDockPanel")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(content)
        return container

    # Project Controller Delegations
    def _new_project(self) -> bool:
        return self._project_controller.new_project()

    def _open_project_folder(self) -> None:
        self._project_controller.open_project_folder()

    def open_project(self, path: str) -> bool:
        return self._project_controller.open_project(path)

    def _activate_project(self, project: ProjectDocument, *, confirm_close: bool = True) -> bool:
        return self._project_controller.activate_project(project, confirm_close=confirm_close)

    def _append_unsaved_aerodynamic_analyses(
        self, changes: list[str], disk_document: ProjectDocument | None
    ) -> None:
        self._project_controller.append_unsaved_aerodynamic_analyses(changes, disk_document)

    def _append_unsaved_performance_analyses(
        self, changes: list[str], disk_document: ProjectDocument | None
    ) -> None:
        self._project_controller.append_unsaved_performance_analyses(changes, disk_document)

    @staticmethod
    def _append_unsaved_analyses(
        changes: list[str],
        disk_entries: list[dict[str, Any]],
        current_entries: list[dict[str, Any]],
        fallback_name: str,
    ) -> None:
        ProjectController.append_unsaved_analyses(
            changes, disk_entries, current_entries, fallback_name
        )

    def open_last_project(self) -> None:
        self._project_controller.open_last_project()

    def save_project(self) -> bool:
        return self._project_controller.save_project()

    def save_project_as(self) -> bool:
        return self._project_controller.save_project_as()

    def _confirm_project_close(self) -> bool:
        return self._project_controller.confirm_project_close()

    def _collect_unsaved_changes(self) -> list[str]:
        return self._project_controller.collect_unsaved_changes()

    def _update_window_title(self) -> None:
        self._project_controller.update_window_title()

    def _recent_projects(self) -> list[str]:
        if hasattr(self, "_project_controller"):
            return self._project_controller.recent_projects()
        return []

    def _add_recent_project(self, path: Path) -> None:
        self._project_controller.add_recent_project(path)

    def _clear_recent_projects(self) -> None:
        self._project_controller.clear_recent_projects()

    def _trim_recent_projects(self, limit: int) -> None:
        self._project_controller.trim_recent_projects(limit)

    # Layout Manager Delegations
    def restore_window_layout(self) -> None:
        self._layout_manager.restore_window_layout()

    def restore_window_geometry(self) -> None:
        self._layout_manager.restore_window_geometry()

    def restore_workspace_layout(self) -> None:
        self._layout_manager.restore_workspace_layout()

    def _reset_outdated_workspace_perspectives(self, settings: QSettings) -> None:
        self._layout_manager.reset_outdated_workspace_perspectives(settings)

    def _switch_workspace(self, workspace_id: str) -> None:
        self._layout_manager.switch_workspace(workspace_id)

    def _schedule_workspace_layout_save(self, *_args: Any) -> None:
        self._layout_manager.schedule_workspace_layout_save()

    def _save_current_workspace_layout(self) -> None:
        self._layout_manager.save_current_workspace_layout()

    def _enable_layout_persistence(self) -> None:
        self._layout_manager.enable_layout_persistence()

    def _apply_default_workspace_layout(self, workspace_id: str) -> None:
        self._layout_manager.apply_default_workspace_layout(workspace_id)

    def _hide_panels_outside_workspace(self, workspace_id: str) -> None:
        self._layout_manager.hide_panels_outside_workspace(workspace_id)

    def _dock(self, panel_id: str) -> QDockWidget | None:
        return self._layout_manager.dock(panel_id)

    def _resize_visible_docks(
        self, docks: tuple[QDockWidget | None, ...], widths: list[int]
    ) -> None:
        self._layout_manager.resize_visible_docks(docks, widths)

    def _reset_current_workspace_layout(self) -> None:
        self._layout_manager.reset_current_workspace_layout()

    # Toolbar Manager Delegations
    def _add_toolbar_item(self, contribution: ToolbarContribution) -> None:
        self._toolbar_manager.add_toolbar_item(contribution)

    def _remove_toolbar_item(self, contribution_id: str) -> None:
        self._toolbar_manager.remove_toolbar_item(contribution_id)

    def _refresh_toolbar_action_states(self) -> None:
        self._toolbar_manager.refresh_toolbar_action_states()

    def _rebuild_toolbar_tools(self) -> None:
        self._toolbar_manager.rebuild_toolbar_tools()

    def _update_main_toolbar_style(self) -> None:
        self._toolbar_manager.update_main_toolbar_style()

    def _update_toolbar_contribution_icons(self) -> None:
        self._toolbar_manager.update_toolbar_contribution_icons()

    def _refresh_workspace_combo(self) -> None:
        self._toolbar_manager.refresh_workspace_combo()

    def _add_workspace(self, contribution: WorkspaceContribution) -> None:
        self._toolbar_manager.add_workspace(contribution)

    def _remove_workspace(self, workspace_id: str) -> None:
        self._toolbar_manager.remove_workspace(workspace_id)

    # Action Manager Delegations
    def _switch_theme(self, mode: str) -> None:
        self._action_manager.switch_theme(mode)

    def _update_all_icons(self) -> None:
        self._action_manager.update_all_icons()

    def _populate_view_menu(self, workspace_id: str | None = None) -> None:
        self._action_manager.populate_view_menu(workspace_id)

    def _update_view_menu(self, workspace_id: str | None) -> None:
        self._action_manager.update_view_menu(workspace_id)

    def _update_panel_action_icon(self, panel_id: str) -> None:
        self._action_manager.update_panel_action_icon(panel_id)

    def _sync_panel_action(self, panel_id: str) -> None:
        self._action_manager.sync_panel_action(panel_id)

    def _update_actions(self) -> None:
        self._action_manager.update_actions()

    def _set_undo_text(self, text: str) -> None:
        self._action_manager.set_undo_text(text)

    def _set_redo_text(self, text: str) -> None:
        self._action_manager.set_redo_text(text)

    def _update_recent_menu(self) -> None:
        self._action_manager.update_recent_menu()

    def _open_settings(self) -> None:
        self._action_manager.open_settings()

    def _open_about(self) -> None:
        self._action_manager.open_about()

    def _open_constraints(self) -> None:
        self._action_manager.open_constraints()

    def bind_plugin_manager(self, manager: PluginManager) -> None:
        self._action_manager.bind_plugin_manager(manager)

    def _open_plugin_manager(self) -> None:
        self._action_manager.open_plugin_manager()

    def _add_action(self, contribution: ActionContribution) -> None:
        self._action_manager.add_action(contribution)

    def _remove_action(self, menu_path: str, title: str) -> None:
        self._action_manager.remove_action(menu_path, title)

    # Status Bar Delegations
    def _show_status_message(
        self, message: str, level: str = "info", timeout_ms: int = 5000
    ) -> None:
        self._status_manager.show_status_message(message, level, timeout_ms)

    def _show_progress(self, completed: int, total: int, label: str = "") -> None:
        self._status_manager.show_progress(completed, total, label)

    def _clear_status_message(self) -> None:
        self._status_manager.clear_status_message()

    def _refresh_status_color(self) -> None:
        self._status_manager.refresh_status_color()

    def _open_log_window(self) -> None:
        self._status_manager.open_log_window()

    def _open_task_monitor_window(self) -> None:
        self._status_manager.open_task_monitor_window()

    def open_task_monitor_window(self) -> None:
        self._status_manager.open_task_monitor_window()

    def _show_degraded_details(self) -> None:
        self._status_manager.show_degraded_details()

    # Event Handlers & Lifecycle
    def _on_modified_changed(self, _modified: bool) -> None:
        self._update_window_title()

    def _on_project_content_changed(self, _project: ProjectDocument) -> None:
        self._update_window_title()
        self._refresh_toolbar_action_states()

    def _on_toolbar_context_changed(self, _selection: object | None) -> None:
        self._refresh_toolbar_action_states()

    def _detach_api_listeners(self, *_args: object) -> None:
        self._api.remove_modified_listener(self._on_modified_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)
        self._api.remove_selection_listener(self._on_toolbar_context_changed)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._schedule_workspace_layout_save()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if not self._layout_persistence_enabled:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._enable_layout_persistence)

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        if isinstance(watched, QDockWidget) and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            self._schedule_workspace_layout_save()
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_project_close():
            event.ignore()
            return

        self._detach_api_listeners()
        settings = QSettings()
        settings.setValue("main_window/geometry", self.saveGeometry())
        if self._current_workspace_id is not None:
            self._save_current_workspace_layout()
            settings.setValue("active_workspace", self._current_workspace_id)

        for _, dock in self._panels.values():
            try:
                dock.close()
            except Exception as exc:
                logger.debug("Error closing dock widget: %s", exc)

        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()


StudioShell = MainWindow

__all__ = ["MainWindow", "StudioShell"]
