from __future__ import annotations

import logging
import time
from collections import deque
from typing import NamedTuple

from PySide6.QtCore import QObject, Signal

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
