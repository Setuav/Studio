"""Data types and protocols for background task management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


class TaskStatus(StrEnum):
    """Lifecycle status of a background task."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    CANCELLED = "cancelled"
    ERROR = "error"


class TaskPriority(IntEnum):
    """Execution priority of a background task."""

    LOW = -10
    NORMAL = 0
    HIGH = 10
    CRITICAL = 20


@dataclass(frozen=True)
class TaskProgress:
    """Task execution progress snapshot."""

    current: int
    total: int
    message: str = ""

    @property
    def percentage(self) -> float:
        """Progress percentage in range [0.0, 100.0]."""
        if self.total <= 0:
            return 0.0
        return min(100.0, max(0.0, (self.current / self.total) * 100.0))


class CancellationToken(Protocol):
    """Token passed to task callbacks to inspect cancellation and report progress."""

    @property
    def is_cancelled(self) -> bool:
        """True if cancellation was requested for this task."""
        ...

    def check_cancelled(self) -> None:
        """Raise TaskCancelledError if cancellation was requested."""
        ...

    def report_progress(self, current: int, total: int, message: str = "") -> None:
        """Report execution progress back to the manager."""
        ...


class TaskCancelledError(Exception):
    """Raised when a background task execution is cancelled."""


class TaskHandle(Protocol[T_co]):
    """Handle to a submitted background task."""

    @property
    def id(self) -> str:
        """Unique task identifier."""
        ...

    @property
    def name(self) -> str:
        """Human-readable task name."""
        ...

    @property
    def priority(self) -> TaskPriority:
        """Task priority."""
        ...

    @property
    def status(self) -> TaskStatus:
        """Current lifecycle status."""
        ...

    @property
    def is_cancelled(self) -> bool:
        """True if cancellation was requested."""
        ...

    @property
    def created_at(self) -> float:
        """Epoch timestamp when the task was created."""
        ...

    @property
    def started_at(self) -> float | None:
        """Epoch timestamp when the task started running."""
        ...

    @property
    def completed_at(self) -> float | None:
        """Epoch timestamp when the task finished/failed/cancelled."""
        ...

    @property
    def duration_seconds(self) -> float:
        """Total execution duration in seconds."""
        ...

    @property
    def progress(self) -> TaskProgress | None:
        """Current progress snapshot."""
        ...

    @property
    def result(self) -> Any | None:
        """Result returned by successful task execution."""
        ...

    @property
    def error(self) -> Exception | None:
        """Exception raised during task execution, if any."""
        ...

    def cancel(self) -> bool:
        """Request cancellation."""
        ...


class TaskManagerProtocol(Protocol):
    """Central background task manager contract exposed to plugins."""

    def submit(
        self,
        name: str,
        target: Callable[[CancellationToken], T],
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
        on_finished: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_progress: Callable[[TaskProgress], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
    ) -> TaskHandle[T]:
        """Submit a callable to the background thread pool."""
        ...

    def cancel(self, task_id: str) -> bool:
        """Cancel a task by its identifier."""
        ...

    def cancel_all(self) -> None:
        """Cancel all running and pending tasks."""
        ...

    def get_task(self, task_id: str) -> TaskHandle[Any] | None:
        """Retrieve task handle by ID."""
        ...

    @property
    def active_tasks(self) -> tuple[TaskHandle[Any], ...]:
        """Tuple of active running and pending tasks."""
        ...

    def recent_tasks(self, limit: int = 50) -> tuple[TaskHandle[Any], ...]:
        """Tuple of recent tasks including finished, failed and cancelled."""
        ...

    def clear_history(self) -> None:
        """Clear finished, failed and cancelled tasks from history."""
        ...


__all__ = [
    "CancellationToken",
    "TaskCancelledError",
    "TaskHandle",
    "TaskManagerProtocol",
    "TaskPriority",
    "TaskProgress",
    "TaskStatus",
]
