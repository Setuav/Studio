import tempfile
import unittest
from pathlib import Path

from setuav_studio.project import create_project, open_project, save_project
from setuav_studio.solver import AnalysisResult, SolverConfig, SolverStatus


class TestSolverProjectIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project.suav"
        self.project = create_project(self.project_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_get_remove_analysis_result(self) -> None:
        config = SolverConfig(
            solver_id="aero_vlm",
            name="Alpha Sweep",
            parameters={"alpha": 5.0},
        )
        result = AnalysisResult(
            solver_id="aero_vlm",
            config=config,
            name="VLM Result 1",
            status=SolverStatus.COMPLETED,
            metrics={"cl": 0.65, "cd": 0.025},
            tables={"polar": [{"alpha": 5.0, "cl": 0.65}]},
        )

        self.assertEqual(len(self.project.analysis_results), 0)
        self.project.add_analysis_result(result)
        self.assertTrue(self.project.modified)
        self.assertEqual(len(self.project.analysis_results), 1)

        fetched = self.project.get_analysis_result(result.id)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.id, result.id)
        self.assertEqual(fetched.name, "VLM Result 1")
        self.assertEqual(fetched.metrics["cl"], 0.65)

        # Test removal
        removed = self.project.remove_analysis_result(result.id)
        self.assertTrue(removed)
        self.assertEqual(len(self.project.analysis_results), 0)
        self.assertIsNone(self.project.get_analysis_result(result.id))

    def test_save_and_open_project_with_analysis_results(self) -> None:
        config1 = SolverConfig(solver_id="aero_vlm", name="Run 1", parameters={"alpha": 2.0})
        result1 = AnalysisResult(
            solver_id="aero_vlm",
            config=config1,
            name="Run 1 Result",
            metrics={"cl": 0.4},
        )
        config2 = SolverConfig(solver_id="thrust_calc", name="Run 2", parameters={"rpm": 3000})
        result2 = AnalysisResult(
            solver_id="thrust_calc",
            config=config2,
            name="Run 2 Result",
            metrics={"thrust": 45.0},
        )

        self.project.add_analysis_result(result1)
        self.project.add_analysis_result(result2)

        # Save project
        save_project(self.project)
        self.assertTrue(self.project_path.is_file())

        # Re-open project
        reopened = open_project(self.project_path)
        self.assertEqual(len(reopened.analysis_results), 2)

        res1_reopened = reopened.get_analysis_result(result1.id)
        self.assertIsNotNone(res1_reopened)
        assert res1_reopened is not None
        self.assertEqual(res1_reopened.name, "Run 1 Result")
        self.assertEqual(res1_reopened.metrics["cl"], 0.4)

        res2_reopened = reopened.get_analysis_result(result2.id)
        self.assertIsNotNone(res2_reopened)
        assert res2_reopened is not None
        self.assertEqual(res2_reopened.name, "Run 2 Result")
        self.assertEqual(res2_reopened.metrics["thrust"], 45.0)


if __name__ == "__main__":
    unittest.main()
