"""Data types and protocols for background task management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
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
    def status(self) -> TaskStatus:
        """Current lifecycle status."""
        ...

    @property
    def is_cancelled(self) -> bool:
        """True if cancellation was requested."""
        ...

    def cancel(self) -> None:
        """Request cancellation."""
        ...


class TaskManagerProtocol(Protocol):
    """Central background task manager contract exposed to plugins."""

    def submit(
        self,
        name: str,
        target: Callable[[CancellationToken], T],
        *,
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

    @property
    def active_tasks(self) -> tuple[TaskHandle[Any], ...]:
        """Tuple of active running and pending tasks."""
        ...


__all__ = [
    "CancellationToken",
    "TaskCancelledError",
    "TaskHandle",
    "TaskManagerProtocol",
    "TaskProgress",
    "TaskStatus",
]
