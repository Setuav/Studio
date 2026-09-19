import unittest

from setuav_studio.solver import AbstractSolver, AnalysisResult, SolverConfig, SolverStatus


class DummySolver(AbstractSolver):
    """Concrete dummy solver for testing AbstractSolver contract."""

    def run(self) -> AnalysisResult:
        self.status = SolverStatus.RUNNING
        self.progress = 50.0

        if self.is_cancel_requested:
            self.status = SolverStatus.CANCELLED
            return AnalysisResult(
                solver_id=self.config.solver_id,
                config=self.config,
                status=SolverStatus.CANCELLED,
            )

        self.status = SolverStatus.COMPLETED
        self.progress = 100.0
        return AnalysisResult(
            solver_id=self.config.solver_id,
            config=self.config,
            status=SolverStatus.COMPLETED,
            execution_time_ms=12.5,
            metrics={"lift": 120.5, "drag": 15.2},
            tables={"polar": [{"alpha": 0.0, "cl": 0.3}, {"alpha": 2.0, "cl": 0.5}]},
        )


class TestSolverBase(unittest.TestCase):
    def test_solver_status_values(self) -> None:
        self.assertEqual(SolverStatus.QUEUED.value, "queued")
        self.assertEqual(SolverStatus.RUNNING.value, "running")
        self.assertEqual(SolverStatus.COMPLETED.value, "completed")
        self.assertEqual(SolverStatus.FAILED.value, "failed")
        self.assertEqual(SolverStatus.CANCELLED.value, "cancelled")

    def test_solver_config_serialization(self) -> None:
        config = SolverConfig(
            solver_id="aero_vlm",
            name="VLM Run 1",
            parameters={"alpha": 2.5, "velocity": 20.0},
            options={"mesh_density": "fine"},
        )
        data = config.to_dict()
        self.assertEqual(data["solver_id"], "aero_vlm")
        self.assertEqual(data["name"], "VLM Run 1")
        self.assertEqual(data["parameters"]["alpha"], 2.5)

        deserialized = SolverConfig.from_dict(data)
        self.assertEqual(deserialized.solver_id, config.solver_id)
        self.assertEqual(deserialized.name, config.name)
        self.assertEqual(deserialized.parameters, config.parameters)
        self.assertEqual(deserialized.options, config.options)

    def test_analysis_result_serialization(self) -> None:
        config = SolverConfig(solver_id="thrust_calc", name="Prop Calc")
        result = AnalysisResult(
            solver_id="thrust_calc",
            config=config,
            name="Prop Result 1",
            status=SolverStatus.COMPLETED,
            execution_time_ms=45.0,
            metrics={"thrust_n": 85.0, "efficiency": 0.78},
            tables={"curve": [{"rpm": 1000, "thrust": 10.0}, {"rpm": 2000, "thrust": 40.0}]},
            artifacts={"mesh": "mesh_ref_1"},
        )
        data = result.to_dict()
        self.assertEqual(data["solver_id"], "thrust_calc")
        self.assertEqual(data["metrics"]["thrust_n"], 85.0)
        self.assertEqual(data["status"], "completed")

        deserialized = AnalysisResult.from_dict(data)
        self.assertEqual(deserialized.id, result.id)
        self.assertEqual(deserialized.solver_id, result.solver_id)
        self.assertEqual(deserialized.status, SolverStatus.COMPLETED)
        self.assertEqual(deserialized.metrics["thrust_n"], 85.0)
        self.assertEqual(deserialized.tables["curve"][0]["rpm"], 1000)
        self.assertEqual(deserialized.artifacts["mesh"], "mesh_ref_1")

    def test_dummy_solver_execution(self) -> None:
        config = SolverConfig(solver_id="dummy", name="Dummy Run")
        solver = DummySolver(config)
        self.assertEqual(solver.status, SolverStatus.QUEUED)

        res = solver.run()
        self.assertEqual(solver.status, SolverStatus.COMPLETED)
        self.assertEqual(solver.progress, 100.0)
        self.assertEqual(res.status, SolverStatus.COMPLETED)
        self.assertIn("lift", res.metrics)

    def test_dummy_solver_cancellation(self) -> None:
        config = SolverConfig(solver_id="dummy", name="Cancel Run")
        solver = DummySolver(config)
        solver.cancel()
        self.assertTrue(solver.is_cancel_requested)

        res = solver.run()
        self.assertEqual(solver.status, SolverStatus.CANCELLED)
        self.assertEqual(res.status, SolverStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
