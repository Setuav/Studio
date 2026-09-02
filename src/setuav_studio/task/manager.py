"""Centralized background task manager with thread pool, progress, and cancellation."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from setuav_studio_sdk.events import StudioEvents
from setuav_studio_sdk.tasks import (
    CancellationToken,
    TaskCancelledError,
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

    started = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(object)
    error = Signal(object)
    cancelled = Signal()


class TaskHandleImpl(Generic[T]):
    """Concrete implementation of TaskHandle."""

    def __init__(
        self,
        task_id: str,
        name: str,
        manager: TaskManager,
        token: _TaskCancellationToken,
    ) -> None:
        self._id = task_id
        self._name = name
        self._manager = manager
        self._token = token
        self._status = TaskStatus.PENDING

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def is_cancelled(self) -> bool:
        return self._token.is_cancelled

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
            self.signals.cancelled.emit()
            return

        self.signals.started.emit(self._task_id)
        try:
            result = self._target(self._token)
            if self._token.is_cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.finished.emit(result)
        except TaskCancelledError:
            self.signals.cancelled.emit()
        except Exception as exc:
            if self._token.is_cancelled:
                self.signals.cancelled.emit()
            else:
                logger.exception("Task '%s' (%s) failed: %s", self._name, self._task_id, exc)
                self.signals.error.emit(exc)


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
        self._lock = threading.Lock()

    @property
    def thread_pool(self) -> QThreadPool:
        return self._thread_pool

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

    def submit(
        self,
        name: str,
        target: Callable[[CancellationToken], T],
        *,
        on_finished: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_progress: Callable[[TaskProgress], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
    ) -> TaskHandleImpl[T]:
        """Submit a background callable to the centralized thread pool."""
        task_id = str(uuid.uuid4())[:8]
        token = _TaskCancellationToken(task_id, self)
        handle = TaskHandleImpl[T](task_id, name, self, token)
        signals = _TaskSignals()

        with self._lock:
            self._handles[task_id] = handle
            self._tokens[task_id] = token
            self._signals_map[task_id] = signals

        # Wire Qt signals to slots on main UI thread
        signals.started.connect(lambda tid: self._on_task_started(tid))
        signals.progress.connect(
            lambda c, t, m, tid=task_id, cb=on_progress: self._on_task_progress(tid, c, t, m, cb)
        )
        signals.finished.connect(
            lambda res, tid=task_id, cb=on_finished: self._on_task_finished(tid, res, cb)
        )
        signals.error.connect(
            lambda exc, tid=task_id, cb=on_error: self._on_task_error(tid, exc, cb)
        )
        signals.cancelled.connect(
            lambda tid=task_id, cb=on_cancelled: self._on_task_cancelled(tid, cb)
        )

        runnable = _TaskRunnable[T](task_id, name, target, token, signals)
        self._thread_pool.start(runnable)
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
            signals.progress.emit(current, total, message)

    def _on_task_started(self, task_id: str) -> None:
        handle = self._handles.get(task_id)
        if handle is not None:
            handle._status = TaskStatus.RUNNING
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
        callback: Callable[[TaskProgress], None] | None,
    ) -> None:
        handle = self._handles.get(task_id)
        if handle is None or handle.status != TaskStatus.RUNNING:
            return
        prog = TaskProgress(current=current, total=total, message=message)
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
        if callback is not None:
            callback(prog)

    def _on_task_finished(
        self,
        task_id: str,
        result: Any,
        callback: Callable[[Any], None] | None,
    ) -> None:
        handle = self._handles.get(task_id)
        if handle is not None:
            handle._status = TaskStatus.SUCCESS
            self.task_finished.emit(task_id, result)
            self._publish_event(
                StudioEvents.TASK_FINISHED,
                {"task_id": task_id, "name": handle.name, "result": result},
            )
            self.tasks_count_changed.emit(len(self.active_tasks))
        if callback is not None:
            callback(result)
        self._cleanup_task(task_id)

    def _on_task_error(
        self,
        task_id: str,
        exc: Exception,
        callback: Callable[[Exception], None] | None,
    ) -> None:
        handle = self._handles.get(task_id)
        if handle is not None:
            handle._status = TaskStatus.ERROR
            self.task_error.emit(task_id, exc)
            self._publish_event(
                StudioEvents.TASK_ERROR,
                {"task_id": task_id, "name": handle.name, "error": str(exc)},
            )
            self.tasks_count_changed.emit(len(self.active_tasks))
        if callback is not None:
            callback(exc)
        self._cleanup_task(task_id)

    def _on_task_cancelled(
        self,
        task_id: str,
        callback: Callable[[], None] | None,
    ) -> None:
        handle = self._handles.get(task_id)
        if handle is not None:
            handle._status = TaskStatus.CANCELLED
            self.task_cancelled.emit(task_id)
            self._publish_event(
                StudioEvents.TASK_CANCELLED,
                {"task_id": task_id, "name": handle.name},
            )
            self.tasks_count_changed.emit(len(self.active_tasks))
        if callback is not None:
            callback()
        self._cleanup_task(task_id)

    def _cleanup_task(self, task_id: str) -> None:
        # Keep handle for query, remove signals
        self._signals_map.pop(task_id, None)

    def _publish_event(self, topic: str | StudioEvents, payload: Any) -> None:
        if self._api is not None:
            if hasattr(self._api, "publish"):
                self._api.publish(str(topic), payload)
            elif hasattr(self._api, "publish_event"):
                self._api.publish_event(str(topic), payload)


__all__ = [
    "TaskCancelledError",
    "TaskHandleImpl",
    "TaskManager",
    "TaskProgress",
    "TaskStatus",
]
