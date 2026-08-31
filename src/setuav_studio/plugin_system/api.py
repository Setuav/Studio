from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon, QUndoStack
from PySide6.QtWidgets import QWidget

from setuav_studio.project import ProjectDocument
from setuav_studio.ui.icons import get_icon
from setuav_studio_sdk.api import (
    ComponentTreeProvider,
    GeometryProvider,
    ProjectTreeProvider,
)
from setuav_studio_sdk.contributions import (
    ActionContribution,
    ComponentTreeNodeContribution,
    PanelContribution,
    ProjectTreeNodeContribution,
    SettingsPageContribution,
    ToolbarContribution,
    ToolContribution,
    WorkspaceContribution,
)

from .host import _StudioHost
from .undo import _ComponentEditCommand, _ProjectEditCommand

logger = logging.getLogger(__name__)


class StudioAPI:
    """Public service surface passed to a plugin during activation.

    Plugins use this object to contribute UI elements, observe application
    state, edit project data with undo/redo support, publish events, and
    register schemas or domain providers. UI contributions and callbacks run on
    the Qt UI thread; long-running work must be delegated to a worker thread.

    Registration identifiers must be globally unique and should use the
    plugin's reverse-domain namespace. QObject-bound event subscribers are
    removed automatically when their owner is destroyed; other listeners and
    contributions should still be removed during plugin deactivation.
    """

    def __init__(self) -> None:
        self.current_project: ProjectDocument | None = None
        self.current_selection: Any | None = None
        self.current_section_selection: tuple[str, int, int] | None = None
        self.current_workspace_id: str | None = None
        self._add_panel: Callable[[PanelContribution], None] | None = None
        self._remove_panel: Callable[[str], None] | None = None
        self._pending_panels: list[PanelContribution] = []
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
        self._status_handler: Callable[[str, str, int], None] | None = None
        self._pending_status: list[tuple[str, str, int]] = []
        self._progress_handler: Callable[[int, int, str], None] | None = None
        self._project_listeners: list[Callable[[ProjectDocument], None]] = []
        self._project_content_listeners: list[Callable[[ProjectDocument], None]] = []
        self._modified_listeners: list[Callable[[bool], None]] = []
        self._workspace_listeners: list[Callable[[str], None]] = []
        self._selection_listeners: list[Callable[[Any | None], None]] = []
        self._section_selection_listeners: list[Callable[[tuple[str, int, int] | None], None]] = []
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
        self._component_models: dict[str, Any] = {}
        self._geometry_providers: dict[str, GeometryProvider] = {}
        self._component_tree_providers: dict[str, ComponentTreeProvider] = {}
        self._project_tree_providers: dict[str, ProjectTreeProvider] = {}
        self._project_requirement_checker: Callable[[dict[str, Any]], list[str]] | None = None
        self._event_subscribers: dict[str, list[Callable[[Any], None]]] = {}
        self._undo_stack = QUndoStack()
        self._undo_stack.cleanChanged.connect(self._on_clean_changed)
        self._host = _StudioHost(self)

    @property
    def project(self) -> ProjectDocument | None:
        """Return the currently open project, or `None` when no project is open."""
        return self.current_project

    def add_panel(self, contribution: PanelContribution) -> None:
        """Add a dock panel to the application shell.

        @param contribution Panel descriptor with a globally unique ID.
        """
        if self._add_panel is not None:
            self._add_panel(contribution)
        else:
            self._pending_panels.append(contribution)

    def remove_panel(self, panel_id: str) -> None:
        """Remove a previously contributed panel by ID."""
        self._pending_panels = [p for p in self._pending_panels if p.id != panel_id]
        if self._remove_panel is not None:
            self._remove_panel(panel_id)

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
        """Clear the current status-bar message."""
        if self._status_handler is not None:
            self._status_handler("", "info", 0)

    def report_progress(self, completed: int, total: int, label: str = "") -> None:
        """Report task progress to the shell status bar.

        A total of 0 (or completed >= total) hides the progress bar.
        """
        if self._progress_handler is not None:
            self._progress_handler(completed, total, label)

    def clear_progress(self) -> None:
        """Hide the status-bar progress indicator."""
        self.report_progress(1, 1, "")

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Subscribe a callback handler to a named studio event (Event Bus).

        Bound methods owned by a QObject are removed automatically when that
        QObject is destroyed.
        """
        self._event_subscribers.setdefault(event_name, []).append(handler)
        owner = getattr(handler, "__self__", None)
        if isinstance(owner, QObject):
            # Panel callbacks commonly belong to widgets that are destroyed
            # when their plugin is deactivated. Remove the callback with the
            # QObject so a later event cannot target a deleted C++ object.
            owner.destroyed.connect(
                lambda _object=None, event=event_name, callback=handler: self.unsubscribe(
                    event, callback
                )
            )

    def unsubscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Unsubscribe a callback handler from a named studio event."""
        if event_name in self._event_subscribers:
            with suppress(ValueError):
                self._event_subscribers[event_name].remove(handler)

    def publish(self, event_name: str, payload: Any = None) -> None:
        """Publish an event to all subscribed listeners."""
        handlers = list(self._event_subscribers.get(event_name, []))
        for handler in handlers:
            try:
                handler(payload)
            except RuntimeError as exc:
                if "already deleted" in str(exc):
                    # QObject destruction can race with queued events. Drop
                    # the stale callback and keep the event bus healthy.
                    self.unsubscribe(event_name, handler)
                    logger.debug(
                        "Removed stale subscriber for event '%s': %s",
                        event_name,
                        exc,
                    )
                    continue
                logger.error(
                    "Error executing subscriber for event '%s': %s", event_name, exc, exc_info=True
                )
            except Exception as exc:
                logger.error(
                    "Error executing subscriber for event '%s': %s", event_name, exc, exc_info=True
                )

    def add_workspace(self, contribution: WorkspaceContribution) -> None:
        """Register a workspace, queuing it until the shell is ready."""
        if self._add_workspace is not None:
            self._add_workspace(contribution)
        else:
            self._pending_workspaces.append(contribution)

    def remove_workspace(self, workspace_id: str) -> None:
        """Remove a previously contributed workspace by ID."""
        self._pending_workspaces = [w for w in self._pending_workspaces if w.id != workspace_id]
        if self._remove_workspace is not None:
            self._remove_workspace(workspace_id)

    def set_workspace(self, contribution: WorkspaceContribution) -> None:
        """Register a workspace; retained as an alias for `add_workspace`."""
        self.add_workspace(contribution)

    def switch_workspace(self, workspace_id: str) -> None:
        """Activate a workspace and notify workspace listeners."""
        self.current_workspace_id = workspace_id
        if self._switch_workspace_handler is not None:
            self._switch_workspace_handler(workspace_id)
        for listener in list(self._workspace_listeners):
            listener(workspace_id)

    def on_workspace_changed(self, listener: Callable[[str], None]) -> None:
        """Subscribe to workspace changes and receive the current ID immediately."""
        self._workspace_listeners.append(listener)
        if self.current_workspace_id is not None:
            listener(self.current_workspace_id)

    def remove_workspace_listener(self, listener: Callable[[str], None]) -> None:
        """Unsubscribe a workspace-change listener."""
        if listener in self._workspace_listeners:
            self._workspace_listeners.remove(listener)

    def add_toolbar_item(self, contribution: ToolbarContribution) -> None:
        """Add an action to the main toolbar."""
        if self._add_toolbar_item is not None:
            self._add_toolbar_item(contribution)
        else:
            self._pending_toolbar_items.append(contribution)

    def remove_toolbar_item(self, contribution_id: str) -> None:
        """Remove a previously contributed toolbar action by ID."""
        self._pending_toolbar_items = [
            item for item in self._pending_toolbar_items if item.id != contribution_id
        ]
        if self._remove_toolbar_item is not None:
            self._remove_toolbar_item(contribution_id)

    def add_action(self, contribution: ActionContribution) -> None:
        """Add an action to the menu path declared by the contribution."""
        if self._add_action is not None:
            self._add_action(contribution)
        else:
            self._pending_actions.append(contribution)

    def remove_action(self, menu: str, title: str) -> None:
        """Remove a contributed menu action by menu path and title."""
        self._pending_actions = [
            a for a in self._pending_actions if not (a.menu == menu and a.title == title)
        ]
        if self._remove_action is not None:
            self._remove_action(menu, title)

    def add_settings_page(self, contribution: SettingsPageContribution) -> None:
        """Add a category to the application Settings dialog.

        Plugins may register pages during ``activate`` and remove them during
        ``deactivate``.  Pages are created lazily when the dialog is opened.
        """
        if contribution.id in self._settings_pages:
            raise ValueError(f"A settings page is already registered for: {contribution.id}")
        self._settings_pages[contribution.id] = contribution

    def remove_settings_page(self, page_id: str) -> None:
        """Remove a plugin settings page by ID."""
        self._settings_pages.pop(page_id, None)

    def register_tool(self, contribution: ToolContribution) -> None:
        """Register a Tools-menu command from a compact tool descriptor."""
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
        """Subscribe to project replacement and receive the current project immediately."""
        self._project_listeners.append(listener)
        if self.current_project is not None:
            listener(self.current_project)

    def on_project_content_changed(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        """Subscribe to edits made within the current project."""
        self._project_content_listeners.append(listener)

    def remove_project_content_listener(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        """Unsubscribe a project-content listener."""
        if listener in self._project_content_listeners:
            self._project_content_listeners.remove(listener)

    def on_modified_changed(self, listener: Callable[[bool], None]) -> None:
        """Subscribe to project modified-state changes and receive current state."""
        self._modified_listeners.append(listener)
        with suppress(RuntimeError):
            listener(bool(self.current_project and self.current_project.modified))

    def remove_modified_listener(self, listener: Callable[[bool], None]) -> None:
        """Unsubscribe a project modified-state listener."""
        if listener in self._modified_listeners:
            self._modified_listeners.remove(listener)

    def edit_component(
        self,
        component: dict[str, Any],
        description: str,
        change: Callable[[], None],
    ) -> None:
        """Apply one undoable edit to a component.

        @param component Mutable component object owned by the current project.
        @param description Human-readable undo command text.
        @param change Callback that performs the mutation.
        """
        before = deepcopy(component)
        change()
        after = deepcopy(component)
        component.clear()
        component.update(before)
        if before == after:
            return
        self._undo_stack.push(
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
        """Apply one undoable edit to the current project data."""
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
        self._undo_stack.push(
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
        """Undo the most recent project or component edit when available."""
        if self._undo_stack.canUndo():
            self._undo_stack.undo()
            self.set_selection(self.current_selection)

    def redo(self) -> None:
        """Redo the most recently undone edit when available."""
        if self._undo_stack.canRedo():
            self._undo_stack.redo()
            self.set_selection(self.current_selection)

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
        """Subscribe to selection changes and receive the current selection."""
        self._selection_listeners.append(listener)
        with suppress(RuntimeError):
            listener(self.current_selection)

    def set_selection(self, selection: Any | None) -> None:
        """Set the application selection and notify listeners."""
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
        """Subscribe to geometry-section selection changes."""
        self._section_selection_listeners.append(listener)
        with suppress(RuntimeError):
            listener(self.current_section_selection)

    def remove_section_selection_listener(
        self,
        listener: Callable[[tuple[str, int, int] | None], None],
    ) -> None:
        """Unsubscribe a geometry-section selection listener."""
        if listener in self._section_selection_listeners:
            self._section_selection_listeners.remove(listener)

    def set_section_selection(
        self,
        selection: tuple[str, int, int] | None,
    ) -> None:
        """Set the selected component, section, and side tuple."""
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
        """Register an editor factory for one fully qualified component type."""
        if component_type in self._component_editors:
            raise ValueError(f"A component editor is already registered for: {component_type}")
        self._component_editors[component_type] = factory

    def remove_component_editor(self, component_type: str) -> None:
        """Remove the editor factory registered for a component type."""
        self._component_editors.pop(component_type, None)

    def register_kind_editor(
        self,
        component_kind: str,
        factory: Callable[[dict[str, Any]], QWidget],
    ) -> None:
        """Register a fallback editor factory for a component kind."""
        if component_kind in self._kind_editors:
            raise ValueError(
                f"An editor is already registered for component kind: {component_kind}"
            )
        self._kind_editors[component_kind] = factory

    def remove_kind_editor(self, component_kind: str) -> None:
        """Remove the fallback editor registered for a component kind."""
        self._kind_editors.pop(component_kind, None)

    def create_component_editor(
        self,
        component: dict[str, Any],
    ) -> QWidget | None:
        component_type = component.get("type")
        factory = (
            self._component_editors.get(component_type) if isinstance(component_type, str) else None
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
        """Register an icon for one fully qualified component type."""
        if component_type in self._component_icons:
            raise ValueError(f"An icon is already registered for component type: {component_type}")
        self._component_icons[component_type] = icon

    def remove_component_icon(self, component_type: str) -> None:
        """Remove the icon registered for a component type."""
        self._component_icons.pop(component_type, None)

    def register_kind_icon(
        self,
        component_kind: str,
        icon: str | Path | QIcon,
    ) -> None:
        """Register a fallback icon for a component kind."""
        if component_kind in self._kind_icons:
            raise ValueError(f"An icon is already registered for component kind: {component_kind}")
        self._kind_icons[component_kind] = icon

    def remove_kind_icon(self, component_kind: str) -> None:
        """Remove the fallback icon registered for a component kind."""
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

    def register_component_model(
        self,
        component_type: str,
        model_factory: Any,
    ) -> None:
        """Register a domain model class or factory for a component type."""
        self._component_models[component_type] = model_factory

    def remove_component_model(self, component_type: str) -> None:
        """Remove a registered component model by component type."""
        self._component_models.pop(component_type, None)

    def create_component_model(
        self,
        component: dict[str, Any],
    ) -> Any:
        """Instantiate the domain model object for a given component dictionary."""
        from setuav_studio.component_model import GenericComponentModel

        component_type = component.get("type")
        factory = (
            self._component_models.get(component_type) if isinstance(component_type, str) else None
        )
        if factory is not None:
            return factory(component)
        return GenericComponentModel(component)

    def register_geometry_provider(
        self,
        component_type: str,
        provider: GeometryProvider,
    ) -> None:
        """Register a 3D geometry provider for a component type."""
        if component_type in self._geometry_providers:
            raise ValueError(f"A geometry provider is already registered for: {component_type}")
        self._geometry_providers[component_type] = provider

    def remove_geometry_provider(self, component_type: str) -> None:
        """Remove the geometry provider registered for a component type."""
        self._geometry_providers.pop(component_type, None)

    def register_component_tree_provider(
        self,
        provider_id: str,
        provider: ComponentTreeProvider,
    ) -> None:
        """Register a provider of virtual nodes beneath project components."""
        if provider_id in self._component_tree_providers:
            raise ValueError(f"A component tree provider is already registered for: {provider_id}")
        self._component_tree_providers[provider_id] = provider

    def remove_component_tree_provider(self, provider_id: str) -> None:
        """Remove a component-tree provider by ID."""
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
        """Register a provider of plugin-owned project-root nodes."""
        if provider_id in self._project_tree_providers:
            raise ValueError(f"A project tree provider is already registered for: {provider_id}")
        self._project_tree_providers[provider_id] = provider
        if self.current_project is not None:
            self.notify_project_content_changed()

    def remove_project_tree_provider(self, provider_id: str) -> None:
        """Remove a project-tree provider and refresh the project tree."""
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

        get_catalog().register_component_type_schema(
            component_type, schema_dict, plugin_id=plugin_id
        )

    def build_geometry_data(
        self,
        project: ProjectDocument | None = None,
    ) -> Any:
        """Build combined geometry data using all registered providers."""
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
        """Unsubscribe a project replacement listener."""
        if listener in self._project_listeners:
            self._project_listeners.remove(listener)

    def remove_selection_listener(
        self,
        listener: Callable[[Any | None], None],
    ) -> None:
        """Unsubscribe a selection listener."""
        if listener in self._selection_listeners:
            self._selection_listeners.remove(listener)


__all__ = ["StudioAPI"]
