from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from setuav_studio.project import ProjectDocument, ProjectOpenError, open_project


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._project: ProjectDocument | None = None

        self.setWindowTitle("Setuav Studio")
        self.resize(1200, 800)

        file_menu = self.menuBar().addMenu("&File")
        open_file_action = file_menu.addAction("Open Project File…")
        open_file_action.triggered.connect(self._open_project_file)

        open_folder_action = file_menu.addAction("Open Project Folder…")
        open_folder_action.triggered.connect(self._open_project_folder)

    def _open_project_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Setuav Project",
            "",
            "Setuav Projects (*.suav project.json);;All Files (*)",
        )
        if path:
            self._load_project(path)

    def _open_project_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Setuav Project Folder")
        if path:
            self._load_project(path)

    def _load_project(self, path: str) -> None:
        try:
            project = open_project(path)
        except ProjectOpenError as exc:
            QMessageBox.critical(self, "Cannot Open Project", str(exc))
            return

        self._project = project
        name = project.data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = Path(path).stem
        self.setWindowTitle(f"{name} — Setuav Studio")
