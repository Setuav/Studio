"""Unit tests for Centralized Background Task Manager."""

import time
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from setuav_studio.api.api import StudioAPI
from setuav_studio.task.manager import (
    CancellationToken,
    TaskCancelledError,
    TaskStatus,
)
from setuav_studio_sdk.events import StudioEvents


class TestTaskManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.tm = self.api.tasks

    def tearDown(self) -> None:
        self.tm.cancel_all()
        self.tm.thread_pool.waitForDone(1000)

    def test_task_success_execution(self) -> None:
        results = []
        progress_events = []

        def work(token: CancellationToken) -> int:
            token.report_progress(1, 2, "Step 1")
            time.sleep(0.01)
            token.report_progress(2, 2, "Step 2")
            return 42

        handle = self.tm.submit(
            name="Test Success",
            target=work,
            on_finished=lambda res: results.append(res),
            on_progress=lambda p: progress_events.append(p),
        )

        self.assertEqual(handle.name, "Test Success")
        self.tm.thread_pool.waitForDone(2000)
        QCoreApplication.processEvents()

        self.assertEqual(handle.status, TaskStatus.SUCCESS)
        self.assertEqual(results, [42])
        self.assertGreaterEqual(len(progress_events), 2)
        self.assertEqual(progress_events[-1].current, 2)
        self.assertEqual(progress_events[-1].percentage, 100.0)

    def test_task_error_handling(self) -> None:
        errors = []

        def failing_work(token: CancellationToken) -> None:
            raise ValueError("Computation blew up")

        handle = self.tm.submit(
            name="Test Failure",
            target=failing_work,
            on_error=lambda err: errors.append(err),
        )

        self.tm.thread_pool.waitForDone(2000)
        QCoreApplication.processEvents()

        self.assertEqual(handle.status, TaskStatus.ERROR)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertEqual(str(errors[0]), "Computation blew up")

    def test_task_cancellation_during_run(self) -> None:
        cancelled_called = []

        def long_loop(token: CancellationToken) -> int:
            count = 0
            for _ in range(50):
                if token.is_cancelled:
                    raise TaskCancelledError("Aborted")
                time.sleep(0.01)
                count += 1
            return count

        handle = self.tm.submit(
            name="Long Task",
            target=long_loop,
            on_cancelled=lambda: cancelled_called.append(True),
        )

        time.sleep(0.02)
        self.assertTrue(handle.cancel())
        self.tm.thread_pool.waitForDone(2000)
        QCoreApplication.processEvents()

        self.assertEqual(handle.status, TaskStatus.CANCELLED)
        self.assertEqual(cancelled_called, [True])

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

        self.tm.submit(name="Event Task", target=simple_work)
        self.tm.thread_pool.waitForDone(2000)
        QCoreApplication.processEvents()

        event_names = [e[0] for e in events]
        self.assertIn("started", event_names)
        self.assertIn("finished", event_names)


if __name__ == "__main__":
    unittest.main()
