import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from setuav_studio.api import StudioAPI
from setuav_studio.project import create_project
from setuav_studio.solver import AbstractSolver, AnalysisResult, SolverConfig, SolverStatus


class AsyncDummySolver(AbstractSolver):
    """Dummy solver for testing asynchronous execution."""

    def run(self) -> AnalysisResult:
        if self.is_cancel_requested:
            self.status = SolverStatus.CANCELLED
            return AnalysisResult(
                solver_id=self.config.solver_id,
                config=self.config,
                status=SolverStatus.CANCELLED,
            )

        self.status = SolverStatus.COMPLETED
        return AnalysisResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            metrics={"lift": 250.0},
        )


class FailingSolver(AbstractSolver):
    """Solver that raises an exception during execution."""

    def run(self) -> AnalysisResult:
        raise ValueError("Computation failed due to convergence error")


class TestSolverRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project.suav"
        self.api = StudioAPI()
        self.api.current_project = create_project(self.project_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_register_and_run_solver_async(self) -> None:
        self.api.register_solver("async_dummy", AsyncDummySolver)
        solver_cls = self.api.solvers.get_solver_class("async_dummy")
        self.assertIs(solver_cls, AsyncDummySolver)

        config = SolverConfig(solver_id="async_dummy", name="Async Run 1")
        solver = AsyncDummySolver(config)

        completed_results: list[AnalysisResult] = []

        def _on_complete(res: AnalysisResult) -> None:
            completed_results.append(res)

        handle = self.api.run_solver(solver, on_complete=_on_complete)
        self.assertIsNotNone(handle)

        # Process Qt event loop until task finishes
        for _ in range(50):
            QApplication.processEvents()
            if completed_results:
                break

        self.assertEqual(len(completed_results), 1)
        res = completed_results[0]
        self.assertEqual(res.status, SolverStatus.COMPLETED)
        self.assertEqual(res.metrics["lift"], 250.0)

        # Verify automatic registration in current_project
        stored = self.api.get_analysis_result(res.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.id, res.id)

    def test_run_failing_solver(self) -> None:
        config = SolverConfig(solver_id="failing", name="Failing Run")
        solver = FailingSolver(config)

        completed_results: list[AnalysisResult] = []

        def _on_complete(res: AnalysisResult) -> None:
            completed_results.append(res)

        self.api.run_solver(solver, on_complete=_on_complete)

        for _ in range(50):
            QApplication.processEvents()
            if completed_results:
                break

        self.assertEqual(len(completed_results), 1)
        res = completed_results[0]
        self.assertEqual(res.status, SolverStatus.FAILED)
        self.assertIn("Computation failed", str(res.error_message))


if __name__ == "__main__":
    unittest.main()
