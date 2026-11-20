from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QByteArray, QEvent, QSettings, QTimer
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
    from setuav_studio.api import (
        StudioAPI,
    )
    from setuav_studio.project import ProjectDocument

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application shell coordinating workbench layout, toolbar, project, and actions."""

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._host = api._host
        self._panels: dict[str, tuple[PanelContribution, QDockWidget]] = {}
        self._normal_geometry: QByteArray | None = None
        self._normal_dock_state: QByteArray | None = None
        self._was_maximized: bool = False
        # The normal geometry is recorded a moment after a resize or move. Entering
        # full screen or maximizing can resize the window before its state changes;
        # the state change cancels the pending record, so that size is never kept.
        self._normal_capture = QTimer(self)
        self._normal_capture.setSingleShot(True)
        self._normal_capture.setInterval(200)
        self._normal_capture.timeout.connect(self._capture_normal_state)

        # Register built-in native UI contributions (Explorer, Properties, Parameters, Editors, Settings)
        register_native_contributions(api)

        self.setDockNestingEnabled(True)
        # Every panel is a dock widget. The central widget stays hidden so the docks
        # share the whole window instead of leaving an empty gap between them.
        central_anchor = QWidget(self)
        central_anchor.setObjectName("studio.central-anchor")
        self.setCentralWidget(central_anchor)
        central_anchor.hide()

        # Initialize sub-managers
        self.project_controller = ProjectController(self, api)
        self.toolbar_manager = ToolbarManager(self, api)
        self.layout_manager = LayoutManager(self, api)
        self.status_manager = StatusBarManager(self, api)
        self.action_manager = ActionManager(self, api)
        self.toolbar_manager.setup_standard_actions(
            self.action_manager.new_project_action,
            self.action_manager.open_folder_action,
            self.action_manager.save_action,
            self.action_manager.save_as_action,
            self.action_manager.undo_action,
            self.action_manager.redo_action,
        )

        # Host bridge bindings
        self._host.bind_panel_handlers(
            self._register_panel, self._unregister_panel, self._show_panel_by_id
        )
        self._host.bind_toolbar_handlers(
            self.toolbar_manager.register_toolbar_item,
            self.toolbar_manager.unregister_toolbar_item,
            self.toolbar_manager.update_toolbar_states,
        )
        self._host.bind_action_handlers(
            self.action_manager.register_action, self.action_manager.unregister_action
        )

        self.setWindowTitle("Setuav Studio")
        self.resize(1280, 720)

        self._api.on_modified_changed(self._on_modified_changed)
        self._api.on_project_content_changed(self._on_project_content_changed)
        self._api.on_selection_changed(self._on_toolbar_context_changed)
        from setuav_studio.ui.widget.table import ExpressionFocusTracker

        ExpressionFocusTracker.add_listener(self.toolbar_manager.update_toolbar_states)
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
            lambda _checked, pid=contribution.id: self.action_manager.update_panel_action_icon(pid)
        )
        dock.visibilityChanged.connect(
            lambda _visible=False, pid=contribution.id: self.action_manager.sync_panel_action(pid)
        )
        dock.dockLocationChanged.connect(self.layout_manager.schedule_layout_save)
        dock.topLevelChanged.connect(self.layout_manager.schedule_layout_save)
        dock.visibilityChanged.connect(self.layout_manager.schedule_layout_save)
        dock.installEventFilter(self)
        self.action_manager.panel_actions[contribution.id] = action
        self.action_manager.update_panel_action_icon(contribution.id)

        self.action_manager.update_view_menu()

    def _unregister_panel(self, panel_id: str) -> None:
        entry = self._panels.pop(panel_id, None)
        if entry is None:
            return
        _, dock = entry
        dock.close()
        dock.deleteLater()
        action = self.action_manager.panel_actions.pop(panel_id, None)
        if action is not None:
            action.deleteLater()
        self.action_manager.update_view_menu()

    def _show_panel_by_id(self, panel_id: str) -> None:
        dock = self.layout_manager.dock(panel_id)
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

    # Event Handlers & Lifecycle
    def _on_modified_changed(self, _modified: bool) -> None:
        self.project_controller.update_window_title()

    def _on_project_content_changed(self, project: ProjectDocument) -> None:
        self.project_controller.update_window_title()
        self.toolbar_manager.update_toolbar_states()
        self.status_manager.evaluate_problems(project)

    def _on_toolbar_context_changed(self, _selection: object | None) -> None:
        self.toolbar_manager.update_toolbar_states()

    def _detach_api_listeners(self, *_args: object) -> None:
        self._api.remove_modified_listener(self._on_modified_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)
        self._api.remove_selection_listener(self._on_toolbar_context_changed)
        from setuav_studio.ui.widget.table import ExpressionFocusTracker

        ExpressionFocusTracker.remove_listener(self.toolbar_manager.update_toolbar_states)

    def _is_normal_state(self) -> bool:
        return not (self.isMaximized() or self.isFullScreen() or self.isMinimized())

    def _capture_normal_state(self) -> None:
        if self._is_normal_state():
            self._normal_geometry = self.saveGeometry()
            self._normal_dock_state = self.saveState(LayoutManager.LAYOUT_VERSION)

    def _restore_normal_state(self) -> None:
        if not self._is_normal_state():
            return
        if self._normal_geometry is not None:
            self.restoreGeometry(self._normal_geometry)
        if self._normal_dock_state is not None:
            self.restoreState(self._normal_dock_state, LayoutManager.LAYOUT_VERSION)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if self._is_normal_state():
            self._normal_capture.start()
        self.layout_manager.schedule_layout_save()

    def moveEvent(self, event: Any) -> None:
        super().moveEvent(event)
        if self._is_normal_state():
            self._normal_capture.start()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            is_max = self.isMaximized() or self.isFullScreen()
            if is_max:
                self._normal_capture.stop()
            elif self._was_maximized:
                # Restore after the window system has applied the new state.
                QTimer.singleShot(0, self._restore_normal_state)
            self._was_maximized = is_max
        super().changeEvent(event)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if not self.isMaximized() and not self.isFullScreen():
            if self._normal_geometry is None:
                self._normal_geometry = self.saveGeometry()
            if self._normal_dock_state is None:
                self._normal_dock_state = self.saveState(LayoutManager.LAYOUT_VERSION)
        if not self.layout_manager.layout_persistence_enabled:
            QTimer.singleShot(0, self.layout_manager.enable_layout_persistence)

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        if isinstance(watched, QDockWidget) and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            self.layout_manager.schedule_layout_save()
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.project_controller.confirm_project_close():
            event.ignore()
            return

        project = self.project_controller.project
        if project is not None:
            self._api.publish(StudioEvents.PROJECT_CLOSED, project)
            self.project_controller.project = None

        self._detach_api_listeners()
        settings = QSettings()
        if not self.isMaximized() and not self.isFullScreen():
            settings.setValue("main_window/geometry", self.saveGeometry())
        elif self._normal_geometry is not None:
            settings.setValue("main_window/geometry", self._normal_geometry)
        self.layout_manager.save_layout()

        for _, dock in self._panels.values():
            dock.close()

        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()


__all__ = ["MainWindow"]
