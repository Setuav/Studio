import logging
import pkgutil
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module, metadata
from pathlib import Path
from typing import Any, Protocol

from packaging.version import InvalidVersion, Version
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QUndoCommand, QUndoStack
from PySide6.QtWidgets import QWidget

from setuav_studio.component_editor import BaseComponentEditor, ParameterField
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.icons import get_icon

__all__ = [
    "BaseComponentEditor",
    "ComponentTreeNodeContribution",
    "ProjectTreeNodeContribution",
    "ParameterField",
    "PanelContribution",
    "SettingsPageContribution",
    "MassPropertiesProvider",
    "StudioAPI",
    "ToolbarContribution",
    "ToolbarMenuItemContribution",
    "ToolContribution",
    "WorkspaceContribution",
    "PluginManager",
]

logger = logging.getLogger(__name__)

GeometryProvider = Callable[[dict[str, Any]], Any]
ComponentTreeProvider = Callable[
    [dict[str, Any]],
    tuple["ComponentTreeNodeContribution", ...],
]
ProjectTreeProvider = Callable[
    [ProjectDocument],
    tuple["ProjectTreeNodeContribution", ...],
]


class MassPropertiesProvider(Protocol):
    """Project-level mass-properties service contributed by a plugin."""

    def evaluate(
        self,
        project: ProjectDocument,
    ) -> Any: ...


@dataclass(frozen=True)
class ComponentTreeNodeContribution:
    """A virtual child displayed beneath a project component."""

    id: str
    title: str
    selection: dict[str, Any]
    icon: str | Path | QIcon | None = None
    tooltip: str | None = None
    rename: Callable[[str], None] | None = None
    delete: Callable[[], None] | None = None


@dataclass(frozen=True)
class ProjectTreeNodeContribution:
    """A plugin-owned node displayed directly beneath the project root."""

    id: str
    title: str
    selection: dict[str, Any]
    children: tuple["ProjectTreeNodeContribution", ...] = ()
    icon: str | Path | QIcon | None = None
    tooltip: str | None = None
    rename: Callable[[str], None] | None = None
    delete: Callable[[], None] | None = None


@dataclass(frozen=True)
class PanelContribution:
    id: str
    title: str
    factory: Callable[[], QWidget]
    area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea
    workspace_id: str | list[str] | tuple[str, ...] | None = None
    icon: str | Path | QIcon | None = None

    def is_in_workspace(self, current_workspace_id: str | None) -> bool:
        if self.workspace_id is None:
            return True
        if isinstance(self.workspace_id, (list, tuple, set)):
            return current_workspace_id in self.workspace_id
        return self.workspace_id == current_workspace_id


@dataclass(frozen=True)
class SettingsPageContribution:
    """A settings category contributed by a plugin.

    ``factory`` creates the page widget when the Settings dialog opens.  The
    optional ``apply`` callback is called with that widget after the user
    presses OK, allowing the plugin to persist its values (usually through
    ``QSettings``) without coupling the core dialog to plugin state.
    Pages with the same ``group`` are shown beneath one expandable heading.
    """

    id: str
    title: str
    factory: Callable[[], QWidget]
    icon: str | Path | QIcon | None = None
    order: int = 0
    apply: Callable[[QWidget], None] | None = None
    group: str | None = None
    group_icon: str | Path | QIcon | None = None


@dataclass(frozen=True)
class WorkspaceContribution:
    id: str
    title: str
    factory: Callable[[], QWidget] | None = None
    icon: str | Path | QIcon | None = None
    order: int = 0


@dataclass(frozen=True)
class ToolbarMenuItemContribution:
    """One command inside a contributed toolbar action's popup menu."""

    title: str
    callback: Callable[[], None]
    icon: str | Path | QIcon | None = None
    enabled_when: Callable[[], bool] | None = None


@dataclass(frozen=True)
class ToolbarContribution:
    """A plugin-provided action displayed in the main application toolbar."""

    id: str
    title: str
    icon: str | Path | QIcon | None = None
    callback: Callable[[], None] | None = None
    command: str | None = None
    menu_items: tuple[ToolbarMenuItemContribution, ...] = ()
    enabled_when: Callable[[], bool] | None = None
    group: str = "default"
    order: int = 0
    workspace_id: str | list[str] | tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.callback is not None and self.command is not None:
            raise ValueError(
                "Toolbar contributions cannot define both callback and command"
            )
        if self.callback is None and self.command is None and not self.menu_items:
            raise ValueError("Toolbar contributions require an action or menu")

    def is_in_workspace(self, current_workspace_id: str | None) -> bool:
        if self.workspace_id is None:
            return True
        if isinstance(self.workspace_id, (list, tuple, set)):
            return current_workspace_id in self.workspace_id
        return self.workspace_id == current_workspace_id


@dataclass(frozen=True)
class ToolContribution:
    title: str
    callback: Callable[[], None]
    group: str | None = None
    icon: str | Path | QIcon | None = None
    shortcut: str | None = None


@dataclass(frozen=True)
class ActionContribution:
    menu: str
    title: str
    callback: Callable[[], None]
    icon: str | Path | QIcon | None = None
    shortcut: str | None = None


@dataclass(frozen=True)
class PluginLoadIssue:
    source: str
    message: str


class _ComponentEditCommand(QUndoCommand):
    def __init__(
        self,
        component: dict[str, Any],
        before: dict[str, Any],
        after: dict[str, Any],
        description: str,
        changed: Callable[[], None],
    ) -> None:
        super().__init__(description)
        self._component = component
        self._before = before
        self._after = after
        self._changed = changed

    def undo(self) -> None:
        self._apply(self._before)

    def redo(self) -> None:
        self._apply(self._after)

    def _apply(self, value: dict[str, Any]) -> None:
        self._component.clear()
        self._component.update(deepcopy(value))
        self._changed()


class _ProjectEditCommand(QUndoCommand):
    def __init__(
        self,
        project: ProjectDocument,
        before: dict[str, Any],
        after: dict[str, Any],
        description: str,
        changed: Callable[[], None],
    ) -> None:
        super().__init__(description)
        self._project = project
        self._before = before
        self._after = after
        self._changed = changed

    def undo(self) -> None:
        self._apply(self._before)

    def redo(self) -> None:
        self._apply(self._after)

    def _apply(self, value: dict[str, Any]) -> None:
        self._project.data.clear()
        self._project.data.update(deepcopy(value))
        self._changed()


class StudioAPI:
    def __init__(self) -> None:
        self.current_project: ProjectDocument | None = None
        self.current_selection: Any | None = None
        self.current_section_selection: tuple[str, int, int] | None = None
        self.current_workspace_id: str | None = None
        self._add_panel: Callable[[PanelContribution], None] | None = None
        self._remove_panel: Callable[[str], None] | None = None
        self._add_workspace: Callable[[WorkspaceContribution], None] | None = None
        self._remove_workspace: Callable[[str], None] | None = None
        self._switch_workspace_handler: Callable[[str], None] | None = None
        self._pending_workspaces: list[WorkspaceContribution] = []
        self._add_toolbar_item: Callable[[ToolbarContribution], None] | None = None
        self._remove_toolbar_item: Callable[[str], None] | None = None
        self._pending_toolbar_items: list[ToolbarContribution] = []
        self._add_action: Callable[[ActionContribution], None] | None = None
        self._remove_action: Callable[[str, str], None] | None = None
        self._pending_actions: list[ActionContribution] = []
        self._settings_pages: dict[str, SettingsPageContribution] = {}
        self._status_handler: (
            Callable[[str, str, int], None] | None
        ) = None
        self._pending_status: list[tuple[str, str, int]] = []
        self._progress_handler: Callable[[int, int, str], None] | None = None
        self._project_listeners: list[Callable[[ProjectDocument], None]] = []
        self._project_content_listeners: list[Callable[[ProjectDocument], None]] = []
        self._modified_listeners: list[Callable[[bool], None]] = []
        self._workspace_listeners: list[Callable[[str], None]] = []
        self._selection_listeners: list[Callable[[Any | None], None]] = []
        self._section_selection_listeners: list[
            Callable[[tuple[str, int, int] | None], None]
        ] = []
        self._component_editors: dict[
            str,
            Callable[[dict[str, Any]], QWidget],
        ] = {}
        self._kind_editors: dict[
            str,
            Callable[[dict[str, Any]], QWidget],
        ] = {}
        self._component_icons: dict[str, str | Path | QIcon] = {}
        self._kind_icons: dict[str, str | Path | QIcon] = {}
        self._geometry_providers: dict[str, GeometryProvider] = {}
        self._component_tree_providers: dict[str, ComponentTreeProvider] = {}
        self._project_tree_providers: dict[str, ProjectTreeProvider] = {}
        self._mass_properties_providers: dict[str, MassPropertiesProvider] = {}
        self._project_requirement_checker: (
            Callable[[dict[str, Any]], list[str]] | None
        ) = None
        self._event_subscribers: dict[str, list[Callable[[Any], None]]] = {}
        self.undo_stack = QUndoStack()
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)

    @property
    def project(self) -> ProjectDocument | None:
        return self.current_project

    @project.setter
    def project(self, value: ProjectDocument | None) -> None:
        self.current_project = value

    def set_panel_handler(
        self,
        handler: Callable[[PanelContribution], None],
        remove_handler: Callable[[str], None] | None = None,
    ) -> None:
        self._add_panel = handler
        self._remove_panel = remove_handler

    def add_panel(self, contribution: PanelContribution) -> None:
        if self._add_panel is None:
            raise RuntimeError("The Studio shell is not ready for panel contributions")
        self._add_panel(contribution)

    def remove_panel(self, panel_id: str) -> None:
        if self._remove_panel is not None:
            self._remove_panel(panel_id)

    def set_status_handler(
        self,
        handler: Callable[[str, str, int], None],
    ) -> None:
        self._status_handler = handler
        for message, level, timeout_ms in self._pending_status:
            handler(message, level, timeout_ms)
        self._pending_status.clear()

    def show_status(
        self,
        message: str,
        level: str = "info",
        timeout_ms: int = 5000,
    ) -> None:
        """Show a message in the shell status bar.

        Levels: "info", "success", "warning", "error". A timeout_ms of 0
        keeps the message until replaced or cleared.
        """
        if self._status_handler is not None:
            self._status_handler(message, level, timeout_ms)
        else:
            self._pending_status.append((message, level, timeout_ms))

    def clear_status(self) -> None:
        if self._status_handler is not None:
            self._status_handler("", "info", 0)

    def set_progress_handler(
        self,
        handler: Callable[[int, int, str], None],
    ) -> None:
        self._progress_handler = handler

    def report_progress(self, completed: int, total: int, label: str = "") -> None:
        """Report task progress to the shell status bar.

        A total of 0 (or completed >= total) hides the progress bar.
        """
        if self._progress_handler is not None:
            self._progress_handler(completed, total, label)

    def clear_progress(self) -> None:
        self.report_progress(1, 1, "")

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Subscribe a callback handler to a named studio event (Event Bus)."""
        self._event_subscribers.setdefault(event_name, []).append(handler)

    def unsubscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Unsubscribe a callback handler from a named studio event."""
        if event_name in self._event_subscribers:
            try:
                self._event_subscribers[event_name].remove(handler)
            except ValueError:
                pass

    def publish(self, event_name: str, payload: Any = None) -> None:
        """Publish an event to all subscribed listeners."""
        handlers = list(self._event_subscribers.get(event_name, []))
        for handler in handlers:
            try:
                handler(payload)
            except Exception as exc:
                logger.error("Error executing subscriber for event '%s': %s", event_name, exc, exc_info=True)

    def set_workspace_handler(
        self,
        handler: Callable[[WorkspaceContribution], None],
        switch_handler: Callable[[str], None] | None = None,
        remove_handler: Callable[[str], None] | None = None,
    ) -> None:
        self._add_workspace = handler
        self._switch_workspace_handler = switch_handler
        self._remove_workspace = remove_handler
        for workspace in self._pending_workspaces:
            handler(workspace)
        self._pending_workspaces.clear()

    def add_workspace(self, contribution: WorkspaceContribution) -> None:
        if self._add_workspace is not None:
            self._add_workspace(contribution)
        else:
            self._pending_workspaces.append(contribution)

    def remove_workspace(self, workspace_id: str) -> None:
        if self._remove_workspace is not None:
            self._remove_workspace(workspace_id)

    def set_workspace(self, contribution: WorkspaceContribution) -> None:
        self.add_workspace(contribution)

    def switch_workspace(self, workspace_id: str) -> None:
        self.current_workspace_id = workspace_id
        if self._switch_workspace_handler is not None:
            self._switch_workspace_handler(workspace_id)
        for listener in list(self._workspace_listeners):
            listener(workspace_id)

    def on_workspace_changed(self, listener: Callable[[str], None]) -> None:
        self._workspace_listeners.append(listener)
        if self.current_workspace_id is not None:
            listener(self.current_workspace_id)

    def set_toolbar_handler(
        self,
        handler: Callable[[ToolbarContribution], None],
        remove_handler: Callable[[str], None] | None = None,
    ) -> None:
        self._add_toolbar_item = handler
        self._remove_toolbar_item = remove_handler
        for contribution in self._pending_toolbar_items:
            handler(contribution)
        self._pending_toolbar_items.clear()

    def add_toolbar_item(self, contribution: ToolbarContribution) -> None:
        if self._add_toolbar_item is not None:
            self._add_toolbar_item(contribution)
        else:
            self._pending_toolbar_items.append(contribution)

    def remove_toolbar_item(self, contribution_id: str) -> None:
        self._pending_toolbar_items = [
            item for item in self._pending_toolbar_items if item.id != contribution_id
        ]
        if self._remove_toolbar_item is not None:
            self._remove_toolbar_item(contribution_id)

    def set_action_handler(
        self,
        handler: Callable[[ActionContribution], None],
        remove_handler: Callable[[str, str], None] | None = None,
    ) -> None:
        self._add_action = handler
        self._remove_action = remove_handler
        for action in self._pending_actions:
            handler(action)
        self._pending_actions.clear()

    def add_action(self, contribution: ActionContribution) -> None:
        if self._add_action is not None:
            self._add_action(contribution)
        else:
            self._pending_actions.append(contribution)

    def remove_action(self, menu: str, title: str) -> None:
        if self._remove_action is not None:
            self._remove_action(menu, title)

    def add_settings_page(self, contribution: SettingsPageContribution) -> None:
        """Add a category to the application Settings dialog.

        Plugins may register pages during ``activate`` and remove them during
        ``deactivate``.  Pages are created lazily when the dialog is opened.
        """
        if contribution.id in self._settings_pages:
            raise ValueError(
                f"A settings page is already registered for: {contribution.id}"
            )
        self._settings_pages[contribution.id] = contribution

    def remove_settings_page(self, page_id: str) -> None:
        self._settings_pages.pop(page_id, None)

    def settings_pages(self) -> tuple[SettingsPageContribution, ...]:
        """Return registered plugin settings pages in display order."""
        return tuple(
            sorted(
                self._settings_pages.values(),
                key=lambda page: (page.order, page.title.casefold(), page.id),
            )
        )

    def register_tool(self, contribution: ToolContribution) -> None:
        menu_path = f"Tools/{contribution.group}" if contribution.group else "Tools"
        self.add_action(
            ActionContribution(
                menu=menu_path,
                title=contribution.title,
                callback=contribution.callback,
                icon=contribution.icon,
                shortcut=contribution.shortcut,
            )
        )

    def on_project_changed(self, listener: Callable[[ProjectDocument], None]) -> None:
        self._project_listeners.append(listener)
        if self.current_project is not None:
            listener(self.current_project)

    def set_project(self, project: ProjectDocument) -> None:
        self.current_project = project
        self.undo_stack.clear()
        self.undo_stack.setClean()
        project.modified = False
        self.set_selection(None)
        self.set_section_selection(None)
        dead_listeners = []
        for listener in list(self._project_listeners):
            try:
                listener(project)
            except RuntimeError:
                dead_listeners.append(listener)
        for dead in dead_listeners:
            if dead in self._project_listeners:
                self._project_listeners.remove(dead)

    def on_project_content_changed(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        self._project_content_listeners.append(listener)

    def remove_project_content_listener(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        if listener in self._project_content_listeners:
            self._project_content_listeners.remove(listener)

    def on_modified_changed(self, listener: Callable[[bool], None]) -> None:
        self._modified_listeners.append(listener)
        try:
            listener(bool(self.current_project and self.current_project.modified))
        except RuntimeError:
            pass

    def remove_modified_listener(self, listener: Callable[[bool], None]) -> None:
        if listener in self._modified_listeners:
            self._modified_listeners.remove(listener)

    def edit_component(
        self,
        component: dict[str, Any],
        description: str,
        change: Callable[[], None],
    ) -> None:
        before = deepcopy(component)
        change()
        after = deepcopy(component)
        component.clear()
        component.update(before)
        if before == after:
            return
        self.undo_stack.push(
            _ComponentEditCommand(
                component,
                before,
                after,
                description,
                self._notify_project_content_changed,
            )
        )

    def edit_project(
        self,
        description: str,
        change: Callable[[], None],
    ) -> None:
        if self.current_project is None:
            change()
            return
        before = deepcopy(self.current_project.data)
        change()
        after = deepcopy(self.current_project.data)
        self.current_project.data.clear()
        self.current_project.data.update(before)
        if before == after:
            return
        self.undo_stack.push(
            _ProjectEditCommand(
                self.current_project,
                before,
                after,
                description,
                self._notify_project_content_changed,
            )
        )

    def edit_project_extension(
        self,
        namespace: str,
        description: str,
        change: Callable[[dict[str, Any]], None],
    ) -> None:
        """Edit root-level extension data for a given namespace with full Undo/Redo tracking."""
        if self.current_project is None:
            return

        def wrapper() -> None:
            assert self.current_project is not None
            if "extensions" not in self.current_project.data or not isinstance(
                self.current_project.data["extensions"], dict
            ):
                self.current_project.data["extensions"] = {}
            ext = self.current_project.data["extensions"].setdefault(namespace, {})
            change(ext)

        self.edit_project(description, wrapper)

    def edit_component_extension(
        self,
        component_id: str,
        namespace: str,
        description: str,
        change: Callable[[dict[str, Any]], None],
    ) -> None:
        """Edit component-level extension data for a given namespace with full Undo/Redo tracking."""
        if self.current_project is None:
            return
        comp = self.current_project.get_component(component_id)
        if comp is None:
            return

        def wrapper() -> None:
            if "extensions" not in comp or not isinstance(comp["extensions"], dict):
                comp["extensions"] = {}
            ext = comp["extensions"].setdefault(namespace, {})
            change(ext)

        self.edit_component(comp, description, wrapper)

    def undo(self) -> None:
        if self.undo_stack.canUndo():
            self.undo_stack.undo()
            self.set_selection(self.current_selection)

    def redo(self) -> None:
        if self.undo_stack.canRedo():
            self.undo_stack.redo()
            self.set_selection(self.current_selection)

    def mark_project_saved(self) -> None:
        self.undo_stack.setClean()

    def set_project_requirement_checker(
        self,
        checker: Callable[[dict[str, Any]], list[str]],
    ) -> None:
        self._project_requirement_checker = checker

    def check_project_requirements(self, data: dict[str, Any]) -> list[str]:
        if self._project_requirement_checker is None:
            return []
        return self._project_requirement_checker(data)

    def notify_project_content_changed(self) -> None:
        """Explicitly notify listeners that project content was updated or needs refresh."""
        self._notify_project_content_changed()

    def _notify_project_content_changed(self) -> None:
        if self.current_project is None:
            return
        dead_listeners = []
        for listener in list(self._project_content_listeners):
            try:
                listener(self.current_project)
            except RuntimeError:
                dead_listeners.append(listener)
        for dead in dead_listeners:
            if dead in self._project_content_listeners:
                self._project_content_listeners.remove(dead)

    def _on_clean_changed(self, clean: bool) -> None:
        modified = not clean
        if self.current_project is not None:
            self.current_project.modified = modified
        dead_listeners = []
        for listener in list(self._modified_listeners):
            try:
                listener(modified)
            except RuntimeError:
                dead_listeners.append(listener)
        for dead in dead_listeners:
            if dead in self._modified_listeners:
                self._modified_listeners.remove(dead)

    def on_selection_changed(self, listener: Callable[[Any | None], None]) -> None:
        self._selection_listeners.append(listener)
        try:
            listener(self.current_selection)
        except RuntimeError:
            pass

    def set_selection(self, selection: Any | None) -> None:
        self.current_selection = selection
        dead_listeners = []
        for listener in list(self._selection_listeners):
            try:
                listener(selection)
            except RuntimeError:
                dead_listeners.append(listener)
        for dead in dead_listeners:
            if dead in self._selection_listeners:
                self._selection_listeners.remove(dead)

    def on_section_selection_changed(
        self,
        listener: Callable[[tuple[str, int, int] | None], None],
    ) -> None:
        self._section_selection_listeners.append(listener)
        try:
            listener(self.current_section_selection)
        except RuntimeError:
            pass

    def remove_section_selection_listener(
        self,
        listener: Callable[[tuple[str, int, int] | None], None],
    ) -> None:
        if listener in self._section_selection_listeners:
            self._section_selection_listeners.remove(listener)

    def set_section_selection(
        self,
        selection: tuple[str, int, int] | None,
    ) -> None:
        self.current_section_selection = selection
        dead_listeners = []
        for listener in list(self._section_selection_listeners):
            try:
                listener(selection)
            except RuntimeError:
                dead_listeners.append(listener)
        for dead in dead_listeners:
            if dead in self._section_selection_listeners:
                self._section_selection_listeners.remove(dead)

    def register_component_editor(
        self,
        component_type: str,
        factory: Callable[[dict[str, Any]], QWidget],
    ) -> None:
        if component_type in self._component_editors:
            raise ValueError(
                f"A component editor is already registered for: {component_type}"
            )
        self._component_editors[component_type] = factory

    def remove_component_editor(self, component_type: str) -> None:
        self._component_editors.pop(component_type, None)

    def register_kind_editor(
        self,
        component_kind: str,
        factory: Callable[[dict[str, Any]], QWidget],
    ) -> None:
        if component_kind in self._kind_editors:
            raise ValueError(
                f"An editor is already registered for component kind: {component_kind}"
            )
        self._kind_editors[component_kind] = factory

    def remove_kind_editor(self, component_kind: str) -> None:
        self._kind_editors.pop(component_kind, None)

    def create_component_editor(
        self,
        component: dict[str, Any],
    ) -> QWidget | None:
        component_type = component.get("type")
        factory = (
            self._component_editors.get(component_type)
            if isinstance(component_type, str)
            else None
        )
        if factory is None:
            component_kind = component.get("kind")
            if isinstance(component_kind, str):
                factory = self._kind_editors.get(component_kind)
        if factory is None:
            return None
        return factory(component)

    def register_component_icon(
        self,
        component_type: str,
        icon: str | Path | QIcon,
    ) -> None:
        if component_type in self._component_icons:
            raise ValueError(
                f"An icon is already registered for component type: {component_type}"
            )
        self._component_icons[component_type] = icon

    def remove_component_icon(self, component_type: str) -> None:
        self._component_icons.pop(component_type, None)

    def register_kind_icon(
        self,
        component_kind: str,
        icon: str | Path | QIcon,
    ) -> None:
        if component_kind in self._kind_icons:
            raise ValueError(
                f"An icon is already registered for component kind: {component_kind}"
            )
        self._kind_icons[component_kind] = icon

    def remove_kind_icon(self, component_kind: str) -> None:
        self._kind_icons.pop(component_kind, None)

    def get_component_icon(self, component: dict[str, Any]) -> QIcon:
        component_type = component.get("type")
        if isinstance(component_type, str) and component_type in self._component_icons:
            return get_icon(self._component_icons[component_type])

        component_kind = component.get("kind")
        if isinstance(component_kind, str) and component_kind in self._kind_icons:
            return get_icon(self._kind_icons[component_kind])

        if component_kind == "instance":
            return get_icon("instance")

        return get_icon("component")

    def register_geometry_provider(
        self,
        component_type: str,
        provider: GeometryProvider,
    ) -> None:
        if component_type in self._geometry_providers:
            raise ValueError(f"A geometry provider is already registered for: {component_type}")
        self._geometry_providers[component_type] = provider

    def remove_geometry_provider(self, component_type: str) -> None:
        self._geometry_providers.pop(component_type, None)

    def register_component_tree_provider(
        self,
        provider_id: str,
        provider: ComponentTreeProvider,
    ) -> None:
        if provider_id in self._component_tree_providers:
            raise ValueError(
                f"A component tree provider is already registered for: {provider_id}"
            )
        self._component_tree_providers[provider_id] = provider

    def remove_component_tree_provider(self, provider_id: str) -> None:
        self._component_tree_providers.pop(provider_id, None)

    def component_tree_nodes(
        self,
        component: dict[str, Any],
    ) -> tuple[ComponentTreeNodeContribution, ...]:
        nodes: list[ComponentTreeNodeContribution] = []
        for provider in self._component_tree_providers.values():
            nodes.extend(provider(component))
        return tuple(nodes)

    def register_project_tree_provider(
        self,
        provider_id: str,
        provider: ProjectTreeProvider,
    ) -> None:
        if provider_id in self._project_tree_providers:
            raise ValueError(
                f"A project tree provider is already registered for: {provider_id}"
            )
        self._project_tree_providers[provider_id] = provider
        if self.current_project is not None:
            self.notify_project_content_changed()

    def remove_project_tree_provider(self, provider_id: str) -> None:
        removed = self._project_tree_providers.pop(provider_id, None)
        if removed is not None and self.current_project is not None:
            self.notify_project_content_changed()

    def project_tree_nodes(
        self,
        project: ProjectDocument,
    ) -> tuple[ProjectTreeNodeContribution, ...]:
        nodes: list[ProjectTreeNodeContribution] = []
        for provider in self._project_tree_providers.values():
            nodes.extend(provider(project))
        return tuple(nodes)

    def register_mass_properties_provider(
        self,
        provider_id: str,
        provider: MassPropertiesProvider,
    ) -> None:
        """Register a synchronous mass/CG/inertia provider."""
        if provider_id in self._mass_properties_providers:
            raise ValueError(
                f"A mass properties provider is already registered for: {provider_id}"
            )
        self._mass_properties_providers[provider_id] = provider

    def remove_mass_properties_provider(self, provider_id: str) -> None:
        self._mass_properties_providers.pop(provider_id, None)

    def get_mass_properties_provider(
        self,
        provider_id: str | None = None,
    ) -> MassPropertiesProvider | None:
        """Resolve a provider by id, or the sole registered provider."""
        if provider_id is not None:
            return self._mass_properties_providers.get(provider_id)
        if len(self._mass_properties_providers) == 1:
            return next(iter(self._mass_properties_providers.values()))
        return None

    def register_schema(self, schema_id: str, schema_dict: dict[str, Any]) -> None:
        """Register a custom JSON schema dynamically (for 3rd-party plugins)."""
        from setuav_studio.schema_validation import get_catalog

        get_catalog().register_schema(schema_dict, schema_id)

    def register_component_type_schema(
        self,
        component_type: str,
        schema_dict: dict[str, Any],
        plugin_id: str | None = None,
    ) -> None:
        """Register a custom component type schema dynamically under a plugin."""
        from setuav_studio.schema_validation import get_catalog

        get_catalog().register_component_type_schema(component_type, schema_dict, plugin_id=plugin_id)

    def build_geometry_data(
        self,
        project: ProjectDocument | None = None,
    ) -> Any:
        document = project or self.current_project
        if document is None:
            from setuav_studio.plugins.geometry.engine.data import GeometryData
            return GeometryData()
        from setuav_studio.plugins.geometry.viewport.scene import build_project_geometry
        return build_project_geometry(document, self._geometry_providers)

    def remove_project_listener(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        if listener in self._project_listeners:
            self._project_listeners.remove(listener)

    def remove_selection_listener(
        self,
        listener: Callable[[Any | None], None],
    ) -> None:
        if listener in self._selection_listeners:
            self._selection_listeners.remove(listener)


class StudioPlugin(Protocol):
    id: str
    priority: int

    def activate(self, api: StudioAPI) -> None: ...

    def deactivate(self, api: StudioAPI) -> None: ...


class PluginManager:
    def __init__(self, api: StudioAPI) -> None:
        self._api = api
        self._plugins: dict[str, StudioPlugin] = {}
        self._providers: dict[str, str] = {}
        self._plugin_providers: dict[str, dict[str, str]] = {}
        api.set_project_requirement_checker(self.check_project_requirements)

    def activate(self, plugin: StudioPlugin) -> None:
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin is already active: {plugin.id}")
        logger.info("Activating plugin: %s", plugin.id)
        plugin.activate(self._api)
        self._plugins[plugin.id] = plugin
        provides = getattr(plugin, "provides", {})
        if isinstance(provides, dict):
            provided = {str(plugin_id): str(version) for plugin_id, version in provides.items()}
            self._providers.update(provided)
            self._plugin_providers[plugin.id] = provided

    def deactivate(self, plugin_id: str) -> None:
        plugin = self._plugins.pop(plugin_id, None)
        if plugin is None:
            raise ValueError(f"Plugin is not active: {plugin_id}")
        logger.info("Deactivating plugin: %s", plugin_id)
        deactivate = getattr(plugin, "deactivate", None)
        if callable(deactivate):
            deactivate(self._api)
        for provided_id in self._plugin_providers.pop(plugin_id, {}):
            self._providers.pop(provided_id, None)

    def discover(self) -> list[PluginLoadIssue]:
        logger.info("Discovering plugins")
        issues = self._discover_bundled()
        issues.extend(self._discover_entry_points())
        return issues

    def check_project_requirements(self, data: dict[str, Any]) -> list[str]:
        requirements = data.get("plugins", [])
        if not isinstance(requirements, list):
            return []

        issues: list[str] = []
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            plugin_id = requirement.get("id")
            requested = requirement.get("version")
            if not isinstance(plugin_id, str):
                continue
            installed = self._providers.get(plugin_id)
            if installed is None:
                issues.append(f"Missing plugin: {plugin_id}")
            elif isinstance(requested, str) and not _version_satisfies(installed, requested):
                issues.append(
                    f"Incompatible plugin: {plugin_id} {installed} (requires {requested})"
                )
        return issues

    def _discover_bundled(self) -> list[PluginLoadIssue]:
        package = import_module("setuav_studio.plugins")
        issues: list[PluginLoadIssue] = []
        candidates: list[tuple[int, str, object]] = []
        for module_info in pkgutil.iter_modules(package.__path__):
            source = f"setuav_studio.plugins.{module_info.name}"
            try:
                module = import_module(source)
                candidate = getattr(module, "PLUGIN", None)
                if candidate is not None:
                    candidates.append(_candidate_sort_key(candidate, source))
            except Exception as exc:
                logger.warning("Failed to load bundled plugin %s: %s", source, exc)
                issues.append(PluginLoadIssue(source, str(exc)))
        candidates.sort(key=lambda item: (item[0], item[1]))
        for _, _, candidate in candidates:
            try:
                self._activate_candidate(candidate)
            except Exception as exc:
                logger.warning("Failed to activate plugin: %s", exc)
                issues.append(PluginLoadIssue("plugin", str(exc)))
        return issues

    def _discover_entry_points(self) -> list[PluginLoadIssue]:
        issues: list[PluginLoadIssue] = []
        candidates: list[tuple[int, str, object]] = []
        for entry_point in metadata.entry_points(group="setuav_studio.plugins"):
            try:
                logger.info("Loading entry-point plugin: %s", entry_point.name)
                candidates.append(_candidate_sort_key(entry_point.load(), entry_point.name))
            except Exception as exc:
                logger.warning("Failed to load entry-point plugin %s: %s", entry_point.name, exc)
                issues.append(PluginLoadIssue(entry_point.name, str(exc)))
        candidates.sort(key=lambda item: (item[0], item[1]))
        for _, _, candidate in candidates:
            try:
                self._activate_candidate(candidate)
            except Exception as exc:
                logger.warning("Failed to activate plugin: %s", exc)
                issues.append(PluginLoadIssue("plugin", str(exc)))
        return issues

    def _activate_candidate(self, candidate: object) -> None:
        plugin = candidate() if isinstance(candidate, type) else candidate
        plugin_id = getattr(plugin, "id", None)
        if isinstance(plugin_id, str) and plugin_id in self._plugins:
            return
        if not hasattr(plugin, "activate") or not isinstance(plugin_id, str):
            raise TypeError("Plugin entry must provide id and activate(api)")
        self.activate(plugin)


def _candidate_sort_key(candidate: object, source: str) -> tuple[int, str, object]:
    priority = getattr(candidate, "priority", 100)
    if not isinstance(priority, int):
        priority = 100
    plugin_id = getattr(candidate, "id", source)
    return priority, str(plugin_id), candidate


def _version_satisfies(installed: str, requirement: str) -> bool:
    installed_version = _parse_version(installed)
    if installed_version is None:
        return False
    if requirement in {"", "*"}:
        return True
    if requirement.startswith("^"):
        minimum = _parse_version(requirement[1:])
        if minimum is None or installed_version < minimum:
            return False
        major, minor, patch = (list(minimum.release) + [0, 0, 0])[:3]
        if major > 0:
            maximum = f"{major + 1}.0.0"
        elif minor > 0:
            maximum = f"0.{minor + 1}.0"
        else:
            maximum = f"0.0.{patch + 1}"
        return installed_version < _parse_version(maximum)
    expected = _parse_version(requirement)
    return expected == installed_version


def _parse_version(value: str) -> Version | None:
    try:
        return Version(value)
    except InvalidVersion:
        return None
