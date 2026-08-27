"""Movable native toolbars used by the main application window."""

import re
from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QToolBar, QToolButton

from setuav_studio.ui.icons import get_icon
from setuav_studio_sdk import WorkspaceContribution


def _configure_toolbar(toolbar: QToolBar) -> None:
    toolbar.setMovable(True)
    toolbar.setFloatable(False)
    toolbar.setAllowedAreas(Qt.ToolBarArea.AllToolBarAreas)
    toolbar.setIconSize(QSize(18, 18))
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)


class WorkspaceToolBar(QToolBar):
    """Movable toolbar containing the active-workspace selector."""

    workspace_activated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Workspaces", parent)
        self.setObjectName("studio.workspace_toolbar")
        _configure_toolbar(self)

        self.workspace_combo = QComboBox(self)
        self.workspace_combo.setObjectName("studio.workspace_combo")
        self.workspace_combo.setToolTip("Workspace")
        self.workspace_combo.setMinimumWidth(170)
        self.workspace_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.workspace_combo.currentIndexChanged.connect(self._emit_workspace_selection)

        self.addWidget(self.workspace_combo)

    def set_workspaces(
        self,
        workspaces: Iterable[WorkspaceContribution],
        current_workspace_id: str | None,
    ) -> None:
        self.workspace_combo.blockSignals(True)
        try:
            self.workspace_combo.clear()
            current_index = -1
            for index, workspace in enumerate(workspaces):
                if workspace.icon:
                    self.workspace_combo.addItem(
                        get_icon(workspace.icon),
                        workspace.title,
                        workspace.id,
                    )
                else:
                    self.workspace_combo.addItem(workspace.title, workspace.id)
                if workspace.id == current_workspace_id:
                    current_index = index

            if current_index < 0 and self.workspace_combo.count() > 0:
                current_index = 0
            self.workspace_combo.setCurrentIndex(current_index)
            self.workspace_combo.setEnabled(self.workspace_combo.count() > 0)
        finally:
            self.workspace_combo.blockSignals(False)

    def set_current_workspace(self, workspace_id: str) -> None:
        index = self.workspace_combo.findData(workspace_id)
        if index < 0 or index == self.workspace_combo.currentIndex():
            return
        self.workspace_combo.blockSignals(True)
        try:
            self.workspace_combo.setCurrentIndex(index)
        finally:
            self.workspace_combo.blockSignals(False)

    def _emit_workspace_selection(self, index: int) -> None:
        workspace_id = self.workspace_combo.itemData(index)
        if isinstance(workspace_id, str) and workspace_id:
            self.workspace_activated.emit(workspace_id)


class ToolSetBar(QToolBar):
    """One independently movable group of plugin-contributed tools."""

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


__all__ = ["ToolSetBar", "WorkspaceToolBar"]
