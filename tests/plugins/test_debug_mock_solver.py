"""Unit tests for Debug Plugin MockGeneratorSolver, cancellation, and pairwise plots."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from plugins.debug import DebugPlugin
from plugins.debug.solver import SOLVER_ID_MOCK_GENERATOR, MockGeneratorSolver
from setuav_studio.api import StudioAPI
from setuav_studio.project import create_project
from setuav_studio.solver.base import SolverConfig, SolverStatus
from setuav_studio.task.types import TaskCancelledError


class TestDebugMockSolver(unittest.TestCase):
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

    def test_mock_solver_generation_even_columns(self) -> None:
        """Test mock data generation with 6 columns and pairwise plots."""
        config = SolverConfig(
            solver_id=SOLVER_ID_MOCK_GENERATOR,
            name="Mock Test Run",
            parameters={"duration": 0.0, "rows": 25, "columns": 6},
        )
        solver = MockGeneratorSolver(config)
        result = solver.run()

        self.assertEqual(result.status, SolverStatus.COMPLETED)
        self.assertIn("mock_data", result.tables)
        tbl = result.tables["mock_data"]

        # Check rows count and columns count
        self.assertEqual(tbl.row_count(), 25)
        self.assertEqual(len(tbl.columns), 6)

        # Check unique units and quantity IDs
        units = [c.unit for c in tbl.columns]
        self.assertEqual(len(units), len(set(units)), "Each column must have a distinct unit")

        # 6 columns -> exactly 3 pairwise plots
        self.assertEqual(len(result.plots), 3)
        plot_list = list(result.plots.values())

        # Plot 0: Pair (0, 1) -> Airspeed vs Time
        self.assertEqual(plot_list[0].x_column, "time")
        self.assertEqual(plot_list[0].series[0].y_column, "airspeed")

        # Plot 1: Pair (2, 3) -> Lift Force vs Angle of Attack
        self.assertEqual(plot_list[1].x_column, "aoa")
        self.assertEqual(plot_list[1].series[0].y_column, "lift")

        # Plot 2: Pair (4, 5) -> Shaft Power vs Dynamic Pressure
        self.assertEqual(plot_list[2].x_column, "dyn_pressure")
        self.assertEqual(plot_list[2].series[0].y_column, "shaft_power")

        # Check summary items
        self.assertIn("rows_generated", result.summary)
        self.assertEqual(result.summary["rows_generated"].value, 25)
        self.assertIn("columns_generated", result.summary)
        self.assertEqual(result.summary["columns_generated"].value, 6)

    def test_mock_solver_minimum_four_columns_enforced(self) -> None:
        """Verify solver enforces at least 4 columns even if fewer are requested."""
        config = SolverConfig(
            solver_id=SOLVER_ID_MOCK_GENERATOR,
            name="Min Cols Run",
            parameters={"duration": 0.0, "rows": 10, "columns": 2},
        )
        solver = MockGeneratorSolver(config)
        result = solver.run()

        self.assertEqual(result.status, SolverStatus.COMPLETED)
        tbl = result.tables["mock_data"]
        self.assertGreaterEqual(len(tbl.columns), 4)
        self.assertEqual(len(result.plots), 2)

    def test_mock_solver_odd_columns_pairwise_wrapping(self) -> None:
        """Verify odd number of columns pairs the remaining column with column 0."""
        config = SolverConfig(
            solver_id=SOLVER_ID_MOCK_GENERATOR,
            name="Odd Cols Run",
            parameters={"duration": 0.0, "rows": 15, "columns": 5},
        )
        solver = MockGeneratorSolver(config)
        result = solver.run()

        self.assertEqual(len(result.tables["mock_data"].columns), 5)
        # 5 columns -> 2 consecutive pairs + 1 wrap pair = 3 plots
        self.assertEqual(len(result.plots), 3)
        plot_list = list(result.plots.values())
        self.assertEqual(plot_list[0].x_column, "time")
        self.assertEqual(plot_list[0].series[0].y_column, "airspeed")
        self.assertEqual(plot_list[1].x_column, "aoa")
        self.assertEqual(plot_list[1].series[0].y_column, "lift")
        self.assertEqual(plot_list[2].x_column, "time")
        self.assertEqual(plot_list[2].series[0].y_column, "dyn_pressure")

    def test_mock_solver_immediate_cancellation(self) -> None:
        """Verify solver cancels immediately if cancellation was already requested."""
        config = SolverConfig(
            solver_id=SOLVER_ID_MOCK_GENERATOR,
            name="Cancelled Run",
            parameters={"duration": 5.0, "rows": 50, "columns": 4},
        )
        solver = MockGeneratorSolver(config)
        solver.cancel()

        with self.assertRaises(TaskCancelledError):
            solver.run()

        self.assertEqual(solver.status, SolverStatus.CANCELLED)

    def test_mock_solver_async_run_and_project_integration(self) -> None:
        """Verify asynchronous execution through StudioAPI and TaskManager."""
        self.api.register_solver(SOLVER_ID_MOCK_GENERATOR, MockGeneratorSolver)

        config = SolverConfig(
            solver_id=SOLVER_ID_MOCK_GENERATOR,
            name="Async Mock Analysis",
            parameters={"duration": 0.05, "rows": 30, "columns": 4},
        )
        solver = MockGeneratorSolver(config)

        completed_results = []
        self.api.run_solver(solver, on_complete=lambda res: completed_results.append(res))

        for _ in range(50):
            QApplication.processEvents()
            if completed_results:
                break
            time.sleep(0.01)

        self.assertEqual(len(completed_results), 1)
        res = completed_results[0]
        self.assertEqual(res.status, SolverStatus.COMPLETED)
        self.assertIn("mock_data", res.tables)

        # Confirm result stored in current project
        stored = self.api.get_analysis_result(res.id)
        self.assertIsNotNone(stored)

    def test_mock_solver_async_cancellation(self) -> None:
        """Verify cancelling task during async execution cleanly halts solver."""
        self.api.register_solver(SOLVER_ID_MOCK_GENERATOR, MockGeneratorSolver)

        config = SolverConfig(
            solver_id=SOLVER_ID_MOCK_GENERATOR,
            name="Async Cancel Mock",
            parameters={"duration": 2.0, "rows": 100, "columns": 4},
        )
        solver = MockGeneratorSolver(config)

        cancelled_called = []
        handle = self.api.run_solver(
            solver,
            on_cancelled=lambda: cancelled_called.append(True),
        )

        # Allow task to start running
        for _ in range(5):
            QApplication.processEvents()
            time.sleep(0.01)

        # Cancel task
        self.api.tasks.cancel(handle.id)

        for _ in range(50):
            QApplication.processEvents()
            if cancelled_called:
                break
            time.sleep(0.01)

        self.assertTrue(len(cancelled_called) > 0)
        self.assertEqual(solver.status, SolverStatus.CANCELLED)

    def test_debug_plugin_lifecycle_and_actions(self) -> None:
        """Verify DebugPlugin activates solvers, tools, and creates analysis config."""
        plugin = DebugPlugin()
        plugin.activate(self.api)

        # Verify solver registration
        self.assertIs(
            self.api.solvers.get_solver_class(SOLVER_ID_MOCK_GENERATOR),
            MockGeneratorSolver,
        )

        # Test adding mock analysis config
        plugin._add_mock_analysis_config()
        configs = self.api.get_analysis_configs()
        self.assertEqual(len(configs), 1)
        cfg = next(iter(configs.values()))
        self.assertEqual(cfg.solver_id, SOLVER_ID_MOCK_GENERATOR)
        self.assertEqual(cfg.parameters.get("columns"), 4)
        self.assertEqual(cfg.parameters.get("rows"), 50)
        self.assertEqual(cfg.parameters.get("duration"), 3.0)

        # Test deactivate cleanly cleans up
        plugin.deactivate(self.api)
        self.assertIsNone(self.api.solvers.get_solver_class(SOLVER_ID_MOCK_GENERATOR))


if __name__ == "__main__":
    unittest.main()
