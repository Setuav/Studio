"""Movable native toolbars used by the main application window."""

import re
from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar, QToolButton


def _configure_toolbar(toolbar: QToolBar) -> None:
    toolbar.setMovable(True)
    toolbar.setFloatable(False)
    toolbar.setAllowedAreas(Qt.ToolBarArea.AllToolBarAreas)
    toolbar.setIconSize(QSize(18, 18))
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)


class ToolSetBar(QToolBar):
    """One independently movable group of contributed tools."""

    def __init__(self, group: str, parent=None) -> None:
        title = group.replace("_", " ").replace("-", " ").title()
        super().__init__(title or "Tools", parent)
        object_suffix = re.sub(r"[^a-z0-9_.-]+", "-", group.casefold()).strip("-")
        self.setObjectName(f"studio.toolset.{object_suffix or 'default'}")
        _configure_toolbar(self)
        self._rendered_actions: list[QAction] = []

    def set_tools(self, actions: Iterable[QAction]) -> None:
        for action in self._rendered_actions:
            self.removeAction(action)
        self._rendered_actions = list(actions)
        for action in self._rendered_actions:
            self.addAction(action)
            button = self.widgetForAction(action)
            if isinstance(button, QToolButton) and action.menu() is not None:
                button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)


class StandardToolBar(QToolBar):
    """Movable toolbar containing standard project and edit actions."""

    def __init__(self, parent=None) -> None:
        super().__init__("Standard", parent)
        self.setObjectName("studio.standard_toolbar")
        _configure_toolbar(self)


__all__ = ["StandardToolBar", "ToolSetBar"]
