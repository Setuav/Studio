"""Public services and provider contracts available to plugins.

@defgroup plugin_api Plugin API
@brief Services passed to ``StudioPlugin.activate``.

@defgroup providers Provider contracts
@brief Callbacks and services that plugins may register.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from setuav_studio.project import ProjectDocument

from .contributions import (
    ActionContribution,
    ComponentTreeNodeContribution,
    PanelContribution,
    ProjectTreeNodeContribution,
    SettingsPageContribution,
    ToolbarContribution,
    ToolContribution,
    WorkspaceContribution,
)

__all__ = [
    "ComponentTreeProvider",
    "GeometryProvider",
    "MassPropertiesProvider",
    "ProjectDocument",
    "ProjectTreeProvider",
    "StudioAPI",
]

GeometryProvider = Callable[[dict[str, Any]], Any]
ComponentTreeProvider = Callable[
    [dict[str, Any]],
    tuple[ComponentTreeNodeContribution, ...],
]
ProjectTreeProvider = Callable[
    [ProjectDocument],
    tuple[ProjectTreeNodeContribution, ...],
]


class MassPropertiesProvider(Protocol):
    """Project-level mass-properties service contributed by a plugin.

    @ingroup providers
    """

    def evaluate(self, project: ProjectDocument) -> Any:
        """Calculate mass, center-of-gravity, and inertia data for a project."""
        ...


class StudioAPI(Protocol):
    """Stable service surface passed to plugins during activation.

    Use this interface to register contributions, observe application state,
    edit project data with undo support, and communicate with other plugins.
    UI factories and callbacks run on the Qt UI thread; move expensive work to
    a worker thread.

    Identifiers must be globally unique. Use a reverse-domain prefix owned by
    the plugin, for example ``com.example.analysis.panel``. Registrations and
    listeners must currently be removed in ``StudioPlugin.deactivate``.

    @ingroup plugin_api
    """

    @property
    def project(self) -> ProjectDocument | None:
        """Currently open project, or ``None`` when no project is open."""
        ...

    @property
    def current_project(self) -> ProjectDocument | None:
        """Currently open project, exposed under the application property name."""
        ...

    @property
    def current_selection(self) -> Any | None:
        """Object currently selected in the application shell."""
        ...

    @property
    def current_section_selection(self) -> tuple[str, int, int] | None:
        """Selected geometry component, section kind, and section index."""
        ...

    @property
    def current_workspace_id(self) -> str | None:
        """Identifier of the active workspace."""
        ...

    def add_panel(self, contribution: PanelContribution) -> None:
        """Add a dockable panel to the application shell."""
        ...

    def remove_panel(self, panel_id: str) -> None:
        """Remove a panel previously registered by the plugin."""
        ...

    def add_workspace(self, contribution: WorkspaceContribution) -> None:
        """Add a workspace to the main workspace selector."""
        ...

    def remove_workspace(self, workspace_id: str) -> None:
        """Remove a workspace previously registered by the plugin."""
        ...

    def switch_workspace(self, workspace_id: str) -> None:
        """Activate a workspace by identifier."""
        ...

    def on_workspace_changed(self, listener: Callable[[str], None]) -> None:
        """Subscribe to workspace changes and immediately receive the current ID."""
        ...

    def add_toolbar_item(self, contribution: ToolbarContribution) -> None:
        """Add an item to the main toolbar."""
        ...

    def remove_toolbar_item(self, contribution_id: str) -> None:
        """Remove a toolbar item previously registered by the plugin."""
        ...

    def add_action(self, contribution: ActionContribution) -> None:
        """Add an action to an application menu path."""
        ...

    def remove_action(self, menu: str, title: str) -> None:
        """Remove an action using its menu path and title."""
        ...

    def register_tool(self, contribution: ToolContribution) -> None:
        """Add a command to the Tools menu."""
        ...

    def add_settings_page(self, contribution: SettingsPageContribution) -> None:
        """Add a lazily created page to the Settings dialog."""
        ...

    def remove_settings_page(self, page_id: str) -> None:
        """Remove a settings page previously registered by the plugin."""
        ...

    def show_status(self, message: str, level: str = "info", timeout_ms: int = 5000) -> None:
        """Show a status message; level is info, success, warning, or error."""
        ...

    def clear_status(self) -> None:
        """Clear the current status message."""
        ...

    def report_progress(self, completed: int, total: int, label: str = "") -> None:
        """Report task progress; a completed task hides the progress display."""
        ...

    def clear_progress(self) -> None:
        """Hide the task progress display."""
        ...

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Subscribe a callback to a named application event."""
        ...

    def unsubscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Remove a callback from a named application event."""
        ...

    def publish(self, event_name: str, payload: Any = None) -> None:
        """Publish a payload to subscribers of a named event."""
        ...

    def on_project_changed(self, listener: Callable[[ProjectDocument], None]) -> None:
        """Subscribe to project replacement and immediately receive the open project."""
        ...

    def remove_project_listener(self, listener: Callable[[ProjectDocument], None]) -> None:
        """Remove a project replacement listener."""
        ...

    def on_project_content_changed(self, listener: Callable[[ProjectDocument], None]) -> None:
        """Subscribe to edits made within the current project."""
        ...

    def remove_project_content_listener(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        """Remove a project-content listener."""
        ...

    def on_modified_changed(self, listener: Callable[[bool], None]) -> None:
        """Subscribe to changes in the current project's modified state."""
        ...

    def remove_modified_listener(self, listener: Callable[[bool], None]) -> None:
        """Remove a project modified-state listener."""
        ...

    def edit_component(
        self,
        component: dict[str, Any],
        description: str,
        change: Callable[[], None],
    ) -> None:
        """Apply a component mutation as one undoable operation."""
        ...

    def edit_project(self, description: str, change: Callable[[], None]) -> None:
        """Apply a project mutation as one undoable operation."""
        ...

    def edit_project_extension(
        self,
        namespace: str,
        description: str,
        change: Callable[[dict[str, Any]], None],
    ) -> None:
        """Edit namespaced project extension data with undo support."""
        ...

    def edit_component_extension(
        self,
        component_id: str,
        namespace: str,
        description: str,
        change: Callable[[dict[str, Any]], None],
    ) -> None:
        """Edit namespaced component extension data with undo support."""
        ...

    def undo(self) -> None:
        """Undo the most recent project or component edit."""
        ...

    def redo(self) -> None:
        """Redo the most recently undone edit."""
        ...

    def notify_project_content_changed(self) -> None:
        """Request refresh after a mutation performed outside the edit helpers."""
        ...

    def on_selection_changed(self, listener: Callable[[Any | None], None]) -> None:
        """Subscribe to selection changes and immediately receive the current value."""
        ...

    def remove_selection_listener(self, listener: Callable[[Any | None], None]) -> None:
        """Remove a selection listener."""
        ...

    def set_selection(self, selection: Any | None) -> None:
        """Change the application selection."""
        ...

    def on_section_selection_changed(
        self,
        listener: Callable[[tuple[str, int, int] | None], None],
    ) -> None:
        """Subscribe to geometry-section selection changes."""
        ...

    def remove_section_selection_listener(
        self,
        listener: Callable[[tuple[str, int, int] | None], None],
    ) -> None:
        """Remove a geometry-section selection listener."""
        ...

    def set_section_selection(self, selection: tuple[str, int, int] | None) -> None:
        """Change the selected component section."""
        ...

    def register_component_editor(
        self,
        component_type: str,
        factory: Callable[[dict[str, Any]], QWidget],
    ) -> None:
        """Register an editor factory for a fully qualified component type."""
        ...

    def remove_component_editor(self, component_type: str) -> None:
        """Remove an editor factory registered for a component type."""
        ...

    def register_kind_editor(
        self,
        component_kind: str,
        factory: Callable[[dict[str, Any]], QWidget],
    ) -> None:
        """Register a fallback editor factory for a component kind."""
        ...

    def remove_kind_editor(self, component_kind: str) -> None:
        """Remove an editor factory registered for a component kind."""
        ...

    def create_component_editor(self, component: dict[str, Any]) -> QWidget | None:
        """Create the best registered editor for a component or selection."""
        ...

    def register_component_icon(self, component_type: str, icon: str | Path | QIcon) -> None:
        """Register an icon for a fully qualified component type."""
        ...

    def remove_component_icon(self, component_type: str) -> None:
        """Remove an icon registered for a component type."""
        ...

    def register_kind_icon(self, component_kind: str, icon: str | Path | QIcon) -> None:
        """Register a fallback icon for a component kind."""
        ...

    def remove_kind_icon(self, component_kind: str) -> None:
        """Remove a fallback icon registered for a component kind."""
        ...

    def get_component_icon(self, component: dict[str, Any]) -> QIcon:
        """Resolve the best registered icon for a component or selection."""
        ...

    def register_geometry_provider(self, component_type: str, provider: GeometryProvider) -> None:
        """Register a geometry provider for a fully qualified component type."""
        ...

    def remove_geometry_provider(self, component_type: str) -> None:
        """Remove a geometry provider registered for a component type."""
        ...

    def build_geometry_data(self, project: ProjectDocument | None = None) -> Any:
        """Build combined geometry data using all registered providers."""
        ...

    def register_component_tree_provider(
        self,
        provider_id: str,
        provider: ComponentTreeProvider,
    ) -> None:
        """Register virtual child nodes displayed beneath project components."""
        ...

    def remove_component_tree_provider(self, provider_id: str) -> None:
        """Remove a component-tree provider."""
        ...

    def component_tree_nodes(
        self,
        component: dict[str, Any],
    ) -> tuple[ComponentTreeNodeContribution, ...]:
        """Collect virtual child nodes for a project component."""
        ...

    def register_project_tree_provider(
        self,
        provider_id: str,
        provider: ProjectTreeProvider,
    ) -> None:
        """Register plugin-owned nodes displayed beneath the project root."""
        ...

    def remove_project_tree_provider(self, provider_id: str) -> None:
        """Remove a project-tree provider."""
        ...

    def project_tree_nodes(
        self,
        project: ProjectDocument,
    ) -> tuple[ProjectTreeNodeContribution, ...]:
        """Collect plugin-owned nodes for the project root."""
        ...

    def register_mass_properties_provider(
        self,
        provider_id: str,
        provider: MassPropertiesProvider,
    ) -> None:
        """Register a synchronous mass-properties provider."""
        ...

    def remove_mass_properties_provider(self, provider_id: str) -> None:
        """Remove a mass-properties provider."""
        ...

    def get_mass_properties_provider(
        self,
        provider_id: str | None = None,
    ) -> MassPropertiesProvider | None:
        """Resolve a provider by ID, or return the sole registered provider."""
        ...

    def register_schema(self, schema_id: str, schema_dict: dict[str, Any]) -> None:
        """Register a reusable JSON Schema document."""
        ...

    def register_component_type_schema(
        self,
        component_type: str,
        schema_dict: dict[str, Any],
        plugin_id: str | None = None,
    ) -> None:
        """Register a JSON Schema for a fully qualified component type."""
        ...
