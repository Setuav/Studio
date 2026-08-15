from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module, metadata
import pkgutil
from typing import Any, Protocol

from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoCommand, QUndoStack
from PySide6.QtWidgets import QWidget

from setuav_studio.project import ProjectDocument
from setuav_studio.geometry_data import GeometryData
from setuav_studio.geometry_scene import GeometryProvider, build_project_geometry


@dataclass(frozen=True)
class PanelContribution:
    id: str
    title: str
    factory: Callable[[], QWidget]
    area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea


@dataclass(frozen=True)
class WorkspaceContribution:
    id: str
    factory: Callable[[], QWidget]


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


class StudioAPI:
    def __init__(self) -> None:
        self.current_project: ProjectDocument | None = None
        self.current_selection: Any | None = None
        self._add_panel: Callable[[PanelContribution], None] | None = None
        self._set_workspace: Callable[[WorkspaceContribution], None] | None = None
        self._project_listeners: list[Callable[[ProjectDocument], None]] = []
        self._project_content_listeners: list[Callable[[ProjectDocument], None]] = []
        self._modified_listeners: list[Callable[[bool], None]] = []
        self._selection_listeners: list[Callable[[Any | None], None]] = []
        self._component_editors: dict[
            str,
            Callable[[dict[str, Any]], QWidget],
        ] = {}
        self._kind_editors: dict[
            str,
            Callable[[dict[str, Any]], QWidget],
        ] = {}
        self._geometry_providers: dict[str, GeometryProvider] = {}
        self._project_requirement_checker: (
            Callable[[dict[str, Any]], list[str]] | None
        ) = None
        self.undo_stack = QUndoStack()
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)

    def set_panel_handler(self, handler: Callable[[PanelContribution], None]) -> None:
        self._add_panel = handler

    def add_panel(self, contribution: PanelContribution) -> None:
        if self._add_panel is None:
            raise RuntimeError("The Studio shell is not ready for panel contributions")
        self._add_panel(contribution)

    def set_workspace_handler(
        self,
        handler: Callable[[WorkspaceContribution], None],
    ) -> None:
        self._set_workspace = handler

    def set_workspace(self, contribution: WorkspaceContribution) -> None:
        if self._set_workspace is None:
            raise RuntimeError("The Studio shell is not ready for a workspace contribution")
        self._set_workspace(contribution)

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
        for listener in self._project_listeners:
            listener(project)

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
        listener(bool(self.current_project and self.current_project.modified))

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

    def _notify_project_content_changed(self) -> None:
        if self.current_project is None:
            return
        for listener in self._project_content_listeners:
            listener(self.current_project)

    def _on_clean_changed(self, clean: bool) -> None:
        modified = not clean
        if self.current_project is not None:
            self.current_project.modified = modified
        for listener in self._modified_listeners:
            listener(modified)

    def on_selection_changed(self, listener: Callable[[Any | None], None]) -> None:
        self._selection_listeners.append(listener)
        listener(self.current_selection)

    def set_selection(self, selection: Any | None) -> None:
        self.current_selection = selection
        for listener in self._selection_listeners:
            listener(selection)

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

    def register_geometry_provider(
        self,
        component_type: str,
        provider: GeometryProvider,
    ) -> None:
        if component_type in self._geometry_providers:
            raise ValueError(f"A geometry provider is already registered for: {component_type}")
        self._geometry_providers[component_type] = provider

    def build_geometry_data(
        self,
        project: ProjectDocument | None = None,
    ) -> GeometryData:
        document = project or self.current_project
        if document is None:
            return GeometryData()
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

    def activate(self, api: StudioAPI) -> None: ...


class PluginManager:
    def __init__(self, api: StudioAPI) -> None:
        self._api = api
        self._plugins: dict[str, StudioPlugin] = {}
        self._providers: dict[str, str] = {}
        api.set_project_requirement_checker(self.check_project_requirements)

    def activate(self, plugin: StudioPlugin) -> None:
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin is already active: {plugin.id}")
        plugin.activate(self._api)
        self._plugins[plugin.id] = plugin
        provides = getattr(plugin, "provides", {})
        if isinstance(provides, dict):
            for plugin_id, version in provides.items():
                self._providers[str(plugin_id)] = str(version)

    def discover(self) -> list[PluginLoadIssue]:
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
        for module_info in pkgutil.iter_modules(package.__path__):
            source = f"setuav_studio.plugins.{module_info.name}"
            try:
                module = import_module(source)
                candidate = getattr(module, "PLUGIN", None)
                if candidate is not None:
                    self._activate_candidate(candidate)
            except Exception as exc:
                issues.append(PluginLoadIssue(source, str(exc)))
        return issues

    def _discover_entry_points(self) -> list[PluginLoadIssue]:
        issues: list[PluginLoadIssue] = []
        for entry_point in metadata.entry_points(group="setuav_studio.plugins"):
            try:
                self._activate_candidate(entry_point.load())
            except Exception as exc:
                issues.append(PluginLoadIssue(entry_point.name, str(exc)))
        return issues

    def _activate_candidate(self, candidate: object) -> None:
        plugin = candidate() if isinstance(candidate, type) else candidate
        plugin_id = getattr(plugin, "id", None)
        if isinstance(plugin_id, str) and plugin_id in self._plugins:
            return
        if not hasattr(plugin, "activate") or not isinstance(plugin_id, str):
            raise TypeError("Plugin entry must provide id and activate(api)")
        self.activate(plugin)


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
        major, minor, patch = minimum
        if major > 0:
            maximum = (major + 1, 0, 0)
        elif minor > 0:
            maximum = (0, minor + 1, 0)
        else:
            maximum = (0, 0, patch + 1)
        return installed_version < maximum
    expected = _parse_version(requirement)
    return expected == installed_version


def _parse_version(value: str) -> tuple[int, int, int] | None:
    try:
        parts = value.split("-", 1)[0].split("+", 1)[0].split(".")
        if len(parts) != 3:
            return None
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
