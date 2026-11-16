"""Asynchronous solver execution runner integrated with TaskManager and StudioAPI."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from setuav_studio.task.types import CancellationToken, TaskCancelledError, TaskPriority

from .base import AbstractSolver, SolverStatus
from .results import SolverResult

if TYPE_CHECKING:
    from setuav_studio.api.api import StudioAPI


def execute_solver(solver: AbstractSolver, token: CancellationToken) -> SolverResult:
    """Run a solver synchronously and return its completed result.

    Cancellation raises ``TaskCancelledError`` and solver failures propagate, so the
    task manager reports them through its cancelled and error callbacks.
    """
    start_time = time.perf_counter()
    solver.status = SolverStatus.RUNNING
    solver.token = token
    token.report_progress(0, 100, f"Running {solver.config.name}...")

    try:
        token.check_cancelled()
        if solver.is_cancel_requested:
            raise TaskCancelledError(f"Solver {solver.config.name} cancelled.")
        solver.check_parameter_ranges()
        result = solver.run()
    except TaskCancelledError:
        solver.status = SolverStatus.CANCELLED
        raise
    except Exception as exc:
        solver.status = SolverStatus.FAILED
        solver.error_message = str(exc)
        raise

    result.execution_time_ms = (time.perf_counter() - start_time) * 1000.0
    solver.status = result.status
    token.report_progress(100, 100, f"Completed {solver.config.name}.")
    return result


class SolverRunner:
    """Manages asynchronous solver execution, progress callbacks, and project document updates."""

    def __init__(self, api: StudioAPI) -> None:
        self._api = api
        self._registry: dict[str, type[AbstractSolver]] = {}

    def register_solver(self, solver_id: str, solver_cls: type[AbstractSolver]) -> None:
        """Register a solver class by solver ID."""
        self._registry[solver_id] = solver_cls

    def unregister_solver(self, solver_id: str) -> None:
        """Unregister a solver class by solver ID."""
        self._registry.pop(solver_id, None)

    def get_solver_class(self, solver_id: str) -> type[AbstractSolver] | None:
        """Get registered solver class by ID."""
        return self._registry.get(solver_id)

    def run_solver(
        self,
        solver: AbstractSolver,
        on_complete: Callable[[SolverResult], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> Any:
        """Submit a solver instance to run asynchronously via TaskManager."""
        if solver.project is None:
            solver.project = self._api.project
        if solver.api is None:
            solver.api = self._api

        name = f"Solver: {solver.config.name}"

        def _on_finished(result: SolverResult) -> None:
            self._api.add_solver_result(result)
            if on_complete:
                on_complete(result)

        def _on_err(exc: Exception) -> None:
            if on_error:
                on_error(exc)

        def _on_cancelled() -> None:
            if on_cancelled:
                on_cancelled()

        return self._api.tasks.submit(
            name=name,
            target=lambda token: execute_solver(solver, token),
            priority=priority,
            on_finished=_on_finished,
            on_error=_on_err,
            on_cancelled=_on_cancelled,
        )
