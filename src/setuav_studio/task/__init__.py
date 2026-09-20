"""Central background task execution package."""

from .manager import TaskHandleImpl, TaskManager
from .types import (
    CancellationToken,
    TaskCancelledError,
    TaskHandle,
    TaskManagerProtocol,
    TaskPriority,
    TaskProgress,
    TaskStatus,
)

__all__ = [
    "CancellationToken",
    "TaskCancelledError",
    "TaskHandle",
    "TaskHandleImpl",
    "TaskManager",
    "TaskManagerProtocol",
    "TaskPriority",
    "TaskProgress",
    "TaskStatus",
]
