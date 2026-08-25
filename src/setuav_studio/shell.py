import logging
from pathlib import Path
from typing import Any

import shiboken6
from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import (
    ActionContribution,
    PanelContribution,
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    WorkspaceContribution,
)
from setuav_studio.plugins.core.settings import SettingsDialog, StudioSettings
from setuav_studio.project import (
    ProjectDocument,
    ProjectOpenError,
    ProjectSaveError,
    open_project,
    save_project,
)
from setuav_studio.schema_validation import validate_project
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.log_buffer import install_log_buffer
from setuav_studio.ui.main_toolbar import ToolSetBar, WorkspaceToolBar
from setuav_studio.ui.theme import status_color

logger = logging.getLogger(__name__)


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

    message = "\n".join(f"• {issue.path}: {issue.message}" for issue in issues[:10])
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
    _LAYOUT_VERSION = 10

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._project: ProjectDocument | None = None
        self._workspaces: dict[str, WorkspaceContribution] = {}
        self._toolbar_contributions: dict[str, ToolbarContribution] = {}
        self._toolbar_actions: dict[str, QAction] = {}
        self._toolbar_menu_actions: dict[
            str,
            list[tuple[ToolbarMenuItemContribution, QAction]],
        ] = {}
        self._owned_toolbar_actions: set[str] = set()
        self._command_actions: dict[str, QAction] = {}
        self._toolset_bars: dict[str, ToolSetBar] = {}
        self._panels: dict[str, tuple[PanelContribution, QDockWidget]] = {}
        self._panel_actions: dict[str, QAction] = {}
        self._current_workspace_id: str | None = None
        self._workspace_states: dict[str, Any] = {}
        self._restoring_workspace_layout = False
        self._layout_save_scheduled = False
        self._layout_persistence_enabled = False
        self.setDockNestingEnabled(True)

        central_anchor = QWidget(self)
        central_anchor.setObjectName("studio.central-anchor")
        self.setCentralWidget(central_anchor)

        self._workspace_toolbar = WorkspaceToolBar(self)
        self._workspace_toolbar.workspace_activated.connect(self._api.switch_workspace)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._workspace_toolbar)

        self._api.set_panel_handler(self._add_panel, self._remove_panel)
        self._api.set_workspace_handler(
            self._add_workspace,
            self._switch_workspace,
            self._remove_workspace,
        )
        self._api.set_toolbar_handler(
            self._add_toolbar_item,
            self._remove_toolbar_item,
        )
        self._api.set_action_handler(self._add_action, self._remove_action)

        self.setWindowTitle("Setuav Studio")
        self.resize(1200, 800)
        self.setCentralWidget(None)

        self._menus: dict[str, QMenu] = {}
        self._file_menu = self.menuBar().addMenu("&File")
        self._menus["file"] = self._file_menu

        self._open_file_action = self._file_menu.addAction(
            get_icon("file_open"), "Open Project File…"
        )
        self._open_file_action.triggered.connect(self._open_project_file)

        self._open_folder_action = self._file_menu.addAction(
            get_icon("folder_open"), "Open Project Folder…"
        )
        self._open_folder_action.triggered.connect(self._open_project_folder)

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
        self._exit_action = self._file_menu.addAction(get_icon("exit"), "Exit")
        self._exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self._exit_action.triggered.connect(self.close)

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
        self._settings_action = edit_menu.addAction(
            get_icon("fa6s.gear"),
            "Settings…",
        )
        self._settings_action.triggered.connect(self._open_settings)

        self._command_actions.update(
            {
                "core.project.open-file": self._open_file_action,
                "core.project.open-folder": self._open_folder_action,
                "core.project.save": self._save_action,
                "core.project.save-as": self._save_as_action,
                "core.edit.undo": self._undo_action,
                "core.edit.redo": self._redo_action,
                "core.settings.open": self._settings_action,
            }
        )
        self._rebuild_toolbar_tools()

        self._view_menu = self.menuBar().addMenu("&View")
        self._menus["view"] = self._view_menu

        from setuav_studio.ui.theme import current_theme_mode

        cur_mode = current_theme_mode()
        self._theme_action_group = QActionGroup(self)
        self._theme_action_group.setExclusive(True)
        self._dark_theme_action = QAction("Native Dark", self)
        self._dark_theme_action.setCheckable(True)
        self._dark_theme_action.setChecked(cur_mode == "dark")
        self._dark_theme_action.triggered.connect(lambda: self._switch_theme("dark"))
        self._theme_action_group.addAction(self._dark_theme_action)

        self._light_theme_action = QAction("Native Light", self)
        self._light_theme_action.setCheckable(True)
        self._light_theme_action.setChecked(cur_mode == "light")
        self._light_theme_action.triggered.connect(lambda: self._switch_theme("light"))
        self._theme_action_group.addAction(self._light_theme_action)

        self._blender_theme_action = QAction("Blender Theme", self)
        self._blender_theme_action.setCheckable(True)
        self._blender_theme_action.setChecked(cur_mode == "blender")
        self._blender_theme_action.triggered.connect(lambda: self._switch_theme("blender"))
        self._theme_action_group.addAction(self._blender_theme_action)

        self._github_dark_theme_action = QAction("GitHub Dark", self)
        self._github_dark_theme_action.setCheckable(True)
        self._github_dark_theme_action.setChecked(cur_mode == "github_dark")
        self._github_dark_theme_action.triggered.connect(lambda: self._switch_theme("github_dark"))
        self._theme_action_group.addAction(self._github_dark_theme_action)

        self._github_light_theme_action = QAction("GitHub Light", self)
        self._github_light_theme_action.setCheckable(True)
        self._github_light_theme_action.setChecked(cur_mode == "github_light")
        self._github_light_theme_action.triggered.connect(
            lambda: self._switch_theme("github_light")
        )
        self._theme_action_group.addAction(self._github_light_theme_action)

        self._monokai_theme_action = QAction("Monokai", self)
        self._monokai_theme_action.setCheckable(True)
        self._monokai_theme_action.setChecked(cur_mode == "monokai")
        self._monokai_theme_action.triggered.connect(lambda: self._switch_theme("monokai"))
        self._theme_action_group.addAction(self._monokai_theme_action)

        self._nord_theme_action = QAction("Nord", self)
        self._nord_theme_action.setCheckable(True)
        self._nord_theme_action.setChecked(cur_mode == "nord")
        self._nord_theme_action.triggered.connect(lambda: self._switch_theme("nord"))
        self._theme_action_group.addAction(self._nord_theme_action)
        self._populate_view_menu()

        self._tools_menu = self.menuBar().addMenu("&Tools")
        self._menus["tools"] = self._tools_menu

        self._api.undo_stack.canUndoChanged.connect(self._undo_action.setEnabled)
        self._api.undo_stack.canRedoChanged.connect(self._redo_action.setEnabled)
        self._api.undo_stack.undoTextChanged.connect(self._set_undo_text)
        self._api.undo_stack.redoTextChanged.connect(self._set_redo_text)
        self._api.on_modified_changed(self._on_modified_changed)
        self._api.on_project_content_changed(self._on_project_content_changed)
        self._api.on_selection_changed(self._on_toolbar_context_changed)
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
        self._log_button.setIcon(get_icon("log"))
        self._log_button.setToolTip("Application logs")
        self._log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_button.setAutoRaise(True)
        self._log_button.setFixedSize(22, 22)
        self._log_button.clicked.connect(self._open_log_window)
        self._log_window: QDialog | None = None

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setObjectName("studioStatusProgress")
        self._progress_bar.setFixedWidth(260)
        self._progress_bar.setFixedHeight(18)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_bar.hide()
        self.statusBar().addPermanentWidget(self._progress_bar)

        self._status_label = QLabel(self)
        self._status_label.setObjectName("studioStatusMessage")
        self._status_level = "info"
        self.statusBar().addWidget(self._log_button)
        self.statusBar().addWidget(self._status_label)
        self._api.set_progress_handler(self._show_progress)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status_message)
        self._api.set_status_handler(self._show_status_message)
        self._api.show_status("Ready", "info", 0)
        install_log_buffer()

    def _update_main_toolbar_style(self) -> None:
        self._workspace_toolbar.setStyleSheet("")
        for toolbar in self._toolset_bars.values():
            toolbar.setStyleSheet("")

    def _update_all_icons(self) -> None:
        try:
            if hasattr(self, "_open_file_action"):
                self._open_file_action.setIcon(get_icon("file_open"))
            if hasattr(self, "_open_folder_action"):
                self._open_folder_action.setIcon(get_icon("folder_open"))
            if hasattr(self, "_recent_menu"):
                self._recent_menu.setIcon(get_icon("project_folder"))
            if hasattr(self, "_save_action"):
                self._save_action.setIcon(get_icon("save"))
            if hasattr(self, "_save_as_action"):
                self._save_as_action.setIcon(get_icon("save_as"))
            if hasattr(self, "_exit_action"):
                self._exit_action.setIcon(get_icon("exit"))
            if hasattr(self, "_undo_action"):
                self._undo_action.setIcon(get_icon("undo"))
            if hasattr(self, "_redo_action"):
                self._redo_action.setIcon(get_icon("redo"))
            if hasattr(self, "_settings_action"):
                self._settings_action.setIcon(get_icon("fa6s.gear"))
            if hasattr(self, "_log_button"):
                self._log_button.setIcon(get_icon("log"))
            for contribution_id, contribution in self._toolbar_contributions.items():
                action = self._toolbar_actions.get(contribution_id)
                if action is not None and contribution.icon:
                    action.setIcon(get_icon(contribution.icon))
                for menu_item, menu_action in self._toolbar_menu_actions.get(
                    contribution_id,
                    [],
                ):
                    if menu_item.icon:
                        menu_action.setIcon(get_icon(menu_item.icon))
            self._refresh_workspace_combo()
        except Exception as exc:
            logger.debug("Error refreshing icons: %s", exc)

    def _switch_theme(self, mode: str) -> None:
        from setuav_studio.ui.buttons import refresh_all_button_roles
        from setuav_studio.ui.theme import apply_theme

        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, mode)
            self._update_main_toolbar_style()
            self._update_all_icons()
            self._dark_theme_action.setChecked(mode == "dark")
            self._light_theme_action.setChecked(mode == "light")
            self._blender_theme_action.setChecked(mode == "blender")
            self._github_dark_theme_action.setChecked(mode == "github_dark")
            self._github_light_theme_action.setChecked(mode == "github_light")
            self._monokai_theme_action.setChecked(mode == "monokai")
            self._nord_theme_action.setChecked(mode == "nord")
            self._refresh_status_color()
            for widget in app.allWidgets():
                try:
                    if hasattr(widget, "update_theme_style") and callable(
                        widget.update_theme_style
                    ):
                        widget.update_theme_style()
                except Exception:
                    pass

            # Some plugin hooks rebuild their icons. Reapply semantic colors
            # after those hooks so their button roles always win.
            refresh_all_button_roles(app)

            self.repaint()

            curr_settings = StudioSettings.load()
            if curr_settings.theme_mode != mode:
                from dataclasses import replace

                replace(curr_settings, theme_mode=mode).save()
            self.update()

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
        self._status_level = level
        self._refresh_status_color()
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

    def _refresh_status_color(self) -> None:
        palette = self._status_label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, status_color(self._status_level))
        self._status_label.setPalette(palette)

    def restore_window_layout(self) -> None:
        """Restore the window geometry and active workspace layout."""
        self.restore_window_geometry()
        self.restore_workspace_layout()

    def restore_window_geometry(self) -> None:
        """Restore only the top-level window geometry."""
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def restore_workspace_layout(self) -> None:
        """Restore the active dock perspective after the window is exposed."""
        settings = QSettings()
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
            self._save_current_workspace_layout()
            settings.setValue("active_workspace", self._current_workspace_id)

        # Explicitly close all child dock widgets / plugin panels
        for _, dock in self._panels.values():
            try:
                dock.close()
            except Exception as exc:
                logger.debug("Error closing dock widget: %s", exc)

        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()

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
        project_name = str(project.data.get("name") or project.location.name or project.path.name)
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

    def _collect_unsaved_changes(self) -> list[str]:
        if self._project is None:
            return []

        changes: list[str] = []
        try:
            disk_doc = None
            if self._project.location and self._project.location.exists():
                try:
                    from setuav_studio.project import open_project

                    disk_doc = open_project(self._project.location)
                except Exception:
                    pass

            disk_data = disk_doc.data if disk_doc else {}
            curr_data = self._project.data

            # 1. Components
            disk_comps = {
                c.get("id"): c for c in disk_data.get("components", []) if isinstance(c, dict)
            }
            curr_comps = {
                c.get("id"): c for c in curr_data.get("components", []) if isinstance(c, dict)
            }

            for cid, c in curr_comps.items():
                name = c.get("name") or cid
                if cid not in disk_comps:
                    changes.append(f"New Component: {name}")
                elif disk_comps[cid] != c:
                    changes.append(f"Modified Component: {name}")

            for cid, c in disk_comps.items():
                if cid not in curr_comps:
                    name = c.get("name") or cid
                    changes.append(f"Deleted Component: {name}")

            # 2. Assemblies
            disk_asms = {
                a.get("id"): a for a in disk_data.get("assemblies", []) if isinstance(a, dict)
            }
            curr_asms = {
                a.get("id"): a for a in curr_data.get("assemblies", []) if isinstance(a, dict)
            }

            for aid, a in curr_asms.items():
                name = a.get("name") or aid
                if aid not in disk_asms:
                    changes.append(f"New Assembly: {name}")
                elif disk_asms[aid] != a:
                    changes.append(f"Modified Assembly: {name}")

            # 3. Aerodynamic Analyses
            try:
                from setuav_studio.plugins.aerodynamics.analysis_store import (
                    analysis_entries as aero_entries,
                )

                disk_aero = {e.get("id"): e for e in aero_entries(disk_doc)} if disk_doc else {}
                curr_aero = {e.get("id"): e for e in aero_entries(self._project)}
                for eid, e in curr_aero.items():
                    if eid not in disk_aero:
                        name = e.get("name") or "Aerodynamic Analysis"
                        changes.append(f"Unsaved Aerodynamic Analysis: {name}")
            except Exception:
                pass

            # 4. Flight Performance Analyses
            try:
                from setuav_studio.plugins.flight_performance.analysis_store import (
                    analysis_entries as perf_entries,
                )

                disk_perf = {e.get("id"): e for e in perf_entries(disk_doc)} if disk_doc else {}
                curr_perf = {e.get("id"): e for e in perf_entries(self._project)}
                for eid, e in curr_perf.items():
                    if eid not in disk_perf:
                        name = e.get("name") or "Flight Performance Envelope"
                        changes.append(f"Unsaved Flight Performance Analysis: {name}")
            except Exception:
                pass

        except Exception as exc:
            logger.debug("Failed to collect detailed unsaved changes: %s", exc)

        return changes

    def _confirm_project_close(self) -> bool:
        if self._project is None or not self._project.modified:
            return True

        unsaved_items = self._collect_unsaved_changes()
        proj_name = str(
            self._project.data.get("name") or self._project.location.stem or "Current Project"
        )

        msg_box = QMessageBox(self)
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

    def _update_window_title(self) -> None:
        try:
            if not shiboken6.isValid(self):
                return
        except (RuntimeError, Exception) as exc:
            logger.debug("Window title update skipped (widget invalid): %s", exc)
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
        except (RuntimeError, Exception) as exc:
            logger.debug("Modified listener skipped (widget invalid): %s", exc)
            return
        self._update_window_title()

    def _on_project_content_changed(self, _project: ProjectDocument) -> None:
        try:
            if not shiboken6.isValid(self):
                return
        except (RuntimeError, Exception) as exc:
            logger.debug("Content changed listener skipped (widget invalid): %s", exc)
            return
        self._update_window_title()
        self._refresh_toolbar_action_states()

    def _on_toolbar_context_changed(self, _selection: object | None) -> None:
        self._refresh_toolbar_action_states()

    def _detach_api_listeners(self, *_args: object) -> None:
        self._api.remove_modified_listener(self._on_modified_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)
        self._api.remove_selection_listener(self._on_toolbar_context_changed)

    def _update_actions(self) -> None:
        has_project = self._project is not None
        self._save_action.setEnabled(has_project)
        self._save_as_action.setEnabled(has_project)
        self._refresh_toolbar_action_states()

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
        dialog = SettingsDialog(
            StudioSettings.load(),
            self,
            pages=self._api.settings_pages(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        values.save()
        dialog.apply_plugin_pages()
        self._switch_theme(values.theme_mode)
        self._trim_recent_projects(values.recent_project_limit)
        self._update_recent_menu()

    def _trim_recent_projects(self, limit: int) -> None:
        QSettings().setValue("recent_projects", self._recent_projects()[:limit])

    def _update_view_menu(self, workspace_id: str | None) -> None:
        self._populate_view_menu(workspace_id)

    def _populate_view_menu(self, workspace_id: str | None = None) -> None:
        self._view_menu.clear()
        theme_menu = self._view_menu.addMenu("Theme")
        theme_menu.addAction(self._dark_theme_action)
        theme_menu.addAction(self._light_theme_action)
        theme_menu.addSeparator()
        theme_menu.addAction(self._blender_theme_action)
        theme_menu.addAction(self._github_dark_theme_action)
        theme_menu.addAction(self._github_light_theme_action)
        theme_menu.addAction(self._monokai_theme_action)
        theme_menu.addAction(self._nord_theme_action)
        self._view_menu.addSeparator()
        for cid, (panel_contrib, dock) in self._panels.items():
            if workspace_id is None or panel_contrib.is_in_workspace(workspace_id):
                action = self._panel_actions.get(cid)
                if action is not None:
                    action.setChecked(dock.isVisible())
                    self._update_panel_action_icon(cid)
                    self._view_menu.addAction(action)

    def _update_panel_action_icon(self, panel_id: str) -> None:
        action = self._panel_actions.get(panel_id)
        if action is None:
            return
        action.setIcon(get_icon("fa6s.square-check" if action.isChecked() else "fa6s.square"))

    def _sync_panel_action(self, panel_id: str) -> None:
        entry = self._panels.get(panel_id)
        action = self._panel_actions.get(panel_id)
        if entry is None or action is None:
            return
        _, dock = entry
        action.setChecked(dock.isVisible())
        self._update_panel_action_icon(panel_id)

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

    def _add_toolbar_item(self, contribution: ToolbarContribution) -> None:
        if contribution.id in self._toolbar_contributions:
            self._remove_toolbar_item(contribution.id)

        self._toolbar_contributions[contribution.id] = contribution
        if contribution.callback is not None:
            action = QAction(contribution.title, self)
            action.triggered.connect(contribution.callback)
            self._toolbar_actions[contribution.id] = action
            self._owned_toolbar_actions.add(contribution.id)
        elif contribution.command is not None:
            action = self._command_actions.get(contribution.command or "")
            if action is not None:
                self._toolbar_actions[contribution.id] = action
        else:
            action = QAction(contribution.title, self)
            self._toolbar_actions[contribution.id] = action
            self._owned_toolbar_actions.add(contribution.id)

        action = self._toolbar_actions.get(contribution.id)
        if action is not None:
            action.setToolTip(contribution.title)
            if contribution.icon:
                action.setIcon(get_icon(contribution.icon))
            if contribution.menu_items:
                menu = QMenu(contribution.title, self)
                menu_actions: list[tuple[ToolbarMenuItemContribution, QAction]] = []
                for menu_item in contribution.menu_items:
                    if menu_item.icon:
                        menu_action = menu.addAction(
                            get_icon(menu_item.icon),
                            menu_item.title,
                        )
                    else:
                        menu_action = menu.addAction(menu_item.title)
                    menu_action.triggered.connect(
                        lambda _checked=False, callback=menu_item.callback: callback()
                    )
                    menu_actions.append((menu_item, menu_action))
                action.setMenu(menu)
                self._toolbar_menu_actions[contribution.id] = menu_actions
        self._rebuild_toolbar_tools()
        self._refresh_toolbar_action_states()

    def _remove_toolbar_item(self, contribution_id: str) -> None:
        self._toolbar_contributions.pop(contribution_id, None)
        action = self._toolbar_actions.pop(contribution_id, None)
        self._toolbar_menu_actions.pop(contribution_id, None)
        owned = contribution_id in self._owned_toolbar_actions
        self._owned_toolbar_actions.discard(contribution_id)
        self._rebuild_toolbar_tools()
        if owned and action is not None:
            menu = action.menu()
            if menu is not None:
                menu.deleteLater()
            action.deleteLater()

    def _refresh_toolbar_action_states(self) -> None:
        for contribution_id, contribution in self._toolbar_contributions.items():
            action = self._toolbar_actions.get(contribution_id)
            if action is None:
                continue
            enabled = True
            if contribution.enabled_when is not None:
                try:
                    enabled = bool(contribution.enabled_when())
                except Exception:
                    logger.exception(
                        "Could not evaluate toolbar state: %s",
                        contribution_id,
                    )
                    enabled = False

            menu_has_enabled_item = not contribution.menu_items
            for menu_item, menu_action in self._toolbar_menu_actions.get(
                contribution_id,
                [],
            ):
                item_enabled = True
                if menu_item.enabled_when is not None:
                    try:
                        item_enabled = bool(menu_item.enabled_when())
                    except Exception:
                        logger.exception(
                            "Could not evaluate toolbar menu state: %s",
                            menu_item.title,
                        )
                        item_enabled = False
                menu_action.setEnabled(enabled and item_enabled)
                menu_has_enabled_item = menu_has_enabled_item or item_enabled
            action.setEnabled(enabled and menu_has_enabled_item)

    def _rebuild_toolbar_tools(self) -> None:
        workspace_id = self._current_workspace_id or self._api.current_workspace_id
        grouped_actions: dict[str, list[QAction]] = {}
        group_order: list[str] = []
        contributions = sorted(
            self._toolbar_contributions.values(),
            key=lambda item: (item.order, item.group, item.title.casefold()),
        )
        for contribution in contributions:
            if not contribution.is_in_workspace(workspace_id):
                continue
            action = self._toolbar_actions.get(contribution.id)
            if action is None and contribution.command:
                action = self._command_actions.get(contribution.command)
                if action is not None:
                    self._toolbar_actions[contribution.id] = action
                    action.setToolTip(contribution.title)
                    if contribution.icon:
                        action.setIcon(get_icon(contribution.icon))
            if action is not None:
                if contribution.group not in grouped_actions:
                    grouped_actions[contribution.group] = []
                    group_order.append(contribution.group)
                grouped_actions[contribution.group].append(action)

        registered_groups = {
            contribution.group for contribution in self._toolbar_contributions.values()
        }
        for group, toolbar in list(self._toolset_bars.items()):
            if group not in registered_groups:
                self.removeToolBar(toolbar)
                toolbar.deleteLater()
                del self._toolset_bars[group]

        for group in group_order:
            toolbar = self._toolset_bars.get(group)
            if toolbar is None:
                toolbar = ToolSetBar(group, self)
                self._toolset_bars[group] = toolbar
                self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
            toolbar.set_tools(grouped_actions[group])
            toolbar.show()

        for group, toolbar in self._toolset_bars.items():
            if group not in grouped_actions:
                toolbar.set_tools([])
                toolbar.hide()

    def _add_workspace(self, contribution: WorkspaceContribution) -> None:
        self._workspaces[contribution.id] = contribution
        self._refresh_workspace_combo()

    def _remove_workspace(self, workspace_id: str) -> None:
        if workspace_id not in self._workspaces:
            return
        del self._workspaces[workspace_id]
        self._workspace_states.pop(workspace_id, None)
        QSettings().remove(f"workspace_perspective/{workspace_id}")
        self._refresh_workspace_combo()
        for panel_id in list(self._panels):
            contribution, _ = self._panels[panel_id]
            if contribution.workspace_id == workspace_id or (
                isinstance(contribution.workspace_id, (list, tuple, set))
                and workspace_id in contribution.workspace_id
            ):
                self._remove_panel(panel_id)

    def _refresh_workspace_combo(self) -> None:
        workspaces = sorted(
            self._workspaces.values(),
            key=lambda item: (item.order, item.title.casefold()),
        )
        current_id = self._current_workspace_id or self._api.current_workspace_id
        self._workspace_toolbar.set_workspaces(workspaces, current_id)

    def _switch_workspace(self, workspace_id: str) -> None:
        if workspace_id not in self._workspaces:
            return

        # 1. Save previous workspace perspective
        if self._current_workspace_id is not None and self._current_workspace_id != workspace_id:
            prev_state = self.saveState(self._LAYOUT_VERSION)
            self._workspace_states[self._current_workspace_id] = prev_state
            QSettings().setValue(
                f"workspace_perspective/{self._current_workspace_id}",
                prev_state,
            )

        self._current_workspace_id = workspace_id
        self._workspace_toolbar.set_current_workspace(workspace_id)
        self._rebuild_toolbar_tools()

        # 2. Restore saved workspace perspective if available, or apply default layout
        settings = QSettings()
        saved_state = self._workspace_states.get(workspace_id) or settings.value(
            f"workspace_perspective/{workspace_id}"
        )
        self._restoring_workspace_layout = True
        try:
            if saved_state is not None:
                self.restoreState(saved_state, self._LAYOUT_VERSION)
                # Ensure any dock not belonging to this workspace is hidden
                for _cid, (panel_contrib, dock) in self._panels.items():
                    if not panel_contrib.is_in_workspace(workspace_id):
                        dock.hide()
            else:
                self._apply_default_workspace_layout(workspace_id)
        finally:
            self._restoring_workspace_layout = False

        # 3. Update View menu actions for the active workspace only
        self._update_view_menu(workspace_id)

    def _schedule_workspace_layout_save(self, *_args) -> None:
        if (
            not self._layout_persistence_enabled
            or self._restoring_workspace_layout
            or self._current_workspace_id is None
        ):
            return
        if self._layout_save_scheduled:
            return
        self._layout_save_scheduled = True
        QTimer.singleShot(0, self._save_current_workspace_layout)

    def _save_current_workspace_layout(self) -> None:
        self._layout_save_scheduled = False
        workspace_id = self._current_workspace_id
        if workspace_id is None or self._restoring_workspace_layout:
            return
        state = self.saveState(self._LAYOUT_VERSION)
        self._workspace_states[workspace_id] = state
        QSettings().setValue(f"workspace_perspective/{workspace_id}", state)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_workspace_layout_save()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._layout_persistence_enabled:
            QTimer.singleShot(0, self._enable_layout_persistence)

    def _enable_layout_persistence(self) -> None:
        self._layout_persistence_enabled = True

    def eventFilter(self, watched, event) -> bool:
        if isinstance(watched, QDockWidget) and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            self._schedule_workspace_layout_save()
        return super().eventFilter(watched, event)

    def _apply_default_workspace_layout(self, workspace_id: str) -> None:
        explorer = self.findChild(QDockWidget, "project.explorer")
        viewer = self.findChild(QDockWidget, "studio.viewer.opengl")
        props = self.findChild(QDockWidget, "studio.properties")
        controls = self.findChild(QDockWidget, "propulsion.controls_dock")
        results = self.findChild(QDockWidget, "propulsion.results_dock")

        # Hide any panels that do not belong to this workspace
        for _cid, (panel_contrib, dock) in self._panels.items():
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
                viewer.raise_()
            if props:
                props.show()

            docks = [d for d in [explorer, viewer, props] if d is not None and not d.isHidden()]
            if docks:
                self.resizeDocks(docks, [260, 680, 260][: len(docks)], Qt.Orientation.Horizontal)

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

            for d in (explorer, props, controls, charts, results):
                if d:
                    d.show()

            docks = [
                d
                for d in [explorer, controls, charts, results]
                if d is not None and not d.isHidden()
            ]
            if docks:
                self.resizeDocks(
                    docks, [220, 280, 480, 260][: len(docks)], Qt.Orientation.Horizontal
                )

        elif workspace_id == "studio.workspace.aerodynamics":
            aero_controls = self.findChild(QDockWidget, "aerodynamics.controls_dock")
            aero_charts = self.findChild(QDockWidget, "aerodynamics.charts_dock")
            aero_results = self.findChild(QDockWidget, "aerodynamics.results_dock")

            if viewer:
                viewer.hide()
            if explorer and props:
                self.splitDockWidget(explorer, props, Qt.Orientation.Vertical)
            if explorer and aero_controls:
                self.splitDockWidget(explorer, aero_controls, Qt.Orientation.Horizontal)
            if aero_controls and aero_charts:
                self.splitDockWidget(aero_controls, aero_charts, Qt.Orientation.Horizontal)
            if aero_charts and aero_results:
                self.splitDockWidget(aero_charts, aero_results, Qt.Orientation.Horizontal)
            elif aero_controls and aero_results:
                self.splitDockWidget(aero_controls, aero_results, Qt.Orientation.Horizontal)

            for d in (explorer, props, aero_controls, aero_charts, aero_results):
                if d:
                    d.show()

            docks = [
                d
                for d in [explorer, aero_controls, aero_charts, aero_results]
                if d is not None and not d.isHidden()
            ]
            if docks:
                self.resizeDocks(
                    docks, [200, 260, 560, 260][: len(docks)], Qt.Orientation.Horizontal
                )

        elif workspace_id == "studio.workspace.flight_performance":
            fp_controls = self.findChild(QDockWidget, "flight_performance.controls_dock")
            fp_charts = self.findChild(QDockWidget, "flight_performance.charts_dock")
            fp_results = self.findChild(QDockWidget, "flight_performance.results_dock")

            if viewer:
                viewer.hide()
            if explorer and props:
                self.splitDockWidget(explorer, props, Qt.Orientation.Vertical)
            if explorer and fp_controls:
                self.splitDockWidget(explorer, fp_controls, Qt.Orientation.Horizontal)
            if fp_controls and fp_charts:
                self.splitDockWidget(fp_controls, fp_charts, Qt.Orientation.Horizontal)
            if fp_charts and fp_results:
                self.splitDockWidget(fp_charts, fp_results, Qt.Orientation.Horizontal)
            elif fp_controls and fp_results:
                self.splitDockWidget(fp_controls, fp_results, Qt.Orientation.Horizontal)

            for d in (explorer, props, fp_controls, fp_charts, fp_results):
                if d:
                    d.show()

            docks = [
                d
                for d in [explorer, fp_controls, fp_charts, fp_results]
                if d is not None and not d.isHidden()
            ]
            if docks:
                self.resizeDocks(
                    docks, [200, 260, 560, 260][: len(docks)], Qt.Orientation.Horizontal
                )

        elif workspace_id == "studio.workspace.weight_balance":
            wb_view = self.findChild(QDockWidget, "weight_balance.view_dock")
            wb_results = self.findChild(QDockWidget, "weight_balance.results_dock")

            if viewer:
                viewer.hide()
            if explorer and props:
                self.splitDockWidget(explorer, props, Qt.Orientation.Vertical)
            if explorer and wb_view:
                self.splitDockWidget(explorer, wb_view, Qt.Orientation.Horizontal)
            if wb_view and wb_results:
                self.splitDockWidget(wb_view, wb_results, Qt.Orientation.Horizontal)

            if wb_results and props:
                self.splitDockWidget(wb_results, props, Qt.Orientation.Vertical)

            for dock in (explorer, props, wb_view, wb_results):
                if dock:
                    dock.show()

            docks = [
                dock
                for dock in (explorer, wb_view, wb_results)
                if dock is not None and not dock.isHidden()
            ]
            if docks:
                self.resizeDocks(
                    docks,
                    [220, 600, 340][: len(docks)],
                    Qt.Orientation.Horizontal,
                )

        else:
            for _cid, (panel_contrib, dock) in self._panels.items():
                if panel_contrib.is_in_workspace(workspace_id):
                    dock.show()
                else:
                    dock.hide()
