"""Unit tests for Centralized Background Task Manager."""

from __future__ import annotations

import time
import unittest

from PySide6.QtCore import QCoreApplication

from setuav_studio.api.api import StudioAPI
from setuav_studio.task.manager import (
    CancellationToken,
    TaskCancelledError,
    TaskHandleImpl,
    TaskPriority,
    TaskStatus,
)
from setuav_studio.ui.task_monitor import TaskMonitorDialog
from setuav_studio_sdk.events import StudioEvents
from tests._common import get_qapp


def _wait_for_task(handle: TaskHandleImpl, timeout_s: float = 3.0) -> None:
    start = time.time()
    while handle.status in (TaskStatus.PENDING, TaskStatus.RUNNING) and (time.time() - start < timeout_s):
        QCoreApplication.processEvents()
        time.sleep(0.005)
    QCoreApplication.processEvents()


class TestTaskManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.tm = self.api.tasks

    def tearDown(self) -> None:
        self.tm.cancel_all()
        _wait_for_task(TaskHandleImpl("dummy", "dummy", self.tm, None), timeout_s=0.05)  # type: ignore

    def test_task_success_execution(self) -> None:
        results = []
        progress_events = []

        def work(token: CancellationToken) -> int:
            token.report_progress(1, 2, "Step 1")
            token.report_progress(2, 2, "Step 2")
            return 42

        handle = self.tm.submit(
            name="Test Success",
            target=work,
            on_finished=lambda res: results.append(res),
            on_progress=lambda p: progress_events.append(p),
        )

        _wait_for_task(handle)

        self.assertEqual(handle.status, TaskStatus.SUCCESS)
        self.assertEqual(results, [42])
        self.assertEqual(handle.result, 42)
        self.assertGreaterEqual(len(progress_events), 2)
        self.assertEqual(progress_events[-1].current, 2)
        self.assertEqual(progress_events[-1].percentage, 100.0)
        self.assertIsNotNone(handle.started_at)
        self.assertIsNotNone(handle.completed_at)
        self.assertGreaterEqual(handle.duration_seconds, 0.0)

    def test_task_error_handling(self) -> None:
        errors = []

        def failing_work(token: CancellationToken) -> None:
            raise ValueError("Computation blew up")

        handle = self.tm.submit(
            name="Test Failure",
            target=failing_work,
            on_error=lambda err: errors.append(err),
        )

        _wait_for_task(handle)

        self.assertEqual(handle.status, TaskStatus.ERROR)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertEqual(str(errors[0]), "Computation blew up")
        self.assertIsInstance(handle.error, ValueError)

    def test_task_cancellation_during_run(self) -> None:
        cancelled_called = []

        def long_loop(token: CancellationToken) -> int:
            count = 0
            for _ in range(500):
                if token.is_cancelled:
                    raise TaskCancelledError("Aborted")
                time.sleep(0.005)
                count += 1
            return count

        handle = self.tm.submit(
            name="Long Task",
            target=long_loop,
            on_cancelled=lambda: cancelled_called.append(True),
        )

        # Give it a couple ms to start, then cancel
        time.sleep(0.02)
        handle.cancel()
        _wait_for_task(handle)

        self.assertEqual(handle.status, TaskStatus.CANCELLED)
        self.assertEqual(cancelled_called, [True])

    def test_task_priority_and_timestamps(self) -> None:
        handle = self.tm.submit(
            name="High Priority Task",
            target=lambda token: "done",
            priority=TaskPriority.HIGH,
        )
        self.assertEqual(handle.priority, TaskPriority.HIGH)
        self.assertGreater(handle.created_at, 0)
        _wait_for_task(handle)
        self.assertEqual(handle.status, TaskStatus.SUCCESS)

    def test_task_history_and_cleanup(self) -> None:
        self.tm.clear_history()
        h1 = self.tm.submit(name="Task 1", target=lambda token: 1)
        h2 = self.tm.submit(name="Task 2", target=lambda token: 2)

        _wait_for_task(h1)
        _wait_for_task(h2)

        recent = self.tm.recent_tasks()
        self.assertGreaterEqual(len(recent), 2)
        self.assertEqual(recent[0].id, h2.id)
        self.assertEqual(recent[1].id, h1.id)

        self.tm.clear_history()
        self.assertEqual(len(self.tm.recent_tasks()), 0)

    def test_max_workers_property(self) -> None:
        original = self.tm.max_workers
        self.tm.max_workers = 8
        self.assertEqual(self.tm.max_workers, 8)
        self.tm.max_workers = original

    def test_task_monitor_dialog(self) -> None:
        dlg = TaskMonitorDialog(self.api)
        self.assertIsNotNone(dlg)

        handle = self.tm.submit(name="Dialog Test Task", target=lambda token: 100)
        _wait_for_task(handle)
        dlg._refresh_all()

        recent = self.tm.recent_tasks()
        self.assertIn(handle.id, [h.id for h in recent])
        dlg.close()

    def test_task_events_published_to_bus(self) -> None:
        events = []
        self.api.subscribe(
            StudioEvents.TASK_STARTED,
            lambda p: events.append(("started", p)),
        )
        self.api.subscribe(
            StudioEvents.TASK_FINISHED,
            lambda p: events.append(("finished", p)),
        )

        def simple_work(token: CancellationToken) -> str:
            return "done"

        handle = self.tm.submit(name="Event Task", target=simple_work)
        _wait_for_task(handle)

        event_names = [e[0] for e in events]
        self.assertIn("started", event_names)
        self.assertIn("finished", event_names)


if __name__ == "__main__":
    unittest.main()
