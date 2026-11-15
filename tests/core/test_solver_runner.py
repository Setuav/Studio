"""Unit tests for solver execution, cancellation, and SolverRunner task lifecycle."""

from __future__ import annotations

from typing import Any

import pytest

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.solver import (
    AbstractSolver,
    SolverConfig,
    SolverResult,
    SolverRunner,
    SolverStatus,
    execute_solver,
)
from setuav_studio.task.types import TaskCancelledError
from tests._common import get_qapp


@pytest.fixture(autouse=True)
def qapp() -> Any:
    return get_qapp()


class DummyCancellationToken:
    def __init__(self, cancelled: bool = False) -> None:
        self._cancelled = cancelled

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def check_cancelled(self) -> None:
        if self._cancelled:
            raise TaskCancelledError("Cancelled")

    def report_progress(self, current: int, total: int, message: str = "") -> None:
        pass

    def cancel(self) -> None:
        self._cancelled = True


class SuccessSolver(AbstractSolver):
    def run(self) -> SolverResult:
        self.progress = 50.0
        return SolverResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            metrics={"lift": 120.0, "drag": 15.0},
        )


class CancelableSolver(AbstractSolver):
    def run(self) -> SolverResult:
        if self.token:
            self.token.check_cancelled()
        if self.is_cancel_requested:
            raise TaskCancelledError("Cancelled by solver flag")
        return SolverResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
        )


class FailingSolver(AbstractSolver):
    def run(self) -> SolverResult:
        raise ValueError("Simulation diverged")


# ==============================================================================
# 1. execute_solver Worker Function Tests
# ==============================================================================


def test_execute_solver_success() -> None:
    config = SolverConfig(solver_id="org.test:aero", name="Aero Run")
    solver = SuccessSolver(config)
    token = DummyCancellationToken()

    result = execute_solver(solver, token)  # type: ignore[arg-type]

    assert result.status == SolverStatus.COMPLETED
    assert solver.status == SolverStatus.COMPLETED
    assert result.metrics["lift"] == 120.0
    assert result.execution_time_ms > 0.0


def test_execute_solver_cancellation() -> None:
    config = SolverConfig(solver_id="org.test:aero", name="Aero Cancel")
    solver = CancelableSolver(config)
    token = DummyCancellationToken(cancelled=True)

    with pytest.raises(TaskCancelledError):
        execute_solver(solver, token)  # type: ignore[arg-type]

    assert solver.status == SolverStatus.CANCELLED


def test_execute_solver_failure() -> None:
    config = SolverConfig(solver_id="org.test:aero", name="Aero Failure")
    solver = FailingSolver(config)
    token = DummyCancellationToken()

    with pytest.raises(ValueError, match="Simulation diverged"):
        execute_solver(solver, token)  # type: ignore[arg-type]

    assert solver.status == SolverStatus.FAILED
    assert solver.error_message == "Simulation diverged"


# ==============================================================================
# 2. SolverRunner Registry & Execution Tests
# ==============================================================================


def test_solver_runner_registry() -> None:
    studio_api = StudioAPI()
    runner = SolverRunner(studio_api)

    runner.register_solver("org.test:success", SuccessSolver)
    assert runner.get_solver_class("org.test:success") is SuccessSolver
    assert runner.get_solver_class("org.test:missing") is None

    runner.unregister_solver("org.test:success")
    assert runner.get_solver_class("org.test:success") is None


def test_solver_runner_executes_and_adds_result_to_project() -> None:
    studio_api = StudioAPI()
    project = ProjectDocument(path=None, kind="json", data={"components": []})  # type: ignore[arg-type]
    studio_api._host.set_project(project)

    runner = SolverRunner(studio_api)
    config = SolverConfig(solver_id="org.test:aero", name="Async Run")
    solver = SuccessSolver(config)

    completed_results: list[SolverResult] = []

    # Run solver asynchronously via task manager
    _ = runner.run_solver(
        solver,
        on_complete=completed_results.append,
    )

    # Wait for the task to finish on Qt thread pool
    assert studio_api.tasks.thread_pool.waitForDone(5000)
    get_qapp().processEvents()

    # Result was passed to callback
    assert len(completed_results) == 1
    res = completed_results[0]
    assert res.status == SolverStatus.COMPLETED
    assert res.metrics["lift"] == 120.0

    # Result was automatically added to current project
    assert res.id in project.solver_results


def test_solver_runner_reports_failure_through_on_error() -> None:
    studio_api = StudioAPI()
    project = ProjectDocument(path=None, kind="json", data={"components": []})  # type: ignore[arg-type]
    studio_api._host.set_project(project)

    runner = SolverRunner(studio_api)
    solver = FailingSolver(SolverConfig(solver_id="org.test:aero", name="Diverging Run"))
    completed: list[SolverResult] = []
    errors: list[Exception] = []

    runner.run_solver(solver, on_complete=completed.append, on_error=errors.append)
    assert studio_api.tasks.thread_pool.waitForDone(5000)
    get_qapp().processEvents()

    assert completed == []
    assert [str(err) for err in errors] == ["Simulation diverged"]
    assert project.solver_results == {}
    assert solver.status == SolverStatus.FAILED
