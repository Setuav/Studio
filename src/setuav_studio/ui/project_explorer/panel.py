from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.project_explorer.tree import ProjectExplorer
from setuav_studio.ui.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ProjectExplorerPanel(QWidget):
    """Panel containing search box and the clean model tree."""

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search bar
        search_box = QWidget()
        s_layout = QHBoxLayout(search_box)
        s_layout.setContentsMargins(2, 2, 2, 2)
        s_layout.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter model...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(
            get_icon("fa6s.magnifying-glass"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        s_layout.addWidget(self.search_edit)
        self.expand_all_button = self._tree_action_button(
            "fa6s.square-plus",
            "Expand All",
            self._expand_all,
        )
        s_layout.addWidget(self.expand_all_button)
        self.collapse_all_button = self._tree_action_button(
            "fa6s.square-minus",
            "Collapse All",
            self._collapse_all,
        )
        s_layout.addWidget(self.collapse_all_button)
        layout.addWidget(search_box)

        self.explorer = ProjectExplorer(api)
        layout.addWidget(self.explorer, 1)

        self.search_edit.textChanged.connect(self.explorer.filter_items)

    def _expand_all(self) -> None:
        self.explorer.expandAll()

    def _collapse_all(self) -> None:
        self.explorer.collapseAll()

    @staticmethod
    def _tree_action_button(
        icon_name: str,
        tooltip: str,
        callback: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton()
        button.setIcon(get_icon(icon_name))
        button.setToolTip(tooltip)
        button.setStatusTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setAutoRaise(True)
        button.setFixedSize(26, 26)
        button.clicked.connect(callback)
        return button

    def update_theme_style(self) -> None:
        self.explorer.refresh_project()
        self.explorer.viewport().update()
