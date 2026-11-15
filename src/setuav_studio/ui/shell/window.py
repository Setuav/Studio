from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QByteArray, QEvent, QSettings
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import PanelContribution, StudioEvents

from .actions import ActionManager
from .layout_manager import LayoutManager
from .native_registrations import register_native_contributions
from .project_controller import ProjectController
from .status_bar import StatusBarManager
from .toolbar_manager import ToolbarManager

if TYPE_CHECKING:
    from pathlib import Path

    from setuav_studio.api import (
        ActionContribution,
        StudioAPI,
        ToolbarContribution,
    )
    from setuav_studio.plugin import PluginManager
    from setuav_studio.project import ProjectDocument

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application shell coordinating workbench layout, toolbar, project, and actions."""

    _LAYOUT_VERSION = LayoutManager.LAYOUT_VERSION
    _LAYOUT_DEFAULTS_KEY = LayoutManager.LAYOUT_DEFAULTS_KEY

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._host = api._host
        self._project: ProjectDocument | None = None
        self._panels: dict[str, tuple[PanelContribution, QDockWidget]] = {}
        self._normal_geometry: QByteArray | None = None
        self._normal_dock_state: QByteArray | None = None
        self._was_maximized: bool = False

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

        # Host bridge bindings
        self._host.bind_panel_handlers(
            self._register_panel, self._unregister_panel, self._show_panel_by_id
        )
        self._host.bind_toolbar_handlers(
            self._register_toolbar_item,
            self._unregister_toolbar_item,
            self._refresh_toolbar_action_states,
        )
        self._host.bind_action_handlers(self._register_action, self._unregister_action)

        self.setWindowTitle("Setuav Studio")
        self.resize(1280, 720)
        self.setCentralWidget(None)  # type: ignore[arg-type]

        self._api.on_modified_changed(self._on_modified_changed)
        self._api.on_project_content_changed(self._on_project_content_changed)
        self._api.on_selection_changed(self._on_toolbar_context_changed)
        from setuav_studio.ui.widget.table import ExpressionFocusTracker

        ExpressionFocusTracker.add_listener(self._refresh_toolbar_action_states)
        self.destroyed.connect(self._detach_api_listeners)

    # Panel Management
    def _register_panel(self, contribution: PanelContribution) -> None:
        if contribution.id in self._panels:
            logger.info(
                "Panel '%s' already registered, skipping duplicate contribution.",
                contribution.id,
            )
            return
        dock = QDockWidget(contribution.title, self)
        dock.setFont(QApplication.font())
        dock.setObjectName(contribution.id)
        dock.setWidget(self._wrap_panel(contribution.factory()))
        self.addDockWidget(contribution.area, dock)
        if not contribution.default_visible:
            dock.hide()
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
        dock.dockLocationChanged.connect(self._schedule_layout_save)
        dock.topLevelChanged.connect(self._schedule_layout_save)
        dock.visibilityChanged.connect(self._schedule_layout_save)
        dock.installEventFilter(self)
        self._action_manager.panel_actions[contribution.id] = action
        self._update_panel_action_icon(contribution.id)

        self._update_view_menu()

    def _unregister_panel(self, panel_id: str) -> None:
        entry = self._panels.pop(panel_id, None)
        if entry is None:
            return
        _, dock = entry
        dock.close()
        dock.deleteLater()
        action = self._action_manager.panel_actions.pop(panel_id, None)
        if action is not None:
            action.deleteLater()
        self._update_view_menu()

    def _show_panel_by_id(self, panel_id: str) -> None:
        dock = self._dock(panel_id)
        if dock is not None:
            dock.show()
            dock.raise_()

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

    def _open_project_dialog(self) -> None:
        self._project_controller.open_project_dialog()

    def _open_project_folder(self) -> None:
        self._project_controller.open_project_folder()

    def open_project(self, path: str) -> bool:
        return self._project_controller.open_project(path)

    def _activate_project(self, project: ProjectDocument, *, confirm_close: bool = True) -> bool:
        return self._project_controller.activate_project(project, confirm_close=confirm_close)

    @property
    def project(self) -> ProjectDocument | None:
        return self._project

    def new_untitled_project(self) -> bool:
        return self._project_controller.new_untitled_project()

    def open_last_project(self) -> bool:
        return self._project_controller.open_last_project()

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
        return self._project_controller.recent_projects()

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

    def restore_layout(self) -> None:
        self._layout_manager.restore_dock_layout()

    def _schedule_layout_save(self, *_args: Any) -> None:
        self._layout_manager.schedule_layout_save()

    def save_layout(self) -> None:
        self._layout_manager.save_layout()

    def reset_layout(self) -> None:
        self._layout_manager.reset_layout()

    def _enable_layout_persistence(self) -> None:
        self._layout_manager.enable_layout_persistence()

    def _dock(self, panel_id: str) -> QDockWidget | None:
        return self._layout_manager.dock(panel_id)

    def _resize_visible_docks(
        self, docks: tuple[QDockWidget | None, ...], widths: list[int]
    ) -> None:
        self._layout_manager.resize_visible_docks(docks, widths)

    # Toolbar Manager Delegations
    def _register_toolbar_item(self, contribution: ToolbarContribution) -> None:
        self._toolbar_manager.register_toolbar_item(contribution)

    def _unregister_toolbar_item(self, contribution_id: str) -> None:
        self._toolbar_manager.unregister_toolbar_item(contribution_id)

    def _refresh_toolbar_action_states(self) -> None:
        self._toolbar_manager.update_toolbar_states()

    def _rebuild_toolbar_tools(self) -> None:
        self._toolbar_manager.rebuild_toolbar_tools()

    def _update_main_toolbar_style(self) -> None:
        self._toolbar_manager.update_main_toolbar_style()

    def _update_toolbar_contribution_icons(self) -> None:
        self._toolbar_manager.update_toolbar_contribution_icons()

    # Action Manager Delegations
    def _switch_theme(self, mode: str) -> None:
        self._action_manager.switch_theme(mode)

    def _update_all_icons(self) -> None:
        self._action_manager.update_all_icons()

    def _populate_view_menu(self) -> None:
        self._action_manager.populate_view_menu()

    def _update_view_menu(self) -> None:
        self._action_manager.update_view_menu()

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

    def _register_action(self, contribution: ActionContribution) -> None:
        self._action_manager.register_action(contribution)

    def _unregister_action(self, menu_path: str, title: str) -> None:
        self._action_manager.unregister_action(menu_path, title)

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

    def open_task_manager_window(self) -> None:
        self._status_manager.open_task_manager_window()

    def open_command_palette(self) -> None:
        self._action_manager.open_command_palette()

    def _show_degraded_details(self) -> None:
        self._status_manager.show_degraded_details()

    # Event Handlers & Lifecycle
    def _on_modified_changed(self, _modified: bool) -> None:
        self._update_window_title()

    def _on_project_content_changed(self, project: ProjectDocument) -> None:
        self._update_window_title()
        self._refresh_toolbar_action_states()
        self._status_manager.evaluate_problems(project)

    def _on_toolbar_context_changed(self, _selection: object | None) -> None:
        self._refresh_toolbar_action_states()

    def _detach_api_listeners(self, *_args: object) -> None:
        self._api.remove_modified_listener(self._on_modified_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)
        self._api.remove_selection_listener(self._on_toolbar_context_changed)
        from setuav_studio.ui.widget.table import ExpressionFocusTracker

        ExpressionFocusTracker.remove_listener(self._refresh_toolbar_action_states)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if not self.isMaximized() and not self.isFullScreen():
            self._normal_geometry = self.saveGeometry()
            self._normal_dock_state = self.saveState(self._LAYOUT_VERSION)
        self._schedule_layout_save()

    def moveEvent(self, event: Any) -> None:
        super().moveEvent(event)
        if not self.isMaximized() and not self.isFullScreen():
            self._normal_geometry = self.saveGeometry()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            is_max = self.isMaximized() or self.isFullScreen()
            if self._was_maximized and not is_max:
                if self._normal_geometry is not None:
                    self.restoreGeometry(self._normal_geometry)
                if self._normal_dock_state is not None:
                    self.restoreState(self._normal_dock_state, self._LAYOUT_VERSION)
            self._was_maximized = is_max
        super().changeEvent(event)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if not self.isMaximized() and not self.isFullScreen():
            if self._normal_geometry is None:
                self._normal_geometry = self.saveGeometry()
            if self._normal_dock_state is None:
                self._normal_dock_state = self.saveState(self._LAYOUT_VERSION)
        if not self._layout_manager.layout_persistence_enabled:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._enable_layout_persistence)

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        if isinstance(watched, QDockWidget) and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            self._schedule_layout_save()
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_project_close():
            event.ignore()
            return

        if self._project is not None:
            self._api.publish(StudioEvents.PROJECT_CLOSED, self._project)
            self._project = None

        self._detach_api_listeners()
        settings = QSettings()
        if not self.isMaximized() and not self.isFullScreen():
            settings.setValue("main_window/geometry", self.saveGeometry())
        elif self._normal_geometry is not None:
            settings.setValue("main_window/geometry", self._normal_geometry)
        self._layout_manager.save_layout()

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
