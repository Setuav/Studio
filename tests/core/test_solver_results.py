"""Unit tests for SolverConfig, SolverResult models, tables, plots, persistence, and results UI panels."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument, create_project, open_project, save_project
from setuav_studio.solver.base import SolverConfig, SolverStatus
from setuav_studio.solver.results import (
    PlotSeriesDef,
    SolverResult,
    TableColumn,
)
from setuav_studio.ui.editor.solver_config import SolverConfigPropertyEditor
from setuav_studio.ui.panels.results import (
    AnalysisChartPanel,
    AnalysisTablePanel,
    ResultPanel,
)
from tests._common import get_qapp


@pytest.fixture(autouse=True)
def qapp() -> QApplication:
    return get_qapp()


# ==============================================================================
# 1. SolverStatus & SolverConfig Tests
# ==============================================================================


def test_solver_status_values() -> None:
    assert SolverStatus.QUEUED == "queued"
    assert SolverStatus.RUNNING == "running"
    assert SolverStatus.COMPLETED == "completed"
    assert SolverStatus.FAILED == "failed"
    assert SolverStatus.CANCELLED == "cancelled"


def test_solver_config_serialization_roundtrip() -> None:
    config = SolverConfig(
        solver_id="org.setuav.vlm",
        name="VLM Run Alpha",
        parameters={"alpha": 3.5, "velocity": 22.0},
        options={"mesh_density": "fine", "symmetry": True},
    )
    raw = config.to_dict()
    assert raw["solver_id"] == "org.setuav.vlm"
    assert raw["parameters"]["alpha"] == 3.5

    restored = SolverConfig.from_dict(raw)
    assert restored.config_id == config.config_id
    assert restored.solver_id == config.solver_id
    assert restored.name == "VLM Run Alpha"
    assert restored.parameters == {"alpha": 3.5, "velocity": 22.0}
    assert restored.options == {"mesh_density": "fine", "symmetry": True}


# ==============================================================================
# 2. SolverResult, Tables, Plots, Summaries
# ==============================================================================


def test_solver_result_tables_plots_serialization() -> None:
    config = SolverConfig(solver_id="org.setuav.aero", name="Polar Sweep")
    result = SolverResult(
        solver_id="org.setuav.aero",
        config=config,
        name="Polar Results",
        status=SolverStatus.COMPLETED,
        execution_time_ms=125.0,
        metrics={"cl_max": 1.55, "cd0": 0.021},
    )

    # 1. Summary items
    result.add_summary("cl_max", 1.55, label="Max CL")
    result.add_summary("stall_speed", 13.8, label="Stall Speed", unit="m/s")

    # 2. Table
    table = result.add_table(
        table_id="polar",
        title="Lift-Drag Polar",
        columns=[
            TableColumn(key="alpha", label="Alpha", unit="deg"),
            TableColumn(key="cl", label="Lift Coeff"),
            TableColumn(key="cd", label="Drag Coeff"),
        ],
        data=[
            {"alpha": 0.0, "cl": 0.25, "cd": 0.021},
            {"alpha": 5.0, "cl": 0.75, "cd": 0.038},
            {"alpha": 10.0, "cl": 1.25, "cd": 0.082},
        ],
    )
    assert len(table.get_column("cl")) == 3

    # 3. Plot
    plot = result.add_plot(
        plot_id="cl_alpha",
        table_id="polar",
        x_column="alpha",
        title="CL vs Alpha",
        x_label="Angle of Attack [deg]",
        y_label="Lift Coefficient CL",
        series=[
            PlotSeriesDef(
                y_column="cl",
                label="Baseline Wing",
                color="#0066cc",
            )
        ],
    )
    assert len(plot.series) == 1

    # Roundtrip serialization
    raw = result.to_dict()
    assert raw["status"] == "completed"
    assert raw["metrics"]["cl_max"] == 1.55

    restored = SolverResult.from_dict(raw)
    assert restored.id == result.id
    assert restored.name == "Polar Results"
    assert restored.status == SolverStatus.COMPLETED
    assert restored.execution_time_ms == 125.0

    # Verify tables restored
    assert "polar" in restored.tables
    restored_table = restored.tables["polar"]
    assert len(restored_table.get_column("cl")) == 3
    assert restored_table.get_column("cl")[1] == 0.75

    # Verify plots restored
    assert "cl_alpha" in restored.plots
    restored_plot = restored.plots["cl_alpha"]
    assert len(restored_plot.series) == 1
    assert restored_plot.series[0].label == "Baseline Wing"
    assert restored_plot.series[0].y_column == "cl"


def test_solver_result_csv_and_json_export(tmp_path: Path) -> None:
    config = SolverConfig(solver_id="aero", name="Export Case")
    result = SolverResult(
        solver_id="aero",
        config=config,
        name="Export Result",
        status=SolverStatus.COMPLETED,
    )
    result.add_summary("cl_max", 1.45, label="Max CL")
    result.add_table(
        table_id="sweep",
        columns=[
            TableColumn(key="alpha", label="AoA", unit="deg"),
            TableColumn(key="cl", label="CL"),
        ],
        data={"alpha": [0.0, 5.0], "cl": [0.2, 0.7]},
    )

    # 1. Export CSV
    exported_csvs = result.export_csv(tmp_path)
    assert len(exported_csvs) == 2  # summary.csv and sweep.csv
    assert (tmp_path / "summary.csv").is_file()
    assert (tmp_path / "sweep.csv").is_file()
    assert "AoA [deg],CL" in (tmp_path / "sweep.csv").read_text(encoding="utf-8")

    # 2. Export JSON
    json_path = tmp_path / "result.json"
    result.export_json(json_path)
    assert json_path.is_file()

    # 3. Reload from exported JSON
    import json

    with open(json_path, encoding="utf-8") as f:
        loaded = json.load(f)
    from_json = SolverResult.from_dict(loaded)
    assert from_json.id == result.id
    assert from_json.tables["sweep"].get_column("cl") == [0.2, 0.7]


# ==============================================================================
# 3. Project Integration & Persistence
# ==============================================================================


def test_project_solver_configs_and_results_lifecycle(tmp_path: Path) -> None:
    project_path = tmp_path / "uav_analysis.suav"
    project = create_project(project_path)

    # 1. Config management
    config1 = SolverConfig(solver_id="org.setuav.vlm", name="Cruise VLM")
    config2 = SolverConfig(solver_id="org.setuav.motor", name="Prop Calc")
    project.add_solver_config(config1)
    project.add_solver_config(config2)
    assert len(project.solver_configs) == 2
    assert project.get_solver_config(config1.config_id) == config1

    # 2. Result management
    result = SolverResult(
        solver_id="org.setuav.vlm",
        config=config1,
        name="Cruise VLM Result",
        status=SolverStatus.COMPLETED,
        metrics={"cl": 0.42},
    )
    project.add_solver_result(result)
    assert len(project.solver_results) == 1
    assert project.get_solver_result(result.id) is not None

    # 3. Persistence across save and reopen
    save_project(project)
    reopened = open_project(project_path)

    assert len(reopened.solver_configs) == 2
    cfg_reopened = reopened.get_solver_config(config1.config_id)
    assert cfg_reopened is not None
    assert cfg_reopened.name == "Cruise VLM"

    assert len(reopened.solver_results) == 1
    res_reopened = reopened.get_solver_result(result.id)
    assert res_reopened is not None
    assert res_reopened.name == "Cruise VLM Result"
    assert res_reopened.metrics["cl"] == 0.42

    # 4. Removal
    reopened.remove_solver_config(config1.config_id)
    reopened.remove_solver_result(result.id)
    assert len(reopened.solver_configs) == 1
    assert len(reopened.solver_results) == 0


def test_studio_api_solver_config_selection_events() -> None:
    studio_api = StudioAPI()
    project = ProjectDocument(Path("test.json"), "json", {"components": []})
    studio_api._host.set_project(project)

    config = SolverConfig(solver_id="vlm", name="Test Config")
    selected_configs: list[SolverConfig | None] = []

    studio_api.on_solver_config_selection_changed(selected_configs.append)
    studio_api.add_solver_config(config)

    assert studio_api.current_solver_config_id == config.config_id
    assert studio_api.get_current_solver_config() == config
    assert config in selected_configs


# ==============================================================================
# 4. Results UI Panels & Config Property Editor
# ==============================================================================


def test_solver_config_property_editor(tmp_path: Path) -> None:
    studio_api = StudioAPI()
    project = create_project(tmp_path / "editor_test.suav")
    studio_api._host.set_project(project)

    config = SolverConfig(
        solver_id="vlm_solver",
        name="Aero Run 1",
        parameters={"alpha": 2.0, "speed": 30.0},
    )
    studio_api.add_solver_config(config)

    selection = {
        "kind": "solver_config",
        "id": config.config_id,
        "config_id": config.config_id,
    }
    editor = SolverConfigPropertyEditor(studio_api, selection)
    assert editor.general_table.rowCount() >= 2


def test_result_panel_and_child_views() -> None:
    studio_api = StudioAPI()
    config = SolverConfig(solver_id="org.setuav.aero", name="Case A")
    result = SolverResult(
        solver_id="org.setuav.aero",
        config=config,
        name="Result A",
        status=SolverStatus.COMPLETED,
        metrics={"efficiency": 0.88},
    )
    result.add_summary("efficiency", 0.88, label="Efficiency")
    result.add_table(
        table_id="summary_tbl",
        title="Summary Table",
        columns=[
            TableColumn(key="param", label="Parameter"),
            TableColumn(key="val", label="Value"),
        ],
        data=[{"param": "eta", "val": 0.88}],
    )
    result.add_plot(
        plot_id="curve",
        table_id="summary_tbl",
        x_column="param",
        title="Efficiency Curve",
        series=[
            PlotSeriesDef(
                y_column="val",
                label="Eta",
            )
        ],
    )

    # 1. ResultPanel
    panel = ResultPanel(studio_api)
    tbl = result.tables["summary_tbl"]
    plt = result.plots["curve"]
    panel.show_table(result, tbl)
    assert len(panel._panes) == 1

    panel.show_plot(result, plt, tbl, mode="add")
    assert len(panel._panes) == 2

    # 2. AnalysisTablePanel
    table_panel = AnalysisTablePanel(studio_api)
    table_panel.load_table(tbl, result)
    assert table_panel._current_table == tbl

    # 3. AnalysisChartPanel
    chart_panel = AnalysisChartPanel(studio_api)
    chart_panel.load_plot(plt, tbl, result)
    assert chart_panel._current_plot == plt
