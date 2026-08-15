from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from setuav_studio.plugin_system import PanelContribution, StudioAPI
from setuav_studio.plugins.core.settings import SettingsDialog, StudioSettings
from setuav_studio.project import (
    ProjectDocument,
    ProjectOpenError,
    ProjectSaveError,
    open_project,
    save_project,
)


class MainWindow(QMainWindow):
    _LAYOUT_VERSION = 2

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._project: ProjectDocument | None = None
        self._api.set_panel_handler(self._add_panel)

        self.setWindowTitle("Setuav Studio")
        self.resize(1200, 800)
        self.setCentralWidget(QWidget(self))

        self._file_menu = self.menuBar().addMenu("&File")
        open_file_action = self._file_menu.addAction("Open Project File…")
        open_file_action.triggered.connect(self._open_project_file)

        open_folder_action = self._file_menu.addAction("Open Project Folder…")
        open_folder_action.triggered.connect(self._open_project_folder)

        self._recent_menu = self._file_menu.addMenu("Open Recent")
        self._file_menu.addSeparator()

        self._save_action = self._file_menu.addAction("Save")
        self._save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_action.triggered.connect(self.save_project)

        self._save_as_action = self._file_menu.addAction("Save As…")
        self._save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._save_as_action.triggered.connect(self.save_project_as)

        self._file_menu.addSeparator()
        exit_action = self._file_menu.addAction("Exit")
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)

        edit_menu = self.menuBar().addMenu("&Edit")
        self._undo_action = edit_menu.addAction("Undo")
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.triggered.connect(self._api.undo)
        self._undo_action.setEnabled(False)

        self._redo_action = edit_menu.addAction("Redo")
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(self._api.redo)
        self._redo_action.setEnabled(False)

        edit_menu.addSeparator()
        settings_action = edit_menu.addAction("Settings…")
        settings_action.triggered.connect(self._open_settings)

        self._view_menu = self.menuBar().addMenu("&View")

        self._api.undo_stack.canUndoChanged.connect(self._undo_action.setEnabled)
        self._api.undo_stack.canRedoChanged.connect(self._redo_action.setEnabled)
        self._api.undo_stack.undoTextChanged.connect(self._set_undo_text)
        self._api.undo_stack.redoTextChanged.connect(self._set_redo_text)
        self._api.on_modified_changed(lambda _modified: self._update_window_title())
        self._api.on_project_content_changed(lambda _project: self._update_window_title())
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
        if self._project is None:
            self.setWindowTitle("Setuav Studio")
            return
        name = self._project.data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = self._project.location.stem
        modified = "*" if self._project.modified else ""
        self.setWindowTitle(f"{name}{modified} — Setuav Studio")

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
        if values.interface_style:
            QApplication.setStyle(values.interface_style)
        self._trim_recent_projects(values.recent_project_limit)
        self._update_recent_menu()

    def _trim_recent_projects(self, limit: int) -> None:
        QSettings().setValue("recent_projects", self._recent_projects()[:limit])

    def _add_panel(self, contribution: PanelContribution) -> None:
        dock = QDockWidget(contribution.title, self)
        dock.setObjectName(contribution.id)
        dock.setWidget(contribution.factory())
        self.addDockWidget(contribution.area, dock)
        self._view_menu.addAction(dock.toggleViewAction())
        if contribution.area in {
            Qt.DockWidgetArea.LeftDockWidgetArea,
            Qt.DockWidgetArea.RightDockWidgetArea,
        }:
            self.resizeDocks([dock], [320], Qt.Orientation.Horizontal)
