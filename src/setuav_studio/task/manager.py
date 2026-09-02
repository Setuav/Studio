"""Centralized background task manager with thread pool, progress, cancellation, priority and history."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from setuav_studio_sdk.events import StudioEvents
from setuav_studio_sdk.tasks import (
    CancellationToken,
    TaskCancelledError,
    TaskPriority,
    TaskProgress,
    TaskStatus,
)

if TYPE_CHECKING:
    from ..api.api import StudioAPI

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _TaskCancellationToken(CancellationToken):
    """Concrete thread-safe cancellation token passed to running tasks."""

    def __init__(self, task_id: str, manager: TaskManager) -> None:
        self._task_id = task_id
        self._manager = manager
        self._cancel_event = threading.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.is_cancelled:
            raise TaskCancelledError(f"Task {self._task_id} cancelled.")

    def cancel(self) -> None:
        self._cancel_event.set()

    def report_progress(self, current: int, total: int, message: str = "") -> None:
        self._manager._report_task_progress(self._task_id, current, total, message)


class _TaskSignals(QObject):
    """Signals emitted across threads for a specific task."""

    started = Signal(str)  # task_id
    progress = Signal(str, int, int, str)  # (task_id, current, total, message)
    finished = Signal(str, object)  # (task_id, result)
    error = Signal(str, object)  # (task_id, exception)
    cancelled = Signal(str)  # task_id


class TaskHandleImpl(Generic[T]):
    """Concrete implementation of TaskHandle."""

    def __init__(
        self,
        task_id: str,
        name: str,
        manager: TaskManager,
        token: _TaskCancellationToken,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> None:
        self._id = task_id
        self._name = name
        self._manager = manager
        self._token = token
        self._priority = priority
        self._status = TaskStatus.PENDING
        self._created_at = time.time()
        self._started_at: float | None = None
        self._completed_at: float | None = None
        self._progress: TaskProgress | None = None
        self._result: T | None = None
        self._error: Exception | None = None

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> TaskPriority:
        return self._priority

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def is_cancelled(self) -> bool:
        return self._token.is_cancelled

    @property
    def created_at(self) -> float:
        return self._created_at

    @property
    def started_at(self) -> float | None:
        return self._started_at

    @property
    def completed_at(self) -> float | None:
        return self._completed_at

    @property
    def duration_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        end_time = self._completed_at if self._completed_at is not None else time.time()
        return max(0.0, end_time - self._started_at)

    @property
    def progress(self) -> TaskProgress | None:
        return self._progress

    @property
    def result(self) -> T | None:
        return self._result

    @property
    def error(self) -> Exception | None:
        return self._error

    def cancel(self) -> bool:
        return self._manager.cancel(self._id)


class _TaskRunnable(QRunnable, Generic[T]):
    """Runnable executing the task target in a background thread."""

    def __init__(
        self,
        task_id: str,
        name: str,
        target: Callable[[CancellationToken], T],
        token: _TaskCancellationToken,
        signals: _TaskSignals,
    ) -> None:
        super().__init__()
        self._task_id = task_id
        self._name = name
        self._target = target
        self._token = token
        self.signals = signals
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        if self._token.is_cancelled:
            self.signals.cancelled.emit(self._task_id)
            return

        self.signals.started.emit(self._task_id)
        try:
            result = self._target(self._token)
            if self._token.is_cancelled:
                self.signals.cancelled.emit(self._task_id)
            else:
                self.signals.finished.emit(self._task_id, result)
        except TaskCancelledError:
            self.signals.cancelled.emit(self._task_id)
        except Exception as exc:
            if self._token.is_cancelled:
                self.signals.cancelled.emit(self._task_id)
            else:
                logger.exception("Task '%s' (%s) failed: %s", self._name, self._task_id, exc)
                self.signals.error.emit(self._task_id, exc)


class TaskManager(QObject):
    """Central manager for executing, monitoring, and cancelling background jobs."""

    task_started = Signal(str, str)  # (task_id, name)
    task_progress = Signal(str, int, int, str)  # (task_id, current, total, message)
    task_finished = Signal(str, object)  # (task_id, result)
    task_cancelled = Signal(str)  # (task_id)
    task_error = Signal(str, object)  # (task_id, exception)
    tasks_count_changed = Signal(int)  # (active_task_count)

    def __init__(
        self,
        api: StudioAPI | None = None,
        thread_pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._handles: dict[str, TaskHandleImpl[Any]] = {}
        self._tokens: dict[str, _TaskCancellationToken] = {}
        self._signals_map: dict[str, _TaskSignals] = {}
        self._callbacks: dict[str, dict[str, Any]] = {}
        self._history_order: list[str] = []
        self._lock = threading.Lock()

    @property
    def thread_pool(self) -> QThreadPool:
        return self._thread_pool

    @property
    def max_workers(self) -> int:
        return self._thread_pool.maxThreadCount()

    @max_workers.setter
    def max_workers(self, count: int) -> None:
        if count > 0:
            self._thread_pool.setMaxThreadCount(count)

    @property
    def active_tasks(self) -> tuple[TaskHandleImpl[Any], ...]:
        with self._lock:
            return tuple(
                h
                for h in self._handles.values()
                if h.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
            )

    def get_task(self, task_id: str) -> TaskHandleImpl[Any] | None:
        with self._lock:
            return self._handles.get(task_id)

    def recent_tasks(self, limit: int = 50) -> tuple[TaskHandleImpl[Any], ...]:
        """Return recently submitted tasks, newest first."""
        with self._lock:
            ordered_ids = list(reversed(self._history_order))
            tasks: list[TaskHandleImpl[Any]] = []
            for tid in ordered_ids:
                h = self._handles.get(tid)
                if h is not None:
                    tasks.append(h)
                if len(tasks) >= limit:
                    break
            return tuple(tasks)

    def clear_history(self) -> None:
        """Remove completed, cancelled, and errored tasks from storage."""
        with self._lock:
            removable_ids = [
                tid
                for tid, h in self._handles.items()
                if h.status in (TaskStatus.SUCCESS, TaskStatus.CANCELLED, TaskStatus.ERROR)
            ]
            for tid in removable_ids:
                self._handles.pop(tid, None)
                self._tokens.pop(tid, None)
                self._signals_map.pop(tid, None)
                self._callbacks.pop(tid, None)
                if tid in self._history_order:
                    self._history_order.remove(tid)

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
    ) -> TaskHandleImpl[T]:
        """Submit a background callable to the centralized thread pool."""
        task_id = str(uuid.uuid4())[:8]
        token = _TaskCancellationToken(task_id, self)
        handle = TaskHandleImpl[T](task_id, name, self, token, priority)
        signals = _TaskSignals()

        with self._lock:
            self._handles[task_id] = handle
            self._tokens[task_id] = token
            self._signals_map[task_id] = signals
            self._callbacks[task_id] = {
                "finished": on_finished,
                "error": on_error,
                "progress": on_progress,
                "cancelled": on_cancelled,
            }
            self._history_order.append(task_id)

        # Wire Qt signals to slots on main UI thread
        signals.started.connect(self._on_task_started)
        signals.progress.connect(self._on_task_progress)
        signals.finished.connect(self._on_task_finished)
        signals.error.connect(self._on_task_error)
        signals.cancelled.connect(self._on_task_cancelled)

        runnable = _TaskRunnable[T](task_id, name, target, token, signals)
        self._thread_pool.start(runnable, priority.value)
        self.tasks_count_changed.emit(len(self.active_tasks))
        return handle

    def cancel(self, task_id: str) -> bool:
        """Request cancellation for a task by ID."""
        with self._lock:
            token = self._tokens.get(task_id)
            handle = self._handles.get(task_id)
            if token is None or handle is None:
                return False
            if handle.status in (TaskStatus.SUCCESS, TaskStatus.CANCELLED, TaskStatus.ERROR):
                return False
            token.cancel()
            return True

    def cancel_all(self) -> None:
        """Cancel all pending and running tasks."""
        with self._lock:
            active_ids = [
                tid
                for tid, h in self._handles.items()
                if h.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
            ]
        for tid in active_ids:
            self.cancel(tid)

    def _report_task_progress(self, task_id: str, current: int, total: int, message: str) -> None:
        signals = self._signals_map.get(task_id)
        if signals is not None:
            signals.progress.emit(task_id, current, total, message)

    def _on_task_started(self, task_id: str) -> None:
        handle = self._handles.get(task_id)
        if handle is not None and handle.status == TaskStatus.PENDING:
            handle._status = TaskStatus.RUNNING
            handle._started_at = time.time()
            self.task_started.emit(task_id, handle.name)
            self._publish_event(
                StudioEvents.TASK_STARTED,
                {"task_id": task_id, "name": handle.name},
            )
            self.tasks_count_changed.emit(len(self.active_tasks))

    def _on_task_progress(
        self,
        task_id: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        handle = self._handles.get(task_id)
        if handle is None or handle.status != TaskStatus.RUNNING:
            return
        prog = TaskProgress(current=current, total=total, message=message)
        handle._progress = prog
        self.task_progress.emit(task_id, current, total, message)
        self._publish_event(
            StudioEvents.TASK_PROGRESS,
            {
                "task_id": task_id,
                "name": handle.name,
                "current": current,
                "total": total,
                "message": message,
                "percent": prog.percentage,
            },
        )
        cb = self._callbacks.get(task_id, {}).get("progress")
        if cb is not None:
            cb(prog)

    def _on_task_finished(
        self,
        task_id: str,
        result: Any,
    ) -> None:
        handle = self._handles.get(task_id)
        if handle is not None and handle.status not in (TaskStatus.SUCCESS, TaskStatus.CANCELLED, TaskStatus.ERROR):
            handle._status = TaskStatus.SUCCESS
            handle._completed_at = time.time()
            handle._result = result
            self.task_finished.emit(task_id, result)
            self._publish_event(
                StudioEvents.TASK_FINISHED,
                {"task_id": task_id, "name": handle.name, "result": result},
            )
            self.tasks_count_changed.emit(len(self.active_tasks))
            cb = self._callbacks.get(task_id, {}).get("finished")
            if cb is not None:
                cb(result)
        self._cleanup_task(task_id)

    def _on_task_error(
        self,
        task_id: str,
        exc: Exception,
    ) -> None:
        handle = self._handles.get(task_id)
        if handle is not None and handle.status not in (TaskStatus.SUCCESS, TaskStatus.CANCELLED, TaskStatus.ERROR):
            handle._status = TaskStatus.ERROR
            handle._completed_at = time.time()
            handle._error = exc
            self.task_error.emit(task_id, exc)
            self._publish_event(
                StudioEvents.TASK_ERROR,
                {"task_id": task_id, "name": handle.name, "error": str(exc)},
            )
            self.tasks_count_changed.emit(len(self.active_tasks))
            cb = self._callbacks.get(task_id, {}).get("error")
            if cb is not None:
                cb(exc)
        self._cleanup_task(task_id)

    def _on_task_cancelled(
        self,
        task_id: str,
    ) -> None:
        handle = self._handles.get(task_id)
        if handle is not None and handle.status not in (TaskStatus.SUCCESS, TaskStatus.CANCELLED, TaskStatus.ERROR):
            handle._status = TaskStatus.CANCELLED
            handle._completed_at = time.time()
            self.task_cancelled.emit(task_id)
            self._publish_event(
                StudioEvents.TASK_CANCELLED,
                {"task_id": task_id, "name": handle.name},
            )
            self.tasks_count_changed.emit(len(self.active_tasks))
            cb = self._callbacks.get(task_id, {}).get("cancelled")
            if cb is not None:
                cb()
        self._cleanup_task(task_id)

    def _cleanup_task(self, task_id: str) -> None:
        # Retain handle in history, release transient Qt signals
        self._signals_map.pop(task_id, None)

    def _publish_event(self, topic: str | StudioEvents, payload: Any) -> None:
        if self._api is not None:
            if hasattr(self._api, "publish"):
                self._api.publish(str(topic), payload)
            elif hasattr(self._api, "publish_event"):
                self._api.publish_event(str(topic), payload)


__all__ = [
    "CancellationToken",
    "TaskCancelledError",
    "TaskHandleImpl",
    "TaskManager",
    "TaskPriority",
    "TaskProgress",
    "TaskStatus",
]
