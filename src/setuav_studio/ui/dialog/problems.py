"""Dialog displaying consolidated system problems, plugin warnings, and constraint violations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.api.api import StudioAPI


@dataclass(frozen=True)
class Problem:
    """Represents a single problem, constraint violation, or system/plugin warning."""

    id: str
    title: str
    message: str
    severity: str = "warning"  # "error" | "warning" | "info"
    source: str = "System"  # "Constraint" | "Plugin" | "System" | "Geometry" etc.


class ProblemsDialog(QDialog):
    """Simple read-only window listing problems as a table, matching LogWindow layout."""

    def __init__(
        self,
        problems: Sequence[Problem],
        parent: QWidget | None = None,
        api: StudioAPI | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._problems = list(problems)

        self.setWindowTitle("Problems")
        self.setWindowIcon(get_icon("warning"))
        self.setMinimumSize(760, 460)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.problem_table = QTableWidget(0, 4, self)
        self.problem_table.setObjectName("problemsTable")
        self.problem_table.setHorizontalHeaderLabels(["Severity", "Source", "Problem", "Message"])
        self.problem_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.problem_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.problem_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.problem_table.setWordWrap(True)
        self.problem_table.verticalHeader().setVisible(False)

        header = self.problem_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.problem_table)

        self._populate_table()

    def _populate_table(self) -> None:
        self.problem_table.setRowCount(0)
        if not self._problems:
            self.problem_table.insertRow(0)
            msg_item = QTableWidgetItem("No problems or rule violations detected.")
            msg_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.problem_table.setItem(0, 3, msg_item)
            return

        for row, p in enumerate(self._problems):
            self.problem_table.insertRow(row)
            icon_key = "error" if p.severity == "error" else "warning"
            sev_text = p.severity.capitalize()

            sev_item = QTableWidgetItem(get_icon(icon_key), sev_text)
            source_item = QTableWidgetItem(p.source)
            title_item = QTableWidgetItem(p.title)
            desc_item = QTableWidgetItem(p.message)

            self.problem_table.setItem(row, 0, sev_item)
            self.problem_table.setItem(row, 1, source_item)
            self.problem_table.setItem(row, 2, title_item)
            self.problem_table.setItem(row, 3, desc_item)


__all__ = ["Problem", "ProblemsDialog"]
