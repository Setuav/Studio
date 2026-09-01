from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PySide6.QtGui import QUndoStack

from setuav_studio.project import ProjectDocument
from setuav_studio_sdk.contributions import (
    ActionContribution,
    PanelContribution,
    SettingsPageContribution,
    ToolbarContribution,
    WorkspaceContribution,
)

if TYPE_CHECKING:
    from .api import StudioAPI


class _StudioHost:
    """Internal bridge used by the application shell to drive ``StudioAPI``.

    Plugins receive only ``StudioAPI``. Shell bindings and host-owned state
    transitions live here so they cannot accidentally become part of the
    supported third-party API.
    """

    def __init__(self, api: StudioAPI) -> None:
        self._api = api

    @property
    def undo_stack(self) -> QUndoStack:
        return self._api._undo_stack

    def bind_panel_handlers(
        self,
        add_handler: Callable[[PanelContribution], None],
        remove_handler: Callable[[str], None] | None = None,
    ) -> None:
        self._api._add_panel = add_handler
        self._api._remove_panel = remove_handler
        for panel in self._api._pending_panels:
            add_handler(panel)
        self._api._pending_panels.clear()

    def bind_status_handler(self, handler: Callable[[str, str, int], None]) -> None:
        self._api._status_handler = handler
        for message, level, timeout_ms in self._api._pending_status:
            handler(message, level, timeout_ms)
        self._api._pending_status.clear()

    def bind_progress_handler(self, handler: Callable[[int, int, str], None]) -> None:
        self._api._progress_handler = handler

    def bind_workspace_handlers(
        self,
        add_handler: Callable[[WorkspaceContribution], None],
        switch_handler: Callable[[str], None] | None = None,
        remove_handler: Callable[[str], None] | None = None,
    ) -> None:
        self._api._add_workspace = add_handler
        self._api._switch_workspace_handler = switch_handler
        self._api._remove_workspace = remove_handler
        for workspace in self._api._pending_workspaces:
            add_handler(workspace)
        self._api._pending_workspaces.clear()

    def bind_toolbar_handlers(
        self,
        add_handler: Callable[[ToolbarContribution], None],
        remove_handler: Callable[[str], None] | None = None,
    ) -> None:
        self._api._add_toolbar_item = add_handler
        self._api._remove_toolbar_item = remove_handler
        for contribution in self._api._pending_toolbar_items:
            add_handler(contribution)
        self._api._pending_toolbar_items.clear()

    def bind_action_handlers(
        self,
        add_handler: Callable[[ActionContribution], None],
        remove_handler: Callable[[str, str], None] | None = None,
    ) -> None:
        self._api._add_action = add_handler
        self._api._remove_action = remove_handler
        for action in self._api._pending_actions:
            add_handler(action)
        self._api._pending_actions.clear()

    def set_project(self, project: ProjectDocument) -> None:
        api = self._api
        api.current_project = project
        api._undo_stack.clear()
        api._undo_stack.setClean()
        project.modified = False
        api.set_selection(None)
        api.set_section_selection(None)
        dead_listeners = []
        for listener in list(api._project_listeners):
            try:
                listener(project)
            except RuntimeError:
                dead_listeners.append(listener)
        for dead in dead_listeners:
            if dead in api._project_listeners:
                api._project_listeners.remove(dead)

    def mark_project_saved(self) -> None:
        self._api._undo_stack.setClean()
        self._api._on_clean_changed(True)

    def bind_project_requirement_checker(
        self,
        checker: Callable[[dict[str, Any]], list[str]],
    ) -> None:
        self._api._project_requirement_checker = checker

    def check_project_requirements(self, data: dict[str, Any]) -> list[str]:
        checker = self._api._project_requirement_checker
        return [] if checker is None else checker(data)

    def settings_pages(self) -> tuple[SettingsPageContribution, ...]:
        return tuple(
            sorted(
                self._api._settings_pages.values(),
                key=lambda page: (page.order, page.title.casefold(), page.id),
            )
        )


__all__ = ["_StudioHost"]
