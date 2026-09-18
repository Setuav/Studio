"""Log buffer and application logs dialog window."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import NamedTuple

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from setuav_studio.ui.style.theme import status_color, tokens

MAX_BUFFER_SIZE = 2000


class LogEntry(NamedTuple):
    time: str
    level: str
    name: str
    message: str


_buffer: deque[LogEntry] = deque(maxlen=MAX_BUFFER_SIZE)
_handler: logging.Handler | None = None


class LogBridge(QObject):
    """Emits a Qt signal when a new log entry is captured, safe across threads."""

    record_added = Signal(object)


_bridge = LogBridge()


class _LogBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        entry = LogEntry(
            time=time.strftime("%H:%M:%S", time.localtime(record.created)),
            level=record.levelname,
            name=record.name,
            message=message,
        )
        _buffer.append(entry)
        _bridge.record_added.emit(entry)


def install_log_buffer(level: int = logging.INFO) -> None:
    """Attach an in-memory log buffer to the root logger (idempotent)."""
    global _handler
    root = logging.getLogger()
    if _handler is None:
        _handler = _LogBufferHandler()
        root.addHandler(_handler)
    _handler.setLevel(level)


def log_buffer_entries() -> list[LogEntry]:
    """Return the captured log entries in chronological order."""
    return list(_buffer)


def log_signal() -> LogBridge:
    """Return the Qt bridge that emits on each new log entry."""
    return _bridge


def clear_log_buffer() -> None:
    _buffer.clear()


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
