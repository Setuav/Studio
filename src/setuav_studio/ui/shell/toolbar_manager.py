from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.shell.toolbar import StandardToolBar, ToolSetBar, WorkspaceToolBar
from setuav_studio_sdk import (
    ToolbarContribution,
    ToolbarMenuItemContribution,
    WorkspaceContribution,
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

logger = logging.getLogger(__name__)


class ToolbarManager:
    """Manages workspace switcher, configuration bar, standard and dynamic toolbars."""

    def __init__(self, window: QMainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self.workspaces: dict[str, WorkspaceContribution] = {}
        self.toolbar_contributions: dict[str, ToolbarContribution] = {}
        self.toolbar_actions: dict[str, QAction] = {}
        self.toolbar_menu_actions: dict[
            str,
            list[tuple[ToolbarMenuItemContribution, QAction]],
        ] = {}
        self.owned_toolbar_actions: set[str] = set()
        self.toolset_bars: dict[str, ToolSetBar] = {}

        self.standard_toolbar = StandardToolBar(self._window)
        self._window.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.standard_toolbar)

        self.workspace_toolbar = WorkspaceToolBar(self._window)
        self.workspace_toolbar.workspace_activated.connect(self._api.switch_workspace)
        self._window.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.workspace_toolbar)

    def setup_standard_actions(
        self,
        new_project_action: QAction,
        open_folder_action: QAction,
        save_action: QAction,
        save_as_action: QAction,
        undo_action: QAction,
        redo_action: QAction,
    ) -> None:
        self.standard_toolbar.addAction(new_project_action)
        self.standard_toolbar.addAction(open_folder_action)
        self.standard_toolbar.addAction(save_action)
        self.standard_toolbar.addAction(save_as_action)
        self.standard_toolbar.addSeparator()
        self.standard_toolbar.addAction(undo_action)
        self.standard_toolbar.addAction(redo_action)

    def update_main_toolbar_style(self) -> None:
        self.standard_toolbar.setStyleSheet("")
        self.workspace_toolbar.setStyleSheet("")
        for toolbar in self.toolset_bars.values():
            toolbar.setStyleSheet("")

    def update_toolbar_contribution_icons(self) -> None:
        for contribution_id, contribution in self.toolbar_contributions.items():
            action = self.toolbar_actions.get(contribution_id)
            if action is not None and contribution.icon:
                action.setIcon(get_icon(contribution.icon))
            for menu_item, menu_action in self.toolbar_menu_actions.get(contribution_id, []):
                if menu_item.icon:
                    menu_action.setIcon(get_icon(menu_item.icon))

    def add_toolbar_item(self, contribution: ToolbarContribution) -> None:
        if contribution.id in self.toolbar_contributions:
            self.remove_toolbar_item(contribution.id)

        self.toolbar_contributions[contribution.id] = contribution
        if contribution.callback is not None:
            action = QAction(contribution.title, self._window)
            action.triggered.connect(contribution.callback)
            self.toolbar_actions[contribution.id] = action
            self.owned_toolbar_actions.add(contribution.id)
        elif contribution.command is not None:
            command_actions = getattr(self._window, "_command_actions", {})
            action = command_actions.get(contribution.command or "")
            if action is not None:
                self.toolbar_actions[contribution.id] = action
        else:
            action = QAction(contribution.title, self._window)
            self.toolbar_actions[contribution.id] = action
            self.owned_toolbar_actions.add(contribution.id)

        action = self.toolbar_actions.get(contribution.id)
        if action is not None:
            action.setToolTip(contribution.title)
            if contribution.icon:
                action.setIcon(get_icon(contribution.icon))
            if contribution.menu_items:
                menu = QMenu(contribution.title, self._window)
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
                self.toolbar_menu_actions[contribution.id] = menu_actions
        self.rebuild_toolbar_tools()
        self.refresh_toolbar_action_states()

    def remove_toolbar_item(self, contribution_id: str) -> None:
        self.toolbar_contributions.pop(contribution_id, None)
        action = self.toolbar_actions.pop(contribution_id, None)
        self.toolbar_menu_actions.pop(contribution_id, None)
        owned = contribution_id in self.owned_toolbar_actions
        self.owned_toolbar_actions.discard(contribution_id)
        self.rebuild_toolbar_tools()
        if owned and action is not None:
            menu = action.menu()
            if menu is not None:
                menu.deleteLater()
            action.deleteLater()

    def refresh_toolbar_action_states(self) -> None:
        for contribution_id, contribution in self.toolbar_contributions.items():
            action = self.toolbar_actions.get(contribution_id)
            if action is None:
                continue
            enabled = True
            if contribution.enabled_when is not None:
                try:
                    enabled = bool(contribution.enabled_when())
                except Exception:
                    logger.exception("Could not evaluate toolbar state: %s", contribution_id)
                    enabled = False

            menu_has_enabled_item = not contribution.menu_items
            for menu_item, menu_action in self.toolbar_menu_actions.get(contribution_id, []):
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

    def rebuild_toolbar_tools(self) -> None:
        current_id = (
            getattr(self._window, "_current_workspace_id", None) or self._api.current_workspace_id
        )
        grouped_actions, group_order = self.workspace_toolbar_actions(current_id)
        self.remove_unregistered_toolbars()
        self.apply_toolbar_groups(grouped_actions, group_order)

    def workspace_toolbar_actions(
        self, workspace_id: str | None
    ) -> tuple[dict[str, list[QAction]], list[str]]:
        grouped_actions: dict[str, list[QAction]] = {}
        group_order: list[str] = []
        contributions = sorted(
            self.toolbar_contributions.values(),
            key=lambda item: (item.order, item.group, item.title.casefold()),
        )
        command_actions = getattr(self._window, "_command_actions", {})
        for contribution in contributions:
            if not contribution.is_in_workspace(workspace_id):
                continue
            action = self.toolbar_actions.get(contribution.id)
            if action is None and contribution.command:
                action = command_actions.get(contribution.command)
                if action is not None:
                    self.toolbar_actions[contribution.id] = action
                    action.setToolTip(contribution.title)
                    if contribution.icon:
                        action.setIcon(get_icon(contribution.icon))
            if action is not None:
                if contribution.group not in grouped_actions:
                    grouped_actions[contribution.group] = []
                    group_order.append(contribution.group)
                grouped_actions[contribution.group].append(action)
        return grouped_actions, group_order

    def remove_unregistered_toolbars(self) -> None:
        registered_groups = {
            contribution.group for contribution in self.toolbar_contributions.values()
        }
        for group, toolbar in list(self.toolset_bars.items()):
            if group not in registered_groups:
                self._window.removeToolBar(toolbar)
                toolbar.deleteLater()
                del self.toolset_bars[group]

    def apply_toolbar_groups(
        self, grouped_actions: dict[str, list[QAction]], group_order: list[str]
    ) -> None:
        for group in group_order:
            toolbar = self.toolset_bars.get(group)
            if toolbar is None:
                toolbar = ToolSetBar(group, self._window)
                self.toolset_bars[group] = toolbar
                self._window.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
            toolbar.set_tools(grouped_actions[group])
            toolbar.show()

        for group, toolbar in self.toolset_bars.items():
            if group not in grouped_actions:
                toolbar.set_tools([])
                toolbar.hide()

    def add_workspace(self, contribution: WorkspaceContribution) -> None:
        self.workspaces[contribution.id] = contribution
        self.refresh_workspace_combo()

    def remove_workspace(self, workspace_id: str) -> None:
        if workspace_id not in self.workspaces:
            return
        was_current = workspace_id in {
            getattr(self._window, "_current_workspace_id", None),
            self._api.current_workspace_id,
        }
        del self.workspaces[workspace_id]
        if hasattr(self._window, "_workspace_states"):
            self._window._workspace_states.pop(workspace_id, None)
        QSettings().remove(f"workspace_perspective/{workspace_id}")
        panels = getattr(self._window, "_panels", {})
        for panel_id in list(panels):
            contribution, _ = panels[panel_id]
            if contribution.workspace_id == workspace_id and hasattr(self._window, "_remove_panel"):
                self._window._remove_panel(panel_id)

        if was_current:
            self._window._current_workspace_id = None
            self._api.current_workspace_id = None

        self.refresh_workspace_combo()

        if was_current:
            remaining = sorted(
                self.workspaces.values(),
                key=lambda item: (item.order, item.title.casefold()),
            )
            if remaining:
                self._api.switch_workspace(remaining[0].id)
            else:
                self.rebuild_toolbar_tools()
                if hasattr(self._window, "_update_view_menu"):
                    self._window._update_view_menu(None)

    def refresh_workspace_combo(self) -> None:
        workspaces = sorted(
            self.workspaces.values(),
            key=lambda item: (item.order, item.title.casefold()),
        )
        current_id = (
            getattr(self._window, "_current_workspace_id", None) or self._api.current_workspace_id
        )
        self.workspace_toolbar.set_workspaces(workspaces, current_id)


__all__ = ["ToolbarManager"]
