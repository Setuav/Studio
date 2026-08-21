from pathlib import Path

import shiboken6
from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QFont, QFontMetrics, QIcon, QKeySequence
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
    QProgressBar,
    QStackedWidget,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.log_buffer import install_log_buffer
from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    ToolContribution,
    WorkspaceContribution,
)
from setuav_studio.plugins.core.settings import SettingsDialog, StudioSettings
from setuav_studio.schema_validation import validate_project
from setuav_studio.ui.theme import STATUS_COLORS, accent_color, rgba, tokens
from setuav_studio.project import (
    ProjectDocument,
    ProjectOpenError,
    ProjectSaveError,
    open_project,
    save_project,
)


class DockTitleBar(QWidget):
    """Simple custom dock title bar styled through theme tokens."""

    def __init__(self, dock: QDockWidget, icon: str | Path | QIcon | None = None) -> None:
        super().__init__(dock)
        self.setObjectName("studioDockTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 1, 4, 1)
        layout.setSpacing(4)

        if icon:
            icon_label = QLabel(self)
            icon_label.setPixmap(get_icon(icon).pixmap(13, 13))
            icon_label.setFixedSize(13, 13)
            icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(icon_label)

        self._title = QLabel(dock.windowTitle(), self)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._title)
        layout.addStretch()

        button_color = tokens()["text"]

        float_button = QToolButton(self)
        float_button.setAutoRaise(True)
        float_button.setFixedSize(22, 20)
        float_button.setIconSize(QSize(13, 13))
        float_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        float_button.setToolTip("Dock or undock panel")
        float_button.setIcon(get_icon("dock_float", color=button_color))
        float_button.clicked.connect(
            lambda: dock.setFloating(not dock.isFloating())
        )
        layout.addWidget(float_button)

        close_button = QToolButton(self)
        close_button.setAutoRaise(True)
        close_button.setFixedSize(22, 20)
        close_button.setIconSize(QSize(13, 13))
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setToolTip("Close panel")
        close_button.setIcon(get_icon("dock_close", color=button_color))
        close_button.clicked.connect(dock.close)
        layout.addWidget(close_button)

        dock.windowTitleChanged.connect(self._title.setText)


def apply_runtime_validation(
    project: ProjectDocument,
    issues: object,
    strictness: str,
    parent: QWidget | None = None,
    *,
    interactive: bool = True,
) -> str:
    """Apply runtime schema validation decisions to a freshly opened project.

    Returns ``"open"``, ``"read_only"``, or ``"cancel"``. When
    ``interactive`` is ``False`` the strict-mode blocking dialog is skipped
    and the project is forced read-only (used by tests).
    """
    if not issues or strictness == "off":
        return "open"
    if strictness == "warn":
        project.read_only = True
        return "read_only"
    if strictness != "strict":
        return "open"

    if not interactive:
        project.read_only = True
        return "read_only"

    message = "\n".join(
        f"• {issue.path}: {issue.message}"
        for issue in issues[:10]
    )
    if len(issues) > 10:
        message += f"\n…and {len(issues) - 10} more."

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Project validation failed")
    box.setText(f"Found {len(issues)} schema issue(s).")
    box.setInformativeText(message)
    btn_ro = box.addButton("Open read-only", QMessageBox.ButtonRole.AcceptRole)
    btn_cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(btn_ro)
    box.exec()
    if box.clickedButton() is btn_cancel:
        return "cancel"
    project.read_only = True
    return "read_only"


class MainWindow(QMainWindow):
    _LAYOUT_VERSION = 6

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._project: ProjectDocument | None = None
        self._workspaces: dict[str, WorkspaceContribution] = {}
        self._workspace_widgets: dict[str, QWidget] = {}
        self._workspace_buttons: dict[str, QToolButton] = {}
        self._panels: dict[str, tuple[PanelContribution, QDockWidget]] = {}
        self._current_workspace_id: str | None = None
        self._workspace_states: dict[str, Any] = {}
        self.setDockNestingEnabled(True)

        central_anchor = QWidget(self)
        central_anchor.setObjectName("studio.central-anchor")
        self.setCentralWidget(central_anchor)

        self._workspace_toolbar = QToolBar("Workspaces", self)
        self._workspace_toolbar.setObjectName("studio.workspace_toolbar")
        self._workspace_toolbar.setMovable(False)
        self._workspace_toolbar.setFloatable(False)
        self._workspace_toolbar.setIconSize(QSize(15, 15))
        self._workspace_toolbar.setStyleSheet(f"""
            QToolBar {{
                background: transparent;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 2px 8px;
            }}
            QToolButton {{
                background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 4px;
                padding: 0px 8px;
                margin: 1px 5px 1px 0px;
                font-size: 10.5pt;
                font-weight: 600;
                color: {tokens()["text"]};
            }}
            QToolButton:hover {{
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.22);
                color: #ffffff;
            }}
            QToolButton:checked {{
                background-color: {rgba(accent_color(), 0.15)};
                border: 1px solid {accent_color()};
                color: {accent_color()};
            }}
        """)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._workspace_toolbar)

        self._api.set_panel_handler(self._add_panel, self._remove_panel)
        self._api.set_workspace_handler(
            self._add_workspace,
            self._switch_workspace,
            self._remove_workspace,
        )
        self._api.set_action_handler(self._add_action, self._remove_action)

        self.setWindowTitle("Setuav Studio")
        self.resize(1200, 800)
        self.setCentralWidget(None)

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

        self._degraded_badge = QToolButton(self)
        self._degraded_badge.setText("⚠ Degraded mode")
        self._degraded_badge.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._degraded_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._degraded_badge.setAutoRaise(True)
        self._degraded_badge.hide()
        self._degraded_badge.clicked.connect(self._show_degraded_details)
        self.statusBar().addPermanentWidget(self._degraded_badge)

        self._log_button = QToolButton(self)
        self._log_button.setObjectName("studioStatusLogButton")
        self._log_button.setIcon(get_icon("log", color=tokens()["text"]))
        self._log_button.setToolTip("Application logs")
        self._log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_button.setAutoRaise(True)
        self._log_button.setFixedSize(22, 22)
        self._log_button.clicked.connect(self._open_log_window)
        self._log_window: QDialog | None = None

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setObjectName("studioStatusProgress")
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_bar.hide()
        self.statusBar().addPermanentWidget(self._progress_bar)

        self._status_label = QLabel(self)
        self._status_label.setObjectName("studioStatusMessage")
        self.statusBar().addWidget(self._log_button)
        self.statusBar().addWidget(self._status_label)
        self.statusBar().setStyleSheet(
            "QStatusBar {"
            " border-top: 1px solid rgba(255, 255, 255, 0.08);"
            " background-color: rgba(0, 0, 0, 0.25);"
            "}"
            "QStatusBar QToolButton {"
            " background: transparent;"
            " border: none;"
            " border-radius: 3px;"
            "}"
            "QStatusBar QToolButton:hover {"
            " background-color: rgba(255, 255, 255, 0.1);"
            "}"
            "QStatusBar QProgressBar {"
            f" background-color: {rgba(accent_color(), 0.12)};"
            f" border: 1px solid {tokens()['border_strong']};"
            " border-radius: 3px;"
            " height: 14px;"
            "}"
            "QStatusBar QProgressBar::chunk {"
            f" background-color: {accent_color()};"
            " border-radius: 2px;"
            "}"
        )
        self._api.set_progress_handler(self._show_progress)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status_message)
        self._api.set_status_handler(self._show_status_message)
        self._api.show_status("Ready", "info", 0)
        install_log_buffer()

    def _open_log_window(self) -> None:
        if self._log_window is None:
            from setuav_studio.ui.log_window import LogWindow

            self._log_window = LogWindow(self)
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()

    def _show_status_message(
        self,
        message: str,
        level: str = "info",
        timeout_ms: int = 5000,
    ) -> None:
        self._status_timer.stop()
        color = STATUS_COLORS.get(level, STATUS_COLORS["info"])
        self._status_label.setStyleSheet(f"color: {color};")
        self._status_label.setText(message)
        if timeout_ms > 0:
            self._status_timer.start(timeout_ms)

    def _show_progress(self, completed: int, total: int, label: str = "") -> None:
        if total <= 0 or completed >= total:
            self._progress_bar.hide()
            return
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(completed)
        self._progress_bar.setFormat(f"{label} %p%" if label else "%p%")
        self._progress_bar.show()

    def _clear_status_message(self) -> None:
        self._status_timer.stop()
        self._status_label.clear()

    def restore_window_layout(self) -> None:
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        active_workspace = settings.value("active_workspace")
        if active_workspace and str(active_workspace) in self._workspaces:
            self._api.switch_workspace(str(active_workspace))
        elif self._api.current_workspace_id:
            self._api.switch_workspace(self._api.current_workspace_id)
        elif "studio.workspace.design" in self._workspaces:
            self._api.switch_workspace("studio.workspace.design")

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_project_close():
            event.ignore()
            return

        self._detach_api_listeners()
        settings = QSettings()
        settings.setValue("main_window/geometry", self.saveGeometry())
        if self._current_workspace_id is not None:
            state = self.saveState(self._LAYOUT_VERSION)
            settings.setValue(
                f"workspace_perspective/{self._current_workspace_id}",
                state,
            )
            settings.setValue("active_workspace", self._current_workspace_id)
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

        validation_issues = validate_project(project.data)
        settings = StudioSettings.load()
        decision = apply_runtime_validation(
            project,
            validation_issues,
            settings.validation_strictness,
            parent=self,
        )
        if decision == "cancel":
            return False

        if not self._confirm_project_close():
            return False

        self._project = project
        project.plugin_issues = self._api.check_project_requirements(project.data)
        self._api.set_project(project)
        self._add_recent_project(project.location)
        self._update_window_title()
        self._update_actions()
        if project.read_only:
            self._api.show_status(
                f"Project opened read-only: {len(validation_issues)} validation issue(s)",
                "warning",
                8000,
            )
        project_name = str(
            project.data.get("name") or project.location.name or project.path.name
        )
        if project.degraded:
            self._degraded_badge.setToolTip("\n".join(project.plugin_issues))
            self._degraded_badge.show()
            self._api.show_status(
                "Degraded mode — " + "; ".join(project.plugin_issues),
                "warning",
                0,
            )
        elif not project.read_only:
            self._degraded_badge.hide()
            self._api.show_status(f"Project opened: {project_name}", "info", 4000)
        else:
            self._degraded_badge.hide()
        return True

    def _show_degraded_details(self) -> None:
        if self._project is None or not self._project.plugin_issues:
            return
        QMessageBox.warning(
            self,
            "Degraded Mode",
            "Some plugins required by this project are missing or incompatible:\n\n"
            + "\n".join(f"• {issue}" for issue in self._project.plugin_issues),
        )

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
        self._api.show_status("Project saved", "success", 3000)
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
        self._trim_recent_projects(values.recent_project_limit)
        self._update_recent_menu()

    def _trim_recent_projects(self, limit: int) -> None:
        QSettings().setValue("recent_projects", self._recent_projects()[:limit])

    def _update_view_menu(self, workspace_id: str | None) -> None:
        self._view_menu.clear()
        for cid, (panel_contrib, dock) in self._panels.items():
            if workspace_id is None or panel_contrib.is_in_workspace(workspace_id):
                action = dock.toggleViewAction()
                if panel_contrib.icon:
                    action.setIcon(get_icon(panel_contrib.icon))
                elif panel_contrib.id == "project.explorer":
                    action.setIcon(get_icon("project_explorer"))
                elif panel_contrib.id == "studio.properties":
                    action.setIcon(get_icon("properties"))
                self._view_menu.addAction(action)

    def _add_panel(self, contribution: PanelContribution) -> None:
        dock = QDockWidget(contribution.title, self)
        dock.setFont(QApplication.font())
        dock.setTitleBarWidget(DockTitleBar(dock, icon=contribution.icon))
        dock.setObjectName(contribution.id)
        dock.setWidget(self._wrap_panel(contribution.factory()))
        self.addDockWidget(contribution.area, dock)
        self._panels[contribution.id] = (contribution, dock)

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

    def _remove_action(self, menu_path: str, title: str) -> None:
        parts = [p.strip().replace("&", "") for p in menu_path.split("/") if p.strip()]
        if not parts:
            parts = ["Tools"]
        path_key = ""
        for name in parts:
            path_key = f"{path_key}/{name.lower()}" if path_key else name.lower()
        menu = self._menus.get(path_key)
        if menu is None or not shiboken6.isValid(menu):
            return
        for action in menu.actions():
            if action.text() == title:
                menu.removeAction(action)
                break

    def _add_workspace(self, contribution: WorkspaceContribution) -> None:
        self._workspaces[contribution.id] = contribution
        self._rebuild_workspace_toolbar()

    def _remove_workspace(self, workspace_id: str) -> None:
        if workspace_id not in self._workspaces:
            return
        del self._workspaces[workspace_id]
        self._rebuild_workspace_toolbar()
        for panel_id in list(self._panels):
            contribution, _ = self._panels[panel_id]
            if contribution.workspace_id == workspace_id or (
                isinstance(contribution.workspace_id, (list, tuple, set))
                and workspace_id in contribution.workspace_id
            ):
                self._remove_panel(panel_id)

    def _rebuild_workspace_toolbar(self) -> None:
        self._workspace_toolbar.clear()
        self._workspace_buttons.clear()

        sorted_workspaces = sorted(self._workspaces.values(), key=lambda w: (w.order, w.title))
        if sorted_workspaces:
            button_font = QFont(self._workspace_toolbar.font())
            button_font.setPointSizeF(10.5)
            font_metrics = QFontMetrics(button_font)
            button_width = (
                max(font_metrics.horizontalAdvance(w.title) for w in sorted_workspaces)
                + 64
            )
        else:
            button_width = 0
        for contribution in sorted_workspaces:
            btn = QToolButton(self._workspace_toolbar)
            btn.setText(contribution.title)
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setFixedSize(button_width, 26)
            btn.clicked.connect(lambda _checked, cid=contribution.id: self._api.switch_workspace(cid))
            self._workspace_toolbar.addWidget(btn)
            self._workspace_buttons[contribution.id] = btn

        if self._api.current_workspace_id and self._api.current_workspace_id in self._workspace_buttons:
            self._workspace_buttons[self._api.current_workspace_id].setChecked(True)

    def _switch_workspace(self, workspace_id: str) -> None:
        if workspace_id not in self._workspaces:
            return

        # 1. Save previous workspace perspective
        if (
            self._current_workspace_id is not None
            and self._current_workspace_id != workspace_id
        ):
            prev_state = self.saveState(self._LAYOUT_VERSION)
            self._workspace_states[self._current_workspace_id] = prev_state
            QSettings().setValue(
                f"workspace_perspective/{self._current_workspace_id}",
                prev_state,
            )

        self._current_workspace_id = workspace_id

        for cid, btn in self._workspace_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(cid == workspace_id)
            btn.blockSignals(False)

        # 2. Restore saved workspace perspective if available, or apply default layout
        settings = QSettings()
        saved_state = self._workspace_states.get(workspace_id) or settings.value(
            f"workspace_perspective/{workspace_id}"
        )
        if saved_state is not None:
            self.restoreState(saved_state, self._LAYOUT_VERSION)
        else:
            self._apply_default_workspace_layout(workspace_id)

        # 3. Update View menu actions for the active workspace only
        self._update_view_menu(workspace_id)

    def _apply_default_workspace_layout(self, workspace_id: str) -> None:
        explorer = self.findChild(QDockWidget, "project.explorer")
        viewer = self.findChild(QDockWidget, "studio.viewer.opengl")
        props = self.findChild(QDockWidget, "studio.properties")
        controls = self.findChild(QDockWidget, "propulsion.controls_dock")
        results = self.findChild(QDockWidget, "propulsion.results_dock")

        # Hide any panels that do not belong to this workspace
        for cid, (panel_contrib, dock) in self._panels.items():
            if not panel_contrib.is_in_workspace(workspace_id):
                dock.hide()

        if workspace_id in {"studio.workspace.design", "studio.viewer.opengl"}:
            if controls:
                controls.hide()
            if results:
                results.hide()
            if explorer and viewer:
                self.splitDockWidget(explorer, viewer, Qt.Orientation.Horizontal)
            if viewer and props:
                self.splitDockWidget(viewer, props, Qt.Orientation.Horizontal)
            if explorer:
                explorer.show()
            if viewer:
                viewer.show()
            if props:
                props.show()

            docks = [d for d in [explorer, viewer, props] if d is not None and not d.isHidden()]
            if docks:
                self.resizeDocks(docks, [260, 680, 260][:len(docks)], Qt.Orientation.Horizontal)

        elif workspace_id == "studio.workspace.propulsion":
            charts = self.findChild(QDockWidget, "propulsion.charts_dock")
            if viewer:
                viewer.hide()
            if explorer and props:
                self.splitDockWidget(explorer, props, Qt.Orientation.Vertical)
            if explorer and controls:
                self.splitDockWidget(explorer, controls, Qt.Orientation.Horizontal)
            if controls and charts:
                self.splitDockWidget(controls, charts, Qt.Orientation.Horizontal)
            if charts and results:
                self.splitDockWidget(charts, results, Qt.Orientation.Horizontal)
            elif controls and results:
                self.splitDockWidget(controls, results, Qt.Orientation.Horizontal)

            if explorer:
                explorer.show()
            if props:
                props.show()
            if controls:
                controls.show()
            if charts:
                charts.show()
            if results:
                results.show()

            docks = [d for d in [explorer, controls, charts, results] if d is not None and not d.isHidden()]
            if docks:
                self.resizeDocks(docks, [220, 280, 480, 260][:len(docks)], Qt.Orientation.Horizontal)

        else:
            for cid, (panel_contrib, dock) in self._panels.items():
                if panel_contrib.is_in_workspace(workspace_id):
                    dock.show()
                else:
                    dock.hide()
