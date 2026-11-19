"""Starting an analysis from the user interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.solver.launch import run_analysis


def test_run_analysis_reports_a_project_without_configurations() -> None:
    api = StudioAPI()
    api._host.set_project(ProjectDocument(Path("empty.json"), "json", {"components": []}))
    statuses: list[tuple[str, str]] = []
    api._host.bind_status_handler(lambda message, level, _ms: statuses.append((message, level)))

    run_analysis(api)

    assert statuses == [("No analysis configuration available to run.", "warning")]
    with pytest.raises(KeyError, match="'missing'"):
        run_analysis(api, "missing")
