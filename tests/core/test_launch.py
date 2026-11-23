"""Starting an analysis from the user interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.solver import SolverConfig
from setuav_studio.solver.base import AbstractSolver
from setuav_studio.solver.launch import run_analysis
from setuav_studio.solver.results import SolverResult


def test_run_analysis_reports_a_project_without_configurations() -> None:
    api = StudioAPI()
    api._host.set_project(ProjectDocument(Path("empty.json"), "json", {"components": []}))
    statuses: list[tuple[str, str]] = []
    api._host.bind_status_handler(lambda message, level, _ms: statuses.append((message, level)))

    run_analysis(api)

    assert statuses == [("No analysis configuration available to run.", "warning")]
    with pytest.raises(KeyError, match="'missing'"):
        run_analysis(api, "missing")


class _NeedsAWing(AbstractSolver):
    @classmethod
    def unmet_requirement(cls, project: ProjectDocument) -> str | None:
        return "Add a lifting surface to the design first."

    def run(self) -> SolverResult:
        raise AssertionError("an analysis with an unmet requirement must not run")


def test_run_analysis_refuses_an_analysis_the_design_cannot_run() -> None:
    api = StudioAPI()
    api._host.set_project(ProjectDocument(Path("empty.json"), "json", {"components": []}))
    statuses: list[tuple[str, str]] = []
    api._host.bind_status_handler(lambda message, level, _ms: statuses.append((message, level)))
    api.register_solver("needs-a-wing", _NeedsAWing)
    config = SolverConfig(solver_id="needs-a-wing", name="Polar", parameters={})
    api.add_solver_config(config)
    started: list[AbstractSolver] = []
    api.run_solver = lambda solver, **_kwargs: started.append(solver)  # type: ignore[method-assign]

    run_analysis(api, config.config_id)

    assert started == []
    assert statuses[-1] == (
        "Analysis 'Polar' cannot run. Add a lifting surface to the design first.",
        "warning",
    )
