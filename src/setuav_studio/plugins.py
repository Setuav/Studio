from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

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
        self._add_panel: Callable[[PanelContribution], None] | None = None
        self._project_listeners: list[Callable[[ProjectDocument], None]] = []

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
        for listener in self._project_listeners:
            listener(project)


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
