from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

import shiboken6
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

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

logger = logging.getLogger(__name__)


class ProjectController:
    """Manages project file operations, document lifecycle, and unsaved changes."""

    def __init__(self, window: QMainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self._host = api._host

    @property
    def project(self) -> ProjectDocument | None:
        return getattr(self._window, "_project", None)

    @project.setter
    def project(self, value: ProjectDocument | None) -> None:
        self._window._project = value

    def new_project(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self._window,
            "New Setuav Project",
            "untitled.suav",
            "Setuav Archive (*.suav)",
        )
        if not path or not self._window._confirm_project_close():
            return False
        if not Path(path).suffix:
            path = f"{path}.suav"

        try:
            doc = create_project(path)
            save_project(doc)
        except ProjectSaveError as exc:
            QMessageBox.critical(self._window, "Cannot Create Project", str(exc))
            return False
        return self._window._activate_project(doc, confirm_close=False)

    def open_project_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self._window, "Open Setuav Project")
        if path:
            self._window.open_project(path)

    def open_project(self, path: str) -> bool:
        try:
            doc = open_project(path)
        except ProjectOpenError as exc:
            QMessageBox.critical(self._window, "Cannot Open Project", str(exc))
            return False
        return self._window._activate_project(doc)

    def open_last_project(self) -> None:
        recent = self._window._recent_projects()
        if recent:
            self._window.open_project(recent[0])

    def activate_project(self, project: ProjectDocument, *, confirm_close: bool = True) -> bool:
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

        if confirm_close and not self._window._confirm_project_close():
            return False

        self.project = project
        project.plugin_issues = self._host.check_project_requirements(project.data)
        self._host.set_project(project)
        self._window._add_recent_project(project.location)
        self._window._update_window_title()
        if hasattr(self._window, "_update_actions"):
            self._window._update_actions()

        status_mgr = getattr(self._window, "_status_manager", None)
        if project.read_only:
            self._api.show_status(
                f"Project opened read-only: {len(validation_issues)} validation issue(s)",
                "warning",
                8000,
            )
        project_name = str(project.data.get("name") or project.location.name or project.path.name)
        if project.degraded:
            if status_mgr:
                status_mgr.degraded_badge.setToolTip("\n".join(project.plugin_issues))
                status_mgr.degraded_badge.show()
            self._api.show_status(
                "Degraded mode — " + "; ".join(project.plugin_issues),
                "warning",
                0,
            )
        elif not project.read_only:
            if status_mgr:
                status_mgr.degraded_badge.hide()
            self._api.show_status(f"Project opened: {project_name}", "info", 4000)
        else:
            if status_mgr:
                status_mgr.degraded_badge.hide()
        return True

    def save_project(self) -> bool:
        if self.project is None:
            return False
        try:
            save_project(self.project)
        except ProjectSaveError as exc:
            QMessageBox.critical(self._window, "Cannot Save Project", str(exc))
            return False
        self._host.mark_project_saved()
        self._window._add_recent_project(self.project.location)
        self._window._update_window_title()
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
            save_project(self.project, path)
        except ProjectSaveError as exc:
            QMessageBox.critical(self._window, "Cannot Save Project", str(exc))
            return False
        self._host.mark_project_saved()
        self._window._add_recent_project(self.project.location)
        self._window._update_window_title()
        return True

    def collect_unsaved_changes(self) -> list[str]:
        if self.project is None:
            return []

        changes: list[str] = []
        try:
            disk_doc = None
            if self.project.location and self.project.location.exists():
                with suppress(Exception):
                    disk_doc = open_project(self.project.location)

            disk_data = disk_doc.data if disk_doc else {}
            curr_data = self.project.data

            _append_entity_changes(
                changes,
                _items_by_id(disk_data, "components"),
                _items_by_id(curr_data, "components"),
                "Component",
                include_deleted=True,
            )
            _append_entity_changes(
                changes,
                _items_by_id(disk_data, "assemblies"),
                _items_by_id(curr_data, "assemblies"),
                "Assembly",
            )
            self.append_unsaved_plugin_entries(changes, disk_data, curr_data)
            self.append_unsaved_aerodynamic_analyses(changes, disk_doc)
            self.append_unsaved_performance_analyses(changes, disk_doc)

        except Exception as exc:
            logger.debug("Failed to collect detailed unsaved changes: %s", exc)

        return changes

    def append_unsaved_aerodynamic_analyses(
        self, changes: list[str], disk_document: ProjectDocument | None
    ) -> None:
        try:
            from plugins.aerodynamics.analysis_store import analysis_entries

            self.append_unsaved_analyses(
                changes,
                analysis_entries(disk_document) if disk_document else [],
                analysis_entries(self.project),
                "Aerodynamic Analysis",
            )
        except Exception:
            pass

    def append_unsaved_performance_analyses(
        self, changes: list[str], disk_document: ProjectDocument | None
    ) -> None:
        try:
            from plugins.flight_performance.analysis_store import analysis_entries

            self.append_unsaved_analyses(
                changes,
                analysis_entries(disk_document) if disk_document else [],
                analysis_entries(self.project),
                "Flight Performance Analysis",
            )
        except Exception:
            pass

    @staticmethod
    def append_unsaved_analyses(
        changes: list[str],
        disk_entries: list[dict[str, Any]],
        current_entries: list[dict[str, Any]],
        fallback_name: str,
    ) -> None:
        disk_ids = {entry.get("id") for entry in disk_entries if isinstance(entry, dict)}
        for entry in current_entries:
            if isinstance(entry, dict) and entry.get("id") not in disk_ids:
                changes.append(f"Unsaved {fallback_name}: {entry.get('name') or fallback_name}")

    @staticmethod
    def append_unsaved_plugin_entries(
        changes: list[str],
        disk_data: dict[str, Any],
        curr_data: dict[str, Any],
    ) -> None:
        """Inspect all plugin/extension namespaces for unsaved analytical entries."""
        disk_plugins = disk_data.get("plugins") or disk_data.get("extensions") or {}
        curr_plugins = curr_data.get("plugins") or curr_data.get("extensions") or {}
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

        unsaved_items = self._window._collect_unsaved_changes()
        proj_name = str(
            self.project.data.get("name") or self.project.location.stem or "Current Project"
        )

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
            return self._window.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def update_window_title(self) -> None:
        try:
            if not shiboken6.isValid(self._window):
                return
        except (RuntimeError, Exception) as exc:
            logger.debug("Window title update skipped (widget invalid): %s", exc)
            return
        if self.project is None:
            self._window.setWindowTitle("Setuav Studio")
            return
        name = self.project.data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = self.project.location.stem
        modified = "*" if self.project.modified else ""
        self._window.setWindowTitle(f"{name}{modified} — Setuav Studio")

    def recent_projects(self) -> list[str]:
        value = QSettings().value("recent_projects", [])
        if isinstance(value, str):
            return [value]
        return [str(path) for path in value]

    def add_recent_project(self, path: Path) -> None:
        path_text = str(path)
        recent = [item for item in self._window._recent_projects() if item != path_text]
        recent.insert(0, path_text)
        limit = StudioSettings.load().recent_project_limit
        QSettings().setValue("recent_projects", recent[:limit])
        if hasattr(self._window, "_update_recent_menu"):
            self._window._update_recent_menu()

    def clear_recent_projects(self) -> None:
        QSettings().remove("recent_projects")
        if hasattr(self._window, "_update_recent_menu"):
            self._window._update_recent_menu()

    def trim_recent_projects(self, limit: int) -> None:
        QSettings().setValue("recent_projects", self._window._recent_projects()[:limit])


__all__ = ["ProjectController"]
