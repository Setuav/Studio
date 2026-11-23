"""Unit tests for Centralized Background Task Manager."""

from __future__ import annotations

import time
import unittest

from PySide6.QtCore import QCoreApplication

from setuav_studio.api import StudioEvents
from setuav_studio.api.api import StudioAPI
from setuav_studio.task.manager import (
    CancellationToken,
    TaskCancelledError,
    TaskHandleImpl,
    TaskPriority,
    TaskStatus,
)
from setuav_studio.ui.dialog.task_manager import TaskManagerDialog
from tests._common import get_qapp


def _wait_for_task(handle: TaskHandleImpl, timeout_s: float = 3.0) -> None:
    start = time.time()
    while handle.status in (TaskStatus.PENDING, TaskStatus.RUNNING) and (
        time.time() - start < timeout_s
    ):
        QCoreApplication.processEvents()
        time.sleep(0.005)
    QCoreApplication.processEvents()


def _process_events(duration_s: float) -> None:
    end = time.time() + duration_s
    while time.time() < end:
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
        _process_events(0.05)

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

    def test_task_manager_dialog(self) -> None:
        dlg = TaskManagerDialog(self.api)
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.windowTitle(), "Task Manager")

        handle = self.tm.submit(name="Dialog Test Task", target=lambda token: 100)
        _wait_for_task(handle)
        dlg._refresh_all()

        recent = self.tm.recent_tasks()
        self.assertIn(handle.id, [h.id for h in recent])
        dlg.close()

    def test_task_manager_dialog_cancel_button_tracks_shifted_rows(self) -> None:
        import threading

        from PySide6.QtWidgets import QToolButton

        gate_first = threading.Event()
        gate_second = threading.Event()

        def wait_second(token: CancellationToken) -> None:
            while not gate_second.wait(0.02):
                token.check_cancelled()

        try:
            first = self.tm.submit(name="First Task", target=lambda _t: gate_first.wait(5.0))
            second = self.tm.submit(name="Second Task", target=wait_second)
            dlg = TaskManagerDialog(self.api)
            dlg._refresh_all()
            self.assertEqual(dlg._active_table.rowCount(), 2)

            # Finish first task so second task shifts into row 0.
            gate_first.set()
            _wait_for_task(first)
            dlg._refresh_all()
            self.assertEqual(dlg._active_table.rowCount(), 1)

            btn = dlg._active_table.cellWidget(0, 4)
            assert isinstance(btn, QToolButton)
            btn.click()
            self.assertTrue(second.is_cancelled)
            dlg.close()
        finally:
            gate_first.set()
            gate_second.set()

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

    def test_completed_task_releases_callbacks(self) -> None:
        import gc
        import weakref

        class _Owner:
            def on_done(self, _res: object) -> None:
                pass

        owner = _Owner()
        ref = weakref.ref(owner)
        handle = self.tm.submit(
            name="Cleanup Test",
            target=lambda _token: 1,
            on_finished=owner.on_done,
        )
        _wait_for_task(handle)
        del owner
        gc.collect()
        self.assertIsNone(ref())

    def test_cancel_before_queued_finished_signal_transitions_to_cancelled(self) -> None:
        import threading

        finished: list[object] = []
        cancelled: list[bool] = []
        done = threading.Event()

        def fast_work(_token: CancellationToken) -> int:
            done.set()
            return 99

        handle = self.tm.submit(
            name="Cancel Race Task",
            target=fast_work,
            on_finished=finished.append,
            on_cancelled=lambda: cancelled.append(True),
        )
        # Wait until worker finishes and queues finished signal, without pumping Qt events.
        self.assertTrue(done.wait(5.0))
        self.assertTrue(self.tm.thread_pool.waitForDone(5000))
        # Cancel on UI thread before queued finished slot executes.
        self.assertTrue(handle.cancel())
        _wait_for_task(handle)

        self.assertEqual(handle.status, TaskStatus.CANCELLED)
        self.assertEqual(finished, [])
        self.assertEqual(cancelled, [True])

    def test_task_manager_dialog_disconnects_signals_on_delete(self) -> None:
        from PySide6.QtCore import QEvent

        dlg = TaskManagerDialog(self.api)
        dlg.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QCoreApplication.processEvents()

        handle = self.tm.submit(name="After Dialog Deleted", target=lambda _t: "ok")
        _wait_for_task(handle)
        self.assertEqual(handle.status, TaskStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
