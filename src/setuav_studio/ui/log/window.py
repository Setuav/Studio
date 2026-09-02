from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from setuav_studio.ui.log.buffer import LogEntry, log_buffer_entries, log_signal
from setuav_studio.ui.theme import status_color, tokens


class LogWindow(QDialog):
    """Simple read-only window showing the application's captured logs as a table."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Application Logs")
        self.setMinimumSize(760, 460)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Time", "Level", "Message"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setWordWrap(True)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self._table)

        for entry in log_buffer_entries():
            self._append_entry(entry, resize=False)
        self._scroll_to_bottom()
        log_signal().record_added.connect(self._append_entry)

    def _append_entry(self, entry: LogEntry, resize: bool = True) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        time_item = QTableWidgetItem(entry.time)
        level_item = QTableWidgetItem(entry.level)
        message = f"{entry.name}: {entry.message}" if entry.name else entry.message
        message_item = QTableWidgetItem(message)

        level = entry.level.lower()
        color = (
            status_color(level)
            if level in {"info", "success", "warning", "error"}
            else tokens()["text"]
        )
        brush = QBrush(QColor(color))
        time_item.setForeground(brush)
        level_item.setForeground(brush)
        message_item.setForeground(brush)

        self._table.setItem(row, 0, time_item)
        self._table.setItem(row, 1, level_item)
        self._table.setItem(row, 2, message_item)
        if resize:
            self._table.resizeRowToContents(row)
        self._scroll_to_bottom()

    def update_theme_style(self) -> None:
        for row in range(self._table.rowCount()):
            level_item = self._table.item(row, 1)
            if level_item is None:
                continue
            level = level_item.text().lower()
            color = (
                status_color(level)
                if level in {"info", "success", "warning", "error"}
                else tokens()["text"]
            )
            brush = QBrush(QColor(color))
            for column in range(self._table.columnCount()):
                item = self._table.item(row, column)
                if item is not None:
                    item.setForeground(brush)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._table.resizeRowsToContents()
        self._scroll_to_bottom()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible():
            self._table.resizeRowsToContents()

    def _scroll_to_bottom(self) -> None:
        scrollbar = self._table.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
