"""Asynchronous solver execution runner integrated with TaskManager and StudioAPI."""

from __future__ import annotations

import time
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from setuav_studio.api.events import StudioEvents
from setuav_studio.project.document import ProjectDocument
from setuav_studio.task.types import CancellationToken, TaskCancelledError, TaskPriority

from .base import AbstractSolver, SolverConfig, SolverStatus
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
        self._api_ref = weakref.ref(api)
        self._registry: dict[str, type[AbstractSolver]] = {}
        self._active_tasks: dict[str, tuple[weakref.ref[ProjectDocument] | None, Any]] = {}
        runner_ref = weakref.ref(self)

        def _on_project_closed(project: Any) -> None:
            runner = runner_ref()
            if runner is not None and isinstance(project, ProjectDocument):
                runner.cancel_project_solvers(project)

        def _on_project_opened(project: Any) -> None:
            runner = runner_ref()
            if runner is not None:
                runner._cancel_other_project_solvers(project)

        api.subscribe(StudioEvents.PROJECT_CLOSED, _on_project_closed)
        api.subscribe(StudioEvents.PROJECT_OPENED, _on_project_opened)

    @property
    def _api(self) -> StudioAPI:
        api = self._api_ref()
        if api is None:
            raise RuntimeError("StudioAPI is no longer alive.")
        return api

    def register_solver(self, solver_id: str, solver_cls: type[AbstractSolver]) -> None:
        """Register a solver class by solver ID."""
        self._registry[solver_id] = solver_cls

    def unregister_solver(self, solver_id: str) -> None:
        """Unregister a solver class by solver ID."""
        self._registry.pop(solver_id, None)

    def get_solver_class(self, solver_id: str) -> type[AbstractSolver] | None:
        """Get registered solver class by ID."""
        return self._registry.get(solver_id)

    def cancel_project_solvers(self, project: ProjectDocument) -> int:
        """Cancel all active solver tasks bound to ``project``."""
        cancelled = 0
        for task_id, (project_ref, handle) in list(self._active_tasks.items()):
            owner = project_ref() if project_ref is not None else None
            if owner is project:
                if handle.cancel():
                    cancelled += 1
                self._active_tasks.pop(task_id, None)
        return cancelled

    def _cancel_other_project_solvers(self, active_project: Any) -> int:
        """Cancel active project-bound solver tasks whose owner is no longer ``active_project``."""
        cancelled = 0
        for task_id, (project_ref, handle) in list(self._active_tasks.items()):
            if project_ref is None:
                continue
            owner = project_ref()
            if owner is None or owner is not active_project:
                if handle.cancel():
                    cancelled += 1
                self._active_tasks.pop(task_id, None)
        return cancelled

    def run_solver(
        self,
        solver: AbstractSolver,
        on_complete: Callable[[SolverResult], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> Any:
        """Submit a solver instance to run asynchronously on an isolated snapshot."""
        api = self._api
        target_project = api.project
        source_project = solver.project if solver.project is not None else target_project
        if isinstance(source_project, ProjectDocument):
            solver.project = source_project.snapshot()
        elif source_project is not None:
            solver.project = source_project
        solver.config = SolverConfig.from_dict(solver.config.to_dict())

        had_target_project = target_project is not None
        target_project_ref = weakref.ref(target_project) if target_project is not None else None
        task_id_box: list[str] = []
        name = f"Solver: {solver.config.name}"

        def _release_tracking() -> None:
            if task_id_box:
                self._active_tasks.pop(task_id_box[0], None)

        def _on_finished(result: SolverResult) -> None:
            _release_tracking()
            current_api = self._api_ref()
            if current_api is None:
                return
            if had_target_project:
                owner = target_project_ref() if target_project_ref is not None else None
                if owner is None or current_api.project is not owner:
                    return
                current_api.add_solver_result(result)
            if on_complete:
                on_complete(result)

        def _on_err(exc: Exception) -> None:
            _release_tracking()
            if on_error:
                on_error(exc)

        def _on_cancelled() -> None:
            _release_tracking()
            if on_cancelled:
                on_cancelled()

        handle = api.tasks.submit(
            name=name,
            target=lambda token: execute_solver(solver, token),
            priority=priority,
            on_finished=_on_finished,
            on_error=_on_err,
            on_cancelled=_on_cancelled,
        )
        task_id_box.append(handle.id)
        self._active_tasks[handle.id] = (target_project_ref, handle)
        return handle
