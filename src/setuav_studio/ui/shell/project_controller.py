from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import shiboken6
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox

from setuav_studio.api.events import StudioEvents
from setuav_studio.project import (
    ProjectDocument,
    ProjectOpenError,
    ProjectSaveError,
    create_project,
    open_project,
    save_project,
)
from setuav_studio.project.validation import validate_project
from setuav_studio.ui.settings.settings_pages import StudioSettings

from .validation import (
    _append_entity_changes,
    _items_by_id,
    apply_runtime_validation,
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

    from .window import MainWindow

logger = logging.getLogger(__name__)


class ProjectController:
    """Manages project file operations, document lifecycle, and unsaved changes."""

    def __init__(self, window: MainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self._host = api._host
        self.project: ProjectDocument | None = None

    def new_project(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self._window,
            "New Setuav Project",
            "Untitled.suav",
            "Setuav Archive (*.suav)",
        )
        if not path or not self.confirm_project_close():
            return False
        if not Path(path).suffix:
            path = f"{path}.suav"

        try:
            doc = create_project(path)
            save_project(doc)
        except ProjectSaveError as exc:
            QMessageBox.critical(self._window, "Cannot Create Project", str(exc))
            return False
        return self.activate_project(doc, confirm_close=False)

    def open_project_dialog(self) -> None:
        file_filter = (
            "Setuav Projects (*.suav project.json);;"
            "Setuav Archive (*.suav);;"
            "Project JSON (project.json);;"
            "All Files (*)"
        )
        path, _ = QFileDialog.getOpenFileName(
            self._window,
            "Open Setuav Project",
            "",
            file_filter,
        )
        if path:
            self.open_project(path)

    def open_project_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self._window, "Open Setuav Project Folder")
        if path:
            self.open_project(path)

    def open_project(self, path: str) -> bool:
        try:
            doc = open_project(path, recompute=False)
        except ProjectOpenError as exc:
            QMessageBox.critical(self._window, "Cannot Open Project", str(exc))
            return False
        return self.activate_project(doc)

    def new_untitled_project(self) -> bool:
        doc = create_project("Untitled.suav")
        doc.modified = False
        doc.untitled = True
        return self.activate_project(doc, confirm_close=False)

    def open_last_project(self) -> bool:
        recent = self.recent_projects()
        if recent:
            return bool(self.open_project(recent[0]))
        return False

    def activate_project(self, project: ProjectDocument, *, confirm_close: bool = True) -> bool:
        if project.untitled:
            project.read_only = False
            validation_issues = []
        else:
            validation_issues = validate_project(project.data)
            settings = StudioSettings.load()
            decision = apply_runtime_validation(
                project,
                validation_issues,
                settings.validation_strictness,
                parent=self._window,
            )
            if decision == "cancel":
                return False

        if confirm_close and not self.confirm_project_close():
            return False

        old_project = self.project
        if old_project is not None and old_project is not project:
            self._api.publish(StudioEvents.PROJECT_CLOSED, old_project)

        self.project = project
        project.plugin_issues = self._host.check_project_requirements(project.data)
        self._host.set_project(project)
        if not project.untitled:
            self.add_recent_project(project.location)
        self.update_window_title()
        self._window.action_manager.update_actions()

        if project.read_only:
            self._api.show_status(
                f"Project opened read-only: {len(validation_issues)} validation issue(s)",
                "warning",
                8000,
            )
        self._window.status_manager.evaluate_problems(project)
        if project.format_warning:
            self._api.show_status(project.format_warning, "warning", 0)
        elif self._api.expression_diagnostics:
            self._api._show_expression_diagnostics()
        elif project.degraded:
            self._api.show_status(
                "Degraded mode — " + "; ".join(project.plugin_issues),
                "warning",
                0,
            )
        elif project.untitled:
            self._api.show_status("New project ready", "info", 4000)
        elif not project.read_only:
            self._api.show_status(f"Project opened: {project.name}", "info", 4000)
        return True

    def save_project(self) -> bool:
        if self.project is None:
            return False
        if self.project.untitled:
            return self.save_project_as()
        try:
            save_project(self.project, api=self._api)
        except ProjectSaveError as exc:
            QMessageBox.critical(self._window, "Cannot Save Project", str(exc))
            return False
        self._host.mark_project_saved()
        self.add_recent_project(self.project.location)
        self.update_window_title()
        self._api.show_status("Project saved", "success", 3000)
        return True

    def save_project_as(self) -> bool:
        if self.project is None:
            return False
        initial_path = str(self.project.location)
        path, _ = QFileDialog.getSaveFileName(
            self._window,
            "Save Setuav Project As",
            initial_path,
            "Setuav Archive (*.suav);;Project JSON (project.json)",
        )
        if not path:
            return False
        try:
            save_project(self.project, path, api=self._api)
        except ProjectSaveError as exc:
            QMessageBox.critical(self._window, "Cannot Save Project", str(exc))
            return False
        self.project.untitled = False
        self._host.mark_project_saved()
        self.add_recent_project(self.project.location)
        self.update_window_title()
        return True

    def collect_unsaved_changes(self) -> list[str]:
        if self.project is None:
            return []

        changes: list[str] = []
        disk_data: dict[str, Any] = {}
        if not self.project.untitled and self.project.location.exists():
            try:
                disk_data = open_project(self.project.location, recompute=False).data
            except ProjectOpenError as exc:
                logger.warning("Saved project could not be read for comparison: %s", exc)
                return changes

        curr_data = self.project.data
        _append_entity_changes(
            changes,
            _items_by_id(disk_data, "components"),
            _items_by_id(curr_data, "components"),
            "Component",
            include_deleted=True,
        )
        self.append_unsaved_plugin_entries(changes, disk_data, curr_data)
        return changes

    @staticmethod
    def append_unsaved_plugin_entries(
        changes: list[str],
        disk_data: dict[str, Any],
        curr_data: dict[str, Any],
    ) -> None:
        """Inspect all extension namespaces for unsaved analytical entries."""
        disk_plugins = disk_data.get("extensions") or {}
        curr_plugins = curr_data.get("extensions") or {}
        if not isinstance(disk_plugins, dict) or not isinstance(curr_plugins, dict):
            return
        for namespace, curr_val in curr_plugins.items():
            if not isinstance(curr_val, dict):
                continue
            disk_val = (
                disk_plugins.get(namespace, {})
                if isinstance(disk_plugins.get(namespace), dict)
                else {}
            )
            for list_key in ("analysis_runs", "results", "entries"):
                curr_list = curr_val.get(list_key, [])
                disk_list = disk_val.get(list_key, []) if isinstance(disk_val, dict) else []
                if isinstance(curr_list, list) and isinstance(disk_list, list):
                    disk_ids = {e.get("id") for e in disk_list if isinstance(e, dict)}
                    for e in curr_list:
                        if isinstance(e, dict) and e.get("id") and e.get("id") not in disk_ids:
                            title = e.get("name") or e.get("id")
                            short_ns = namespace.split(".")[-1].replace("_", " ").title()
                            changes.append(f"Unsaved {short_ns} entry: {title}")

    def confirm_project_close(self) -> bool:
        if self.project is None or not self.project.modified:
            return True

        unsaved_items = self.collect_unsaved_changes()
        proj_name = self.project.name

        msg_box = QMessageBox(self._window)
        msg_box.setWindowTitle("Unsaved Changes")
        msg_box.setIcon(QMessageBox.Icon.Question)

        if unsaved_items:
            bullet_list = "\n".join(f"  • {item}" for item in unsaved_items[:8])
            if len(unsaved_items) > 8:
                bullet_list += f"\n  • ... and {len(unsaved_items) - 8} more unsaved items"
            msg_box.setText(
                f"Project '{proj_name}' contains the following unsaved changes:\n\n"
                f"{bullet_list}\n\n"
                f"Do you want to save your changes before closing?"
            )
        else:
            msg_box.setText(f"Save changes to project '{proj_name}' before closing?")

        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Save)

        answer = msg_box.exec()
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def update_window_title(self) -> None:
        if not shiboken6.isValid(self._window):
            return
        if self.project is None:
            self._window.setWindowTitle("Setuav Studio")
            return
        name = self.project.name
        modified = "*" if self.project.modified else ""
        self._window.setWindowTitle(f"{name}{modified} — Setuav Studio")

    def recent_projects(self) -> list[str]:
        value = QSettings().value("recent_projects", [])
        if isinstance(value, str):
            return [value]
        if not isinstance(value, list):
            return []
        return [str(path) for path in value]

    def add_recent_project(self, path: Path) -> None:
        path_text = str(path)
        recent = [item for item in self.recent_projects() if item != path_text]
        recent.insert(0, path_text)
        limit = StudioSettings.load().recent_project_limit
        QSettings().setValue("recent_projects", recent[:limit])
        self._window.action_manager.update_recent_menu()

    def clear_recent_projects(self) -> None:
        QSettings().remove("recent_projects")
        self._window.action_manager.update_recent_menu()

    def trim_recent_projects(self, limit: int) -> None:
        QSettings().setValue("recent_projects", self.recent_projects()[:limit])


__all__ = ["ProjectController"]
