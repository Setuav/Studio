"""Asynchronous solver execution runner integrated with TaskManager and StudioAPI."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from setuav_studio.task import CancellationToken, TaskPriority

from .base import AbstractSolver, SolverStatus
from .results import AnalysisResult

if TYPE_CHECKING:
    from setuav_studio.api.api import StudioAPI

logger = logging.getLogger(__name__)


def execute_solver(solver: AbstractSolver, token: CancellationToken) -> AnalysisResult:
    """Synchronous worker function that executes a solver and tracks timing/cancellation."""
    start_time = time.perf_counter()
    solver.status = SolverStatus.RUNNING
    token.report_progress(0, 100, f"Running {solver.config.name}...")

    try:
        token.check_cancelled()
        if solver.is_cancel_requested:
            solver.status = SolverStatus.CANCELLED
            token.report_progress(100, 100, "Solver run cancelled.")
            return AnalysisResult(
                solver_id=solver.config.solver_id,
                config=solver.config,
                name=solver.config.name,
                status=SolverStatus.CANCELLED,
            )

        result = solver.run()
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        result.execution_time_ms = elapsed_ms
        solver.status = result.status
        token.report_progress(100, 100, f"Completed {solver.config.name}.")
        return result
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        solver.status = SolverStatus.FAILED
        solver.error_message = str(exc)
        logger.error("Solver %s failed: %s", solver.config.name, exc, exc_info=True)
        return AnalysisResult(
            solver_id=solver.config.solver_id,
            config=solver.config,
            name=solver.config.name,
            status=SolverStatus.FAILED,
            execution_time_ms=elapsed_ms,
            error_message=str(exc),
        )


class SolverRunner:
    """Manages asynchronous solver execution, progress callbacks, and project document updates."""

    def __init__(self, api: StudioAPI) -> None:
        self._api = api
        self._registry: dict[str, type[AbstractSolver]] = {}

    def register_solver(self, solver_id: str, solver_cls: type[AbstractSolver]) -> None:
        """Register a solver class by solver ID."""
        self._registry[solver_id] = solver_cls

    def get_solver_class(self, solver_id: str) -> type[AbstractSolver] | None:
        """Get registered solver class by ID."""
        return self._registry.get(solver_id)

    def run_solver(
        self,
        solver: AbstractSolver,
        on_complete: Callable[[AnalysisResult], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> Any:
        """Submit a solver instance to run asynchronously via TaskManager."""
        name = f"Solver: {solver.config.name}"

        def _on_finished(result: AnalysisResult) -> None:
            self._api.add_analysis_result(result)
            if on_complete:
                on_complete(result)

        def _on_err(exc: Exception) -> None:
            if on_error:
                on_error(exc)

        return self._api.tasks.submit(
            name=name,
            target=lambda token: execute_solver(solver, token),
            priority=priority,
            on_finished=_on_finished,
            on_error=_on_err,
        )
