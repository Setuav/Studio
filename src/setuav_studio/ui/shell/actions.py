from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import shiboken6
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QDialog, QMenu

from setuav_studio.api import ActionContribution
from setuav_studio.ui.dialog.about import AboutDialog
from setuav_studio.ui.dialog.plugin_manager import PluginManagerDialog
from setuav_studio.ui.settings.settings_pages import SettingsDialog, StudioSettings
from setuav_studio.ui.shell.command_palette import CommandPaletteDialog
from setuav_studio.ui.style.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI
    from setuav_studio.plugin import PluginManager
    from setuav_studio.ui.shell.window import MainWindow

logger = logging.getLogger(__name__)


class ActionManager:
    """Manages shell menus, standard actions, themes, and dynamic plugin actions."""

    def __init__(self, window: MainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self._host = api._host
        self.menus: dict[str, QMenu] = {}
        self.command_actions: dict[str, QAction] = {}
        self.panel_actions: dict[str, QAction] = {}
        self.plugin_manager: PluginManager | None = None
        self._plugin_manager_dialog: PluginManagerDialog | None = None
        self._command_palette_dialog: CommandPaletteDialog | None = None

        self._setup_menus()

    def _setup_menus(self) -> None:
        menu_bar = self._window.menuBar()

        # File Menu
        self.file_menu = menu_bar.addMenu("&File")
        self.menus["file"] = self.file_menu

        self.new_project_action = self.file_menu.addAction(get_icon("file_new"), "New Project…")
        self.new_project_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_project_action.triggered.connect(self._window.project_controller.new_project)

        self.open_action = self.file_menu.addAction(get_icon("folder_open"), "Open Project…")
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._window.project_controller.open_project_dialog)

        self.open_project_action = self.open_action
        self.open_folder_action = self.open_action

        self.open_directory_action = self.file_menu.addAction(
            get_icon("project_folder"), "Open Project Folder…"
        )
        self.open_directory_action.triggered.connect(
            self._window.project_controller.open_project_folder
        )

        self.recent_menu = QMenu("Open Recent", self.file_menu)
        self.recent_menu.setIcon(get_icon("project_folder"))
        self.file_menu.addMenu(self.recent_menu)
        self.menus["file/open recent"] = self.recent_menu
        self.file_menu.addSeparator()

        self.save_action = self.file_menu.addAction(get_icon("save"), "Save")
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._window.project_controller.save_project)

        self.save_as_action = self.file_menu.addAction(get_icon("save_as"), "Save As…")
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self._window.project_controller.save_project_as)

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
        self.settings_action = self.edit_menu.addAction(get_icon("settings"), "Settings…")
        self.settings_action.triggered.connect(self.open_settings)

        self.command_actions.update(
            {
                "core.project.new": self.new_project_action,
                "core.project.open": self.open_action,
                "core.project.open-folder": self.open_directory_action,
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

        self.command_palette_action = QAction(
            get_icon("command_palette"),
            "Command Palette…",
            self._window,
        )
        self.command_palette_action.setShortcut("Ctrl+Shift+P")
        self.command_palette_action.triggered.connect(self.open_command_palette)
        self._f1_shortcut = QShortcut(QKeySequence("F1"), self._window)
        self._f1_shortcut.activated.connect(self.open_command_palette)
        self.command_actions["core.command_palette.open"] = self.command_palette_action

        from setuav_studio.ui.style.theme import current_theme_mode

        cur_mode = current_theme_mode()
        self.theme_action_group = QActionGroup(self._window)
        self.theme_action_group.setExclusive(True)

        self.native_theme_action = self._create_theme_action("Native", "native", cur_mode)
        self.blender_theme_action = self._create_theme_action("Blender", "blender", cur_mode)
        self.github_theme_action = self._create_theme_action("GitHub", "github", cur_mode)
        self.monokai_theme_action = self._create_theme_action("Monokai", "monokai", cur_mode)
        self.nord_theme_action = self._create_theme_action("Nord", "nord", cur_mode)

        self.populate_view_menu()

        # Tools Menu
        self.tools_menu = menu_bar.addMenu("&Tools")
        self.menus["tools"] = self.tools_menu
        self.tools_menu.addAction(self.command_palette_action)
        self.task_manager_action = self.tools_menu.addAction(
            get_icon("task_manager"),
            "Task Manager…",
            self.open_task_manager,
        )
        self.task_manager_action.setShortcut("Ctrl+T")
        self.task_monitor_action = self.task_manager_action
        self.command_actions["core.tasks.manage"] = self.task_manager_action
        self.plugin_manager_action = self.tools_menu.addAction(
            get_icon("plugin_manager"),
            "Plugin Manager…",
            self.open_plugin_manager,
        )
        self.plugin_manager_action.setShortcut("Ctrl+P")
        self.plugin_manager_action.setEnabled(False)
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
        from setuav_studio.ui.style.theme import apply_theme
        from setuav_studio.ui.widget.button import refresh_all_button_roles

        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, mode)
            self._window.toolbar_manager.update_main_toolbar_style()
            self.update_all_icons()
            self.native_theme_action.setChecked(mode == "native")
            self.blender_theme_action.setChecked(mode == "blender")
            self.github_theme_action.setChecked(mode == "github")
            self.monokai_theme_action.setChecked(mode == "monokai")
            self.nord_theme_action.setChecked(mode == "nord")
            self._window.status_manager.refresh_status_color()
            for widget in app.allWidgets():
                update_theme_style = getattr(widget, "update_theme_style", None)
                if callable(update_theme_style):
                    update_theme_style()

            refresh_all_button_roles(app)
            self._window.repaint()

            curr_settings = StudioSettings.load()
            if curr_settings.theme_mode != mode:
                from dataclasses import replace

                replace(curr_settings, theme_mode=mode).save()
            self._window.update()

    def update_all_icons(self) -> None:
        self.new_project_action.setIcon(get_icon("file_new"))
        self.open_action.setIcon(get_icon("folder_open"))
        self.open_directory_action.setIcon(get_icon("project_folder"))
        self.recent_menu.setIcon(get_icon("project_folder"))
        self.save_action.setIcon(get_icon("save"))
        self.save_as_action.setIcon(get_icon("save_as"))
        self.exit_action.setIcon(get_icon("exit"))
        self.undo_action.setIcon(get_icon("undo"))
        self.redo_action.setIcon(get_icon("redo"))
        self.settings_action.setIcon(get_icon("settings"))
        self._window.status_manager.log_button.setIcon(get_icon("log"))
        self._window.status_manager.command_palette_button.setIcon(get_icon("command_palette"))
        self._window.toolbar_manager.update_toolbar_contribution_icons()

    def populate_view_menu(self) -> None:
        self.view_menu.clear()
        theme_menu = self.view_menu.addMenu(get_icon("settings_appearance"), "Theme")
        theme_menu.addAction(self.native_theme_action)
        theme_menu.addAction(self.blender_theme_action)
        theme_menu.addAction(self.github_theme_action)
        theme_menu.addAction(self.monokai_theme_action)
        theme_menu.addAction(self.nord_theme_action)
        self.view_menu.addSeparator()

        panels = self._window._panels
        for cid, (_panel_contrib, dock) in panels.items():
            action = self.panel_actions.get(cid)
            if action is not None:
                action.setChecked(dock.isVisible())
                self.update_panel_action_icon(cid)
                self.view_menu.addAction(action)

        self.view_menu.addSeparator()
        reset_layout_action = QAction("Reset Layout", self._window)
        reset_layout_action.setIcon(get_icon("fa6s.arrow-rotate-left"))
        reset_layout_action.triggered.connect(self._window.layout_manager.reset_layout)
        self.view_menu.addAction(reset_layout_action)

    def update_view_menu(self) -> None:
        self.populate_view_menu()

    def update_panel_action_icon(self, panel_id: str) -> None:
        action = self.panel_actions.get(panel_id)
        if action is not None:
            action.setIcon(get_icon("fa6s.square-check" if action.isChecked() else "fa6s.square"))

    def sync_panel_action(self, panel_id: str) -> None:
        entry = self._window._panels.get(panel_id)
        action = self.panel_actions.get(panel_id)
        if entry is None or action is None or not shiboken6.isValid(action):
            return
        _, dock = entry
        action.setChecked(dock.isVisible())
        self.update_panel_action_icon(panel_id)

    def update_actions(self) -> None:
        has_project = self._window.project_controller.project is not None
        self.save_action.setEnabled(has_project)
        self.save_as_action.setEnabled(has_project)
        self._window.toolbar_manager.update_toolbar_states()

    def set_undo_text(self, text: str) -> None:
        if shiboken6.isValid(self.undo_action):
            self.undo_action.setText(f"Undo {text}" if text else "Undo")

    def set_redo_text(self, text: str) -> None:
        if shiboken6.isValid(self.redo_action):
            self.redo_action.setText(f"Redo {text}" if text else "Redo")

    def update_recent_menu(self) -> None:
        if not shiboken6.isValid(self.recent_menu):
            return
        self.recent_menu.clear()
        recent = self._window.project_controller.recent_projects()
        if not recent:
            empty_action = self.recent_menu.addAction("No Recent Projects")
            empty_action.setEnabled(False)
            return
        for path in recent:
            action = self.recent_menu.addAction(path)
            action.triggered.connect(
                lambda _checked=False, val=path: self._window.project_controller.open_project(val)
            )
        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction("Clear Recent Projects")
        clear_action.triggered.connect(self._window.project_controller.clear_recent_projects)

    def open_settings(self) -> None:
        previous = StudioSettings.load()
        dialog = SettingsDialog(
            previous,
            self._window,
            pages=self._host.settings_pages(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        values.save()
        dialog.apply_plugin_pages()
        dialog.apply_units()
        if values.theme_mode != previous.theme_mode:
            self.switch_theme(values.theme_mode)
        self._window.project_controller.trim_recent_projects(values.recent_project_limit)
        self.update_recent_menu()

    def open_command_palette(self) -> None:
        if self._command_palette_dialog is None:
            self._command_palette_dialog = CommandPaletteDialog(self._window, self._api)
        self._command_palette_dialog.populate_and_show(self)

    def open_about(self) -> None:
        AboutDialog(self._window).exec()

    def open_task_manager(self) -> None:
        self._window.status_manager.open_task_manager_window()

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

    def register_action(self, contribution: ActionContribution) -> None:
        parts = [p.strip().replace("&", "") for p in contribution.menu.split("/") if p.strip()]
        if not parts:
            parts = ["Tools"]

        path_key = parts[0].lower()
        current_menu = self._live_menu(path_key)
        if current_menu is None:
            current_menu = self._window.menuBar().addMenu(f"&{parts[0]}")
            self.menus[path_key] = current_menu
        for name in parts[1:]:
            path_key = f"{path_key}/{name.lower()}"
            menu = self._live_menu(path_key)
            if menu is None:
                menu = QMenu(f"&{name}", current_menu)
                current_menu.addMenu(menu)
                self.menus[path_key] = menu
            current_menu = menu

        icon = get_icon(contribution.icon) if contribution.icon else None
        if icon is not None and not icon.isNull():
            action = current_menu.addAction(icon, contribution.title)
        else:
            action = current_menu.addAction(contribution.title)

        if contribution.shortcut:
            action.setShortcut(QKeySequence(contribution.shortcut))

        action.triggered.connect(contribution.callback)

    def _live_menu(self, path_key: str) -> QMenu | None:
        menu = self.menus.get(path_key)
        return menu if menu is not None and shiboken6.isValid(menu) else None

    def unregister_action(self, menu_path: str, title: str) -> None:

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
