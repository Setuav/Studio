from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDockWidget, QFileDialog, QMainWindow, QMessageBox, QWidget

from setuav_studio.plugin_system import PanelContribution, StudioAPI
from setuav_studio.project import ProjectDocument, ProjectOpenError, open_project


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

        file_menu = self.menuBar().addMenu("&File")
        open_file_action = file_menu.addAction("Open Project File…")
        open_file_action.triggered.connect(self._open_project_file)

        open_folder_action = file_menu.addAction("Open Project Folder…")
        open_folder_action.triggered.connect(self._open_project_folder)

        self._view_menu = self.menuBar().addMenu("&View")

    def restore_window_layout(self) -> None:
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        state = settings.value("main_window/state")
        if state is not None:
            self.restoreState(state, self._LAYOUT_VERSION)

    def closeEvent(self, event: QCloseEvent) -> None:
        settings = QSettings()
        settings.setValue("main_window/geometry", self.saveGeometry())
        settings.setValue(
            "main_window/state",
            self.saveState(self._LAYOUT_VERSION),
        )
        super().closeEvent(event)

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

    def open_project(self, path: str) -> None:
        try:
            project = open_project(path)
        except ProjectOpenError as exc:
            QMessageBox.critical(self, "Cannot Open Project", str(exc))
            return

        self._project = project
        self._api.set_project(project)
        name = project.data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = Path(path).stem
        self.setWindowTitle(f"{name} — Setuav Studio")

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
