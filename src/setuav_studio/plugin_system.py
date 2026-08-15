from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from setuav_studio.project import ProjectDocument


@dataclass(frozen=True)
class PanelContribution:
    id: str
    title: str
    factory: Callable[[], QWidget]
    area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea


class StudioAPI:
    def __init__(self) -> None:
        self.current_project: ProjectDocument | None = None
        self.current_selection: Any | None = None
        self._add_panel: Callable[[PanelContribution], None] | None = None
        self._project_listeners: list[Callable[[ProjectDocument], None]] = []
        self._selection_listeners: list[Callable[[Any | None], None]] = []
        self._component_editors: dict[
            str,
            Callable[[dict[str, Any]], QWidget],
        ] = {}

    def set_panel_handler(self, handler: Callable[[PanelContribution], None]) -> None:
        self._add_panel = handler

    def add_panel(self, contribution: PanelContribution) -> None:
        if self._add_panel is None:
            raise RuntimeError("The Studio shell is not ready for panel contributions")
        self._add_panel(contribution)

    def on_project_changed(self, listener: Callable[[ProjectDocument], None]) -> None:
        self._project_listeners.append(listener)
        if self.current_project is not None:
            listener(self.current_project)

    def set_project(self, project: ProjectDocument) -> None:
        self.current_project = project
        self.set_selection(None)
        for listener in self._project_listeners:
            listener(project)

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

    def create_component_editor(
        self,
        component: dict[str, Any],
    ) -> QWidget | None:
        component_type = component.get("type")
        if not isinstance(component_type, str):
            return None
        factory = self._component_editors.get(component_type)
        if factory is None:
            return None
        return factory(component)


class StudioPlugin(Protocol):
    id: str

    def activate(self, api: StudioAPI) -> None: ...


class PluginManager:
    def __init__(self, api: StudioAPI) -> None:
        self._api = api
        self._plugins: dict[str, StudioPlugin] = {}

    def activate(self, plugin: StudioPlugin) -> None:
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin is already active: {plugin.id}")
        plugin.activate(self._api)
        self._plugins[plugin.id] = plugin
