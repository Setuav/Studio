from pathlib import Path

import shiboken6
from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QStyle,
    QToolBar,
    QToolButton,
    QWidget,
)

from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import (
    ActionContribution,
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
)
from setuav_studio.plugins.core.settings import SettingsDialog, StudioSettings
from setuav_studio.plugins.core.theme import apply_theme
from setuav_studio.project import (
    ProjectDocument,
    ProjectOpenError,
    ProjectSaveError,
    open_project,
    save_project,
)


class DockTitleBar(QWidget):
    def __init__(self, dock: QDockWidget) -> None:
        super().__init__(dock)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(2)

        self._title = QLabel(dock.windowTitle(), self)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._title)
        layout.addStretch()

        float_button = QToolButton(self)
        float_button.setAutoRaise(True)
        float_button.setFixedSize(18, 18)
        float_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        float_button.setToolTip("Dock or undock panel")
        float_button.setIcon(get_icon("dock_float"))
        float_button.clicked.connect(
            lambda: dock.setFloating(not dock.isFloating())
        )
        layout.addWidget(float_button)

        close_button = QToolButton(self)
        close_button.setAutoRaise(True)
        close_button.setFixedSize(18, 18)
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setToolTip("Close panel")
        close_button.setIcon(get_icon("dock_close"))
        close_button.clicked.connect(dock.close)
        layout.addWidget(close_button)

        dock.windowTitleChanged.connect(self._title.setText)


class MainWindow(QMainWindow):
    _LAYOUT_VERSION = 3

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._project: ProjectDocument | None = None
        self._workspaces: dict[str, WorkspaceContribution] = {}
        self._workspace_widgets: dict[str, QWidget] = {}
        self._workspace_buttons: dict[str, QToolButton] = {}
        self._panels: dict[str, tuple[PanelContribution, QDockWidget]] = {}
        self._workspace_stack = QStackedWidget(self)
        self._workspace_dock: QDockWidget | None = None
        self.setDockNestingEnabled(True)

        self._workspace_toolbar = QToolBar("Workspaces", self)
        self._workspace_toolbar.setObjectName("studio.workspace_toolbar")
        self._workspace_toolbar.setMovable(False)
        self._workspace_toolbar.setFloatable(False)
        self._workspace_toolbar.setIconSize(QSize(15, 15))
        self._workspace_toolbar.setStyleSheet("""
            QToolBar#studio.workspace_toolbar {
                background-color: #1a1d22;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 2px 8px;
                spacing: 6px;
            }
            QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 8.5pt;
                font-weight: 600;
                color: #abb2bf;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.06);
                color: #ffffff;
            }
            QToolButton:checked {
                background-color: rgba(127, 196, 209, 0.15);
                border: 1px solid #7fc4d1;
                color: #7fc4d1;
            }
        """)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._workspace_toolbar)

        self._api.set_panel_handler(self._add_panel)
        self._api.set_workspace_handler(self._add_workspace, self._switch_workspace)
        self._api.set_action_handler(self._add_action)

        self.setWindowTitle("Setuav Studio")
        self.resize(1200, 800)
        workspace = QWidget(self)
        workspace.setObjectName("studio.empty-workspace")
        self.setCentralWidget(workspace)

        self._menus: dict[str, QMenu] = {}
        self._file_menu = self.menuBar().addMenu("&File")
        self._menus["file"] = self._file_menu

        open_file_action = self._file_menu.addAction(get_icon("file_open"), "Open Project File…")
        open_file_action.triggered.connect(self._open_project_file)

        open_folder_action = self._file_menu.addAction(get_icon("folder_open"), "Open Project Folder…")
        open_folder_action.triggered.connect(self._open_project_folder)

        self._recent_menu = QMenu("Open Recent", self._file_menu)
        self._recent_menu.setIcon(get_icon("project_folder"))
        self._file_menu.addMenu(self._recent_menu)
        self._menus["file/open recent"] = self._recent_menu
        self._file_menu.addSeparator()

        self._save_action = self._file_menu.addAction(get_icon("save"), "Save")
        self._save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_action.triggered.connect(self.save_project)

        self._save_as_action = self._file_menu.addAction(get_icon("save_as"), "Save As…")
        self._save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._save_as_action.triggered.connect(self.save_project_as)

        self._file_menu.addSeparator()
        exit_action = self._file_menu.addAction(get_icon("exit"), "Exit")
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)

        edit_menu = self.menuBar().addMenu("&Edit")
        self._menus["edit"] = edit_menu
        self._undo_action = edit_menu.addAction(get_icon("undo"), "Undo")
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.triggered.connect(self._api.undo)
        self._undo_action.setEnabled(False)

        self._redo_action = edit_menu.addAction(get_icon("redo"), "Redo")
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(self._api.redo)
        self._redo_action.setEnabled(False)

        edit_menu.addSeparator()
        settings_action = edit_menu.addAction(get_icon("settings"), "Settings…")
        settings_action.triggered.connect(self._open_settings)

        self._view_menu = self.menuBar().addMenu("&View")
        self._menus["view"] = self._view_menu

        self._tools_menu = self.menuBar().addMenu("&Tools")
        self._menus["tools"] = self._tools_menu

        self._api.undo_stack.canUndoChanged.connect(self._undo_action.setEnabled)
        self._api.undo_stack.canRedoChanged.connect(self._redo_action.setEnabled)
        self._api.undo_stack.undoTextChanged.connect(self._set_undo_text)
        self._api.undo_stack.redoTextChanged.connect(self._set_redo_text)
        self._api.on_modified_changed(self._on_modified_changed)
        self._api.on_project_content_changed(self._on_project_content_changed)
        self.destroyed.connect(self._detach_api_listeners)
        self._update_recent_menu()
        self._update_actions()

    def restore_window_layout(self) -> None:
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        state = settings.value("main_window/state")
        if state is not None:
            self.restoreState(state, self._LAYOUT_VERSION)


    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_project_close():
            event.ignore()
            return

        self._detach_api_listeners()
        settings = QSettings()
        settings.setValue("main_window/geometry", self.saveGeometry())
        settings.setValue(
            "main_window/state",
            self.saveState(self._LAYOUT_VERSION),
        )
        super().closeEvent(event)

    def open_last_project(self) -> None:
        recent = self._recent_projects()
        if recent:
            self.open_project(recent[0])

    def _open_project_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Setuav Project",
            "",
            "Setuav Projects (*.suav project.json);;All Files (*)",
        )
        if path:
            self.open_project(path)

    def _open_project_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Setuav Project Folder")
        if path:
            self.open_project(path)

    def open_project(self, path: str) -> bool:
        try:
            project = open_project(path)
        except ProjectOpenError as exc:
            QMessageBox.critical(self, "Cannot Open Project", str(exc))
            return False

        if not self._confirm_project_close():
            return False

        self._project = project
        project.plugin_issues = self._api.check_project_requirements(project.data)
        self._api.set_project(project)
        self._add_recent_project(project.location)
        self._update_window_title()
        self._update_actions()
        if project.degraded:
            self.statusBar().showMessage(
                "Degraded mode — " + "; ".join(project.plugin_issues)
            )
        else:
            self.statusBar().clearMessage()
        return True

    def save_project(self) -> bool:
        if self._project is None:
            return False
        try:
            save_project(self._project)
        except ProjectSaveError as exc:
            QMessageBox.critical(self, "Cannot Save Project", str(exc))
            return False
        self._api.mark_project_saved()
        self._add_recent_project(self._project.location)
        self._update_window_title()
        return True

    def save_project_as(self) -> bool:
        if self._project is None:
            return False
        initial_path = str(self._project.location)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Setuav Project As",
            initial_path,
            "Setuav Archive (*.suav);;Project JSON (project.json)",
        )
        if not path:
            return False
        try:
            save_project(self._project, path)
        except ProjectSaveError as exc:
            QMessageBox.critical(self, "Cannot Save Project", str(exc))
            return False
        self._api.mark_project_saved()
        self._add_recent_project(self._project.location)
        self._update_window_title()
        return True

    def _confirm_project_close(self) -> bool:
        if self._project is None or not self._project.modified:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Save changes to the current project?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def _update_window_title(self) -> None:
        try:
            if not shiboken6.isValid(self):
                return
        except Exception:
            return
        if self._project is None:
            self.setWindowTitle("Setuav Studio")
            return
        name = self._project.data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = self._project.location.stem
        modified = "*" if self._project.modified else ""
        self.setWindowTitle(f"{name}{modified} — Setuav Studio")

    def _on_modified_changed(self, _modified: bool) -> None:
        try:
            if not shiboken6.isValid(self):
                return
        except Exception:
            return
        self._update_window_title()

    def _on_project_content_changed(self, _project: ProjectDocument) -> None:
        try:
            if not shiboken6.isValid(self):
                return
        except Exception:
            return
        self._update_window_title()

    def _detach_api_listeners(self, *_args: object) -> None:
        self._api.remove_modified_listener(self._on_modified_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)

    def _update_actions(self) -> None:
        has_project = self._project is not None
        self._save_action.setEnabled(has_project)
        self._save_as_action.setEnabled(has_project)

    def _set_undo_text(self, text: str) -> None:
        self._undo_action.setText(f"Undo {text}" if text else "Undo")

    def _set_redo_text(self, text: str) -> None:
        self._redo_action.setText(f"Redo {text}" if text else "Redo")

    def _recent_projects(self) -> list[str]:
        value = QSettings().value("recent_projects", [])
        if isinstance(value, str):
            return [value]
        return [str(path) for path in value]

    def _add_recent_project(self, path: Path) -> None:
        path_text = str(path)
        recent = [item for item in self._recent_projects() if item != path_text]
        recent.insert(0, path_text)
        limit = StudioSettings.load().recent_project_limit
        QSettings().setValue("recent_projects", recent[:limit])
        self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        if not hasattr(self, "_recent_menu") or not shiboken6.isValid(self._recent_menu):
            return
        self._recent_menu.clear()
        recent = self._recent_projects()
        if not recent:
            empty_action = self._recent_menu.addAction("No Recent Projects")
            empty_action.setEnabled(False)
            return
        for path in recent:
            action = self._recent_menu.addAction(path)
            action.triggered.connect(lambda _checked=False, value=path: self.open_project(value))
        self._recent_menu.addSeparator()
        clear_action = self._recent_menu.addAction("Clear Recent Projects")
        clear_action.triggered.connect(self._clear_recent_projects)

    def _clear_recent_projects(self) -> None:
        QSettings().remove("recent_projects")
        self._update_recent_menu()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(StudioSettings.load(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        values.save()
        apply_theme(QApplication.instance(), values.theme, values.font_size)
        self._trim_recent_projects(values.recent_project_limit)
        self._update_recent_menu()

    def _trim_recent_projects(self, limit: int) -> None:
        QSettings().setValue("recent_projects", self._recent_projects()[:limit])

    def _add_panel(self, contribution: PanelContribution) -> None:
        dock = QDockWidget(contribution.title, self)
        dock.setFont(QApplication.font())
        dock.setTitleBarWidget(DockTitleBar(dock))
        dock.setObjectName(contribution.id)
        dock.setWidget(contribution.factory())
        self.addDockWidget(contribution.area, dock)
        self._panels[contribution.id] = (contribution, dock)

        action = dock.toggleViewAction()
        if contribution.id == "project.explorer":
            action.setIcon(get_icon("project_explorer"))
        elif contribution.id == "studio.properties":
            action.setIcon(get_icon("properties"))
        self._view_menu.addAction(action)

        if (
            contribution.workspace_id is not None
            and contribution.workspace_id != self._api.current_workspace_id
        ):
            dock.hide()

        if contribution.area in {
            Qt.DockWidgetArea.LeftDockWidgetArea,
            Qt.DockWidgetArea.RightDockWidgetArea,
        }:
            self.resizeDocks([dock], [320], Qt.Orientation.Horizontal)

    def _add_action(self, contribution: ActionContribution) -> None:
        parts = [p.strip().replace("&", "") for p in contribution.menu.split("/") if p.strip()]
        if not parts:
            parts = ["Tools"]

        path_key = ""
        current_menu = None
        for i, name in enumerate(parts):
            path_key = f"{path_key}/{name.lower()}" if path_key else name.lower()
            if path_key in self._menus and shiboken6.isValid(self._menus[path_key]):
                current_menu = self._menus[path_key]
            else:
                if i == 0:
                    current_menu = self.menuBar().addMenu(f"&{name}")
                else:
                    sub = QMenu(f"&{name}", current_menu)
                    current_menu.addMenu(sub)
                    current_menu = sub
                self._menus[path_key] = current_menu

        icon = get_icon(contribution.icon) if contribution.icon else None
        if icon is not None and not icon.isNull():
            action = current_menu.addAction(icon, contribution.title)
        else:
            action = current_menu.addAction(contribution.title)

        if contribution.shortcut:
            action.setShortcut(QKeySequence(contribution.shortcut))

        action.triggered.connect(contribution.callback)

    def _add_workspace(self, contribution: WorkspaceContribution) -> None:
        self._workspaces[contribution.id] = contribution

        if self._workspace_dock is None:
            dock = QDockWidget(contribution.title, self)
            dock.setObjectName(contribution.id)
            dock.setFont(QApplication.font())
            dock.setTitleBarWidget(DockTitleBar(dock))
            dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
            dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetClosable
                | QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            )
            dock.setWidget(self._workspace_stack)
            self._workspace_dock = dock

            previous = self.takeCentralWidget()
            if previous is not None:
                previous.deleteLater()

            explorer_dock = self.findChild(QDockWidget, "project.explorer")
            if explorer_dock is not None:
                self.splitDockWidget(explorer_dock, dock, Qt.Orientation.Horizontal)
            else:
                self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

            toggle_action = dock.toggleViewAction()
            toggle_action.setIcon(get_icon("viewer_3d"))
            self._view_menu.addAction(toggle_action)

            props_dock = self.findChild(QDockWidget, "studio.properties")
            docks_to_resize = []
            sizes = []
            if explorer_dock is not None:
                docks_to_resize.append(explorer_dock)
                sizes.append(300)
            docks_to_resize.append(dock)
            sizes.append(600)
            if props_dock is not None:
                docks_to_resize.append(props_dock)
                sizes.append(300)
            self.resizeDocks(docks_to_resize, sizes, Qt.Orientation.Horizontal)

        self._rebuild_workspace_toolbar()

        # Default activate
        if self._api.current_workspace_id is None or contribution.id in {"studio.viewer.opengl", "studio.workspace.design"}:
            self._api.switch_workspace(contribution.id)

    def _rebuild_workspace_toolbar(self) -> None:
        self._workspace_toolbar.clear()
        self._workspace_buttons.clear()

        sorted_workspaces = sorted(self._workspaces.values(), key=lambda w: (w.order, w.title))
        for contribution in sorted_workspaces:
            btn = QToolButton(self._workspace_toolbar)
            btn.setText(contribution.title)
            btn.setCheckable(True)
            if contribution.icon:
                btn.setIcon(get_icon(contribution.icon))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.clicked.connect(lambda _checked, cid=contribution.id: self._api.switch_workspace(cid))
            self._workspace_toolbar.addWidget(btn)
            self._workspace_buttons[contribution.id] = btn

        if self._api.current_workspace_id and self._api.current_workspace_id in self._workspace_buttons:
            self._workspace_buttons[self._api.current_workspace_id].setChecked(True)

    def _switch_workspace(self, workspace_id: str) -> None:
        if workspace_id not in self._workspaces:
            return

        contribution = self._workspaces[workspace_id]
        if workspace_id not in self._workspace_widgets:
            widget = contribution.factory()
            self._workspace_widgets[workspace_id] = widget
            self._workspace_stack.addWidget(widget)

        target_widget = self._workspace_widgets[workspace_id]
        self._workspace_stack.setCurrentWidget(target_widget)

        for cid, btn in self._workspace_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(cid == workspace_id)
            btn.blockSignals(False)

        # Update dock panel visibility for workspace-specific panels
        for cid, (panel_contrib, dock) in self._panels.items():
            if panel_contrib.workspace_id is not None:
                if panel_contrib.workspace_id == workspace_id:
                    dock.show()
                else:
                    dock.hide()

        if self._workspace_dock is not None:
            self._workspace_dock.setWindowTitle(contribution.title)
            self._workspace_dock.setObjectName(contribution.id)
