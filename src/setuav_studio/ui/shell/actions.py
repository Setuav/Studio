from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import shiboken6
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMenu

from setuav_studio.plugins.core.settings import SettingsDialog, StudioSettings
from setuav_studio.ui.about_dialog import AboutDialog
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.plugin_manager import PluginManagerDialog
from setuav_studio_sdk import ActionContribution

if TYPE_CHECKING:
    from setuav_studio.plugin_system import PluginManager, StudioAPI

logger = logging.getLogger(__name__)


class ActionManager:
    """Manages shell menus, standard actions, themes, and dynamic plugin actions."""

    def __init__(self, window: QMainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self._host = api._host
        self.menus: dict[str, QMenu] = {}
        self.command_actions: dict[str, QAction] = {}
        self.panel_actions: dict[str, QAction] = {}
        self.plugin_manager: PluginManager | None = None
        self._plugin_manager_dialog: PluginManagerDialog | None = None

        self._setup_menus()

    def _setup_menus(self) -> None:
        menu_bar = self._window.menuBar()

        # File Menu
        self.file_menu = menu_bar.addMenu("&File")
        self.menus["file"] = self.file_menu

        self.new_project_action = self.file_menu.addAction(get_icon("file_new"), "New Project…")
        self.new_project_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_project_action.triggered.connect(self._window._new_project)

        self.open_folder_action = self.file_menu.addAction(get_icon("folder_open"), "Open Project…")
        self.open_folder_action.triggered.connect(self._window._open_project_folder)

        self.recent_menu = QMenu("Open Recent", self.file_menu)
        self.recent_menu.setIcon(get_icon("project_folder"))
        self.file_menu.addMenu(self.recent_menu)
        self.menus["file/open recent"] = self.recent_menu
        self.file_menu.addSeparator()

        self.save_action = self.file_menu.addAction(get_icon("save"), "Save")
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._window.save_project)

        self.save_as_action = self.file_menu.addAction(get_icon("save_as"), "Save As…")
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self._window.save_project_as)

        self.file_menu.addSeparator()
        self.exit_action = self.file_menu.addAction(get_icon("exit"), "Exit")
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.exit_action.triggered.connect(self._window.close)

        # Edit Menu
        self.edit_menu = menu_bar.addMenu("&Edit")
        self.menus["edit"] = self.edit_menu
        self.undo_action = self.edit_menu.addAction(get_icon("undo"), "Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self._api.undo)
        self.undo_action.setEnabled(False)

        self.redo_action = self.edit_menu.addAction(get_icon("redo"), "Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self._api.redo)
        self.redo_action.setEnabled(False)

        self.edit_menu.addSeparator()
        self.settings_action = self.edit_menu.addAction(get_icon("fa6s.gear"), "Settings…")
        self.settings_action.triggered.connect(self.open_settings)

        self.command_actions.update(
            {
                "core.project.new": self.new_project_action,
                "core.project.open-folder": self.open_folder_action,
                "core.project.save": self.save_action,
                "core.project.save-as": self.save_as_action,
                "core.edit.undo": self.undo_action,
                "core.edit.redo": self.redo_action,
                "core.settings.open": self.settings_action,
            }
        )

        # View Menu
        self.view_menu = menu_bar.addMenu("&View")
        self.menus["view"] = self.view_menu

        from setuav_studio.ui.theme import current_theme_mode

        cur_mode = current_theme_mode()
        self.theme_action_group = QActionGroup(self._window)
        self.theme_action_group.setExclusive(True)

        self.dark_theme_action = self._create_theme_action("Native Dark", "dark", cur_mode)
        self.light_theme_action = self._create_theme_action("Native Light", "light", cur_mode)
        self.blender_theme_action = self._create_theme_action("Blender Theme", "blender", cur_mode)
        self.github_dark_theme_action = self._create_theme_action(
            "GitHub Dark", "github_dark", cur_mode
        )
        self.github_light_theme_action = self._create_theme_action(
            "GitHub Light", "github_light", cur_mode
        )
        self.monokai_theme_action = self._create_theme_action("Monokai", "monokai", cur_mode)
        self.nord_theme_action = self._create_theme_action("Nord", "nord", cur_mode)

        self.populate_view_menu()

        # Tools Menu
        self.tools_menu = menu_bar.addMenu("&Tools")
        self.menus["tools"] = self.tools_menu
        self.constraints_action = self.tools_menu.addAction(
            get_icon("settings"),
            "Design Constraints…",
            self.open_constraints,
        )
        self.command_actions["core.constraints.manage"] = self.constraints_action
        self.plugin_manager_action = self.tools_menu.addAction("Plugin Manager…")
        self.plugin_manager_action.setEnabled(False)
        self.plugin_manager_action.triggered.connect(self.open_plugin_manager)
        self.command_actions["core.plugins.manage"] = self.plugin_manager_action

        # Help Menu
        self.help_menu = menu_bar.addMenu("&Help")
        self.menus["help"] = self.help_menu
        self.about_action = self.help_menu.addAction("About")
        self.about_action.triggered.connect(self.open_about)
        self.command_actions["core.help.about"] = self.about_action

        # Undo stack connections
        self._host.undo_stack.canUndoChanged.connect(self.undo_action.setEnabled)
        self._host.undo_stack.canRedoChanged.connect(self.redo_action.setEnabled)
        self._host.undo_stack.undoTextChanged.connect(self.set_undo_text)
        self._host.undo_stack.redoTextChanged.connect(self.set_redo_text)

        self.update_recent_menu()
        self.update_actions()

    def _create_theme_action(self, title: str, mode: str, cur_mode: str) -> QAction:
        action = QAction(title, self._window)
        action.setCheckable(True)
        action.setChecked(cur_mode == mode)
        action.triggered.connect(lambda: self.switch_theme(mode))
        self.theme_action_group.addAction(action)
        return action

    def switch_theme(self, mode: str) -> None:
        from setuav_studio.ui.buttons import refresh_all_button_roles
        from setuav_studio.ui.theme import apply_theme

        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, mode)
            if hasattr(self._window, "_update_main_toolbar_style"):
                self._window._update_main_toolbar_style()
            self.update_all_icons()
            self.dark_theme_action.setChecked(mode == "dark")
            self.light_theme_action.setChecked(mode == "light")
            self.blender_theme_action.setChecked(mode == "blender")
            self.github_dark_theme_action.setChecked(mode == "github_dark")
            self.github_light_theme_action.setChecked(mode == "github_light")
            self.monokai_theme_action.setChecked(mode == "monokai")
            self.nord_theme_action.setChecked(mode == "nord")
            if hasattr(self._window, "_refresh_status_color"):
                self._window._refresh_status_color()
            for widget in app.allWidgets():
                try:
                    if hasattr(widget, "update_theme_style") and callable(
                        widget.update_theme_style
                    ):
                        widget.update_theme_style()
                except Exception:
                    pass

            refresh_all_button_roles(app)
            self._window.repaint()

            curr_settings = StudioSettings.load()
            if curr_settings.theme_mode != mode:
                from dataclasses import replace

                replace(curr_settings, theme_mode=mode).save()
            self._window.update()

    def update_all_icons(self) -> None:
        try:
            self.new_project_action.setIcon(get_icon("file_new"))
            self.open_folder_action.setIcon(get_icon("folder_open"))
            self.recent_menu.setIcon(get_icon("project_folder"))
            self.save_action.setIcon(get_icon("save"))
            self.save_as_action.setIcon(get_icon("save_as"))
            self.exit_action.setIcon(get_icon("exit"))
            self.undo_action.setIcon(get_icon("undo"))
            self.redo_action.setIcon(get_icon("redo"))
            self.settings_action.setIcon(get_icon("fa6s.gear"))
            if hasattr(self._window, "_log_button"):
                self._window._log_button.setIcon(get_icon("log"))
            if hasattr(self._window, "_update_toolbar_contribution_icons"):
                self._window._update_toolbar_contribution_icons()
            if hasattr(self._window, "_refresh_workspace_combo"):
                self._window._refresh_workspace_combo()
        except Exception as exc:
            logger.debug("Error refreshing icons: %s", exc)

    def populate_view_menu(self, workspace_id: str | None = None) -> None:
        self.view_menu.clear()
        theme_menu = self.view_menu.addMenu("Theme")
        theme_menu.addAction(self.dark_theme_action)
        theme_menu.addAction(self.light_theme_action)
        theme_menu.addSeparator()
        theme_menu.addAction(self.blender_theme_action)
        theme_menu.addAction(self.github_dark_theme_action)
        theme_menu.addAction(self.github_light_theme_action)
        theme_menu.addAction(self.monokai_theme_action)
        theme_menu.addAction(self.nord_theme_action)
        self.view_menu.addSeparator()

        panels = getattr(self._window, "_panels", {})
        for cid, (panel_contrib, dock) in panels.items():
            if workspace_id is None or panel_contrib.is_in_workspace(workspace_id):
                action = self.panel_actions.get(cid)
                if action is not None:
                    action.setChecked(dock.isVisible())
                    self.update_panel_action_icon(cid)
                    self.view_menu.addAction(action)

        self.view_menu.addSeparator()
        reset_layout_action = QAction("Reset Workspace Layout", self._window)
        reset_layout_action.setIcon(get_icon("fa6s.arrow-rotate-left"))
        reset_layout_action.triggered.connect(self._window._reset_current_workspace_layout)
        self.view_menu.addAction(reset_layout_action)

    def update_view_menu(self, workspace_id: str | None) -> None:
        self.populate_view_menu(workspace_id)

    def update_panel_action_icon(self, panel_id: str) -> None:
        action = self.panel_actions.get(panel_id)
        if action is not None:
            action.setIcon(get_icon("fa6s.square-check" if action.isChecked() else "fa6s.square"))

    def sync_panel_action(self, panel_id: str) -> None:
        panels = getattr(self._window, "_panels", {})
        entry = panels.get(panel_id)
        action = self.panel_actions.get(panel_id)
        if entry is None or action is None:
            return
        _, dock = entry
        action.setChecked(dock.isVisible())
        self.update_panel_action_icon(panel_id)

    def update_actions(self) -> None:
        has_project = getattr(self._window, "_project", None) is not None
        self.save_action.setEnabled(has_project)
        self.save_as_action.setEnabled(has_project)
        if hasattr(self._window, "_refresh_toolbar_action_states"):
            self._window._refresh_toolbar_action_states()

    def set_undo_text(self, text: str) -> None:
        if hasattr(self, "undo_action") and shiboken6.isValid(self.undo_action):
            self.undo_action.setText(f"Undo {text}" if text else "Undo")

    def set_redo_text(self, text: str) -> None:
        if hasattr(self, "redo_action") and shiboken6.isValid(self.redo_action):
            self.redo_action.setText(f"Redo {text}" if text else "Redo")

    def update_recent_menu(self) -> None:
        if not hasattr(self, "recent_menu") or not shiboken6.isValid(self.recent_menu):
            return
        self.recent_menu.clear()
        recent = (
            self._window._recent_projects() if hasattr(self._window, "_recent_projects") else []
        )
        if not recent:
            empty_action = self.recent_menu.addAction("No Recent Projects")
            empty_action.setEnabled(False)
            return
        for path in recent:
            action = self.recent_menu.addAction(path)
            action.triggered.connect(
                lambda _checked=False, val=path: self._window.open_project(val)
            )
        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction("Clear Recent Projects")
        clear_action.triggered.connect(self._window._clear_recent_projects)

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            StudioSettings.load(),
            self._window,
            pages=self._host.settings_pages(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        values.save()
        dialog.apply_plugin_pages()
        dialog.apply_units()
        if hasattr(self._window, "_switch_theme"):
            self._window._switch_theme(values.theme_mode)
        else:
            self.switch_theme(values.theme_mode)
        if hasattr(self._window, "_trim_recent_projects"):
            self._window._trim_recent_projects(values.recent_project_limit)
        if hasattr(self._window, "_update_recent_menu"):
            self._window._update_recent_menu()
        else:
            self.update_recent_menu()

    def open_about(self) -> None:
        AboutDialog(self._window).exec()

    def open_constraints(self) -> None:
        from setuav_studio.plugins.core.ui.constraints_dialog import ManageConstraintsDialog

        dlg = ManageConstraintsDialog(self._api, parent=self._window)
        dlg.exec()

    def bind_plugin_manager(self, manager: PluginManager) -> None:
        self.plugin_manager = manager
        self.plugin_manager_action.setEnabled(True)

    def open_plugin_manager(self) -> None:
        if self.plugin_manager is None:
            return
        if self._plugin_manager_dialog is None:
            self._plugin_manager_dialog = PluginManagerDialog(self.plugin_manager, self._window)
        self._plugin_manager_dialog.refresh()
        self._plugin_manager_dialog.exec()

    def add_action(self, contribution: ActionContribution) -> None:
        parts = [p.strip().replace("&", "") for p in contribution.menu.split("/") if p.strip()]
        if not parts:
            parts = ["Tools"]

        path_key = ""
        current_menu = None
        for i, name in enumerate(parts):
            path_key = f"{path_key}/{name.lower()}" if path_key else name.lower()
            if path_key in self.menus and shiboken6.isValid(self.menus[path_key]):
                current_menu = self.menus[path_key]
            else:
                if i == 0:
                    current_menu = self._window.menuBar().addMenu(f"&{name}")
                else:
                    sub = QMenu(f"&{name}", current_menu)
                    current_menu.addMenu(sub)
                    current_menu = sub
                self.menus[path_key] = current_menu

        icon = get_icon(contribution.icon) if contribution.icon else None
        if icon is not None and not icon.isNull():
            action = current_menu.addAction(icon, contribution.title)
        else:
            action = current_menu.addAction(contribution.title)

        if contribution.shortcut:
            action.setShortcut(QKeySequence(contribution.shortcut))

        action.triggered.connect(contribution.callback)

    def remove_action(self, menu_path: str, title: str) -> None:
        parts = [p.strip().replace("&", "") for p in menu_path.split("/") if p.strip()]
        if not parts:
            parts = ["Tools"]
        path_key = ""
        for name in parts:
            path_key = f"{path_key}/{name.lower()}" if path_key else name.lower()
        menu = self.menus.get(path_key)
        if menu is None or not shiboken6.isValid(menu):
            return
        for action in menu.actions():
            if action.text() == title:
                menu.removeAction(action)
                break

        for index in range(len(parts), 1, -1):
            child_key = "/".join(part.lower() for part in parts[:index])
            child = self.menus.get(child_key)
            if child is None or not shiboken6.isValid(child) or child.actions():
                break
            parent_key = "/".join(part.lower() for part in parts[: index - 1])
            parent = self.menus.get(parent_key)
            if parent is not None and shiboken6.isValid(parent):
                parent.removeAction(child.menuAction())
            self.menus.pop(child_key, None)
            child.deleteLater()


__all__ = ["ActionManager"]
