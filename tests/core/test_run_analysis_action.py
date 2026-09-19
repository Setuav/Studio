import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from setuav_studio.api import StudioAPI
from setuav_studio.model.analysis_config import AnalysisConfig
from setuav_studio.project import create_project
from setuav_studio.solver import AbstractSolver, AnalysisResult, SolverStatus
from setuav_studio.ui.shell.native_registrations import (
    _on_run_analysis_triggered,
    register_native_contributions,
)


class MockNativeSolver(AbstractSolver):
    def run(self) -> AnalysisResult:
        return AnalysisResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            metrics={"cl": 0.5},
        )


class TestRunAnalysisAction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project.suav"
        self.api = StudioAPI()
        self.api.current_project = create_project(self.project_path)
        self.status_messages: list[tuple[str, str]] = []
        self.api._host.bind_status_handler(
            lambda msg, cat, timeout: self.status_messages.append((msg, cat))
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_native_registrations_includes_run_analysis_action(self) -> None:
        register_native_contributions(self.api)
        # Check action registration
        self.assertIn("Run Analysis", [a.title for a in self.api._pending_actions])
        self.assertIn(
            "org.setuav.studio.toolbar.run_analysis",
            [t.id for t in self.api._pending_toolbar_items],
        )

    def test_trigger_run_analysis_no_configs(self) -> None:
        _on_run_analysis_triggered(self.api)
        self.assertTrue(
            any("No analysis configuration available" in msg for msg, cat in self.status_messages)
        )

    def test_trigger_run_analysis_unregistered_solver(self) -> None:
        config = AnalysisConfig(solver_id="unknown_solver", name="Test Config")
        self.api.add_analysis_config(config)

        _on_run_analysis_triggered(self.api)
        self.assertTrue(
            any("No registered solver found" in msg for msg, cat in self.status_messages)
        )

    def test_trigger_run_analysis_success(self) -> None:
        self.api.register_solver("mock_native", MockNativeSolver)
        config = AnalysisConfig(solver_id="mock_native", name="Mock Run")
        self.api.add_analysis_config(config)

        _on_run_analysis_triggered(self.api)

        # Process Qt events until async execution finishes
        for _ in range(50):
            QApplication.processEvents()

        results = self.api.get_analysis_results()
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
