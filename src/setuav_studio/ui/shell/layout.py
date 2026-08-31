from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from .window import MainWindow


class _WorkspaceLayoutContext:
    """Host implementation of the SDK workspace-layout protocol."""

    def __init__(self, window: MainWindow, workspace_id: str) -> None:
        self._window = window
        self.workspace_id = workspace_id

    def show(self, *dock_ids: str) -> None:
        for dock_id in dock_ids:
            dock = self._window._dock(dock_id)
            if dock is not None:
                dock.show()

    def hide(self, *dock_ids: str) -> None:
        for dock_id in dock_ids:
            dock = self._window._dock(dock_id)
            if dock is not None:
                dock.hide()

    def split(
        self,
        first_dock_id: str,
        second_dock_id: str,
        orientation: str = "horizontal",
    ) -> None:
        first = self._window._dock(first_dock_id)
        second = self._window._dock(second_dock_id)
        if first is None or second is None:
            return
        direction = (
            Qt.Orientation.Vertical
            if orientation.casefold() == "vertical"
            else Qt.Orientation.Horizontal
        )
        self._window.splitDockWidget(first, second, direction)

    def resize(self, dock_ids: tuple[str, ...], sizes: tuple[int, ...]) -> None:
        docks = tuple(
            dock for dock_id in dock_ids if (dock := self._window._dock(dock_id)) is not None
        )
        self._window._resize_visible_docks(docks, list(sizes))

    def raise_dock(self, dock_id: str) -> None:
        dock = self._window._dock(dock_id)
        if dock is not None:
            dock.raise_()


__all__ = ["_WorkspaceLayoutContext"]
