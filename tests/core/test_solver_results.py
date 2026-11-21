"""Unit tests for SolverConfig, SolverResult models, tables, plots, persistence, and results UI panels."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
from PySide6.QtWidgets import QApplication

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument, create_project, open_project, save_project
from setuav_studio.solver.base import SolverConfig, SolverStatus
from setuav_studio.solver.results import (
    PlotDefinition,
    PlotSeriesDef,
    SolverResult,
    SummaryItem,
    TableColumn,
    TableDefinition,
)
from setuav_studio.ui.editor.analysis_plot import AnalysisPlotPropertyEditor
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
    )
    raw = config.to_dict()
    assert raw["solver_id"] == "org.setuav.vlm"
    assert raw["parameters"]["alpha"] == 3.5

    restored = SolverConfig.from_dict(raw)
    assert restored.config_id == config.config_id
    assert restored.solver_id == config.solver_id
    assert restored.name == "VLM Run Alpha"
    assert restored.parameters == {"alpha": 3.5, "velocity": 22.0}


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
        summary={
            "cl_max": SummaryItem(key="cl_max", value=1.55),
            "cd0": SummaryItem(key="cd0", value=0.021),
        },
    )

    # 1. Summary items
    result.summary["stall_speed"] = SummaryItem(
        key="stall_speed", value=13.8, label="Stall Speed", unit="m/s"
    )

    # 2. Table
    table = TableDefinition(
        id="polar",
        title="Lift-Drag Polar",
        columns=[
            TableColumn(key="alpha", label="Alpha", unit="deg"),
            TableColumn(key="cl", label="Lift Coeff"),
            TableColumn(key="cd", label="Drag Coeff"),
        ],
        data={
            "alpha": [0.0, 5.0, 10.0],
            "cl": [0.25, 0.75, 1.25],
            "cd": [0.021, 0.038, 0.082],
        },
    )
    result.tables[table.id] = table
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
    assert raw["summary"]["cl_max"]["value"] == 1.55

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


def test_solver_result_csv_export(tmp_path: Path) -> None:
    config = SolverConfig(solver_id="aero", name="Export Case")
    result = SolverResult(
        solver_id="aero",
        config=config,
        name="Export Result",
        status=SolverStatus.COMPLETED,
        summary={"cl_max": SummaryItem(key="cl_max", value=1.45, label="Max CL")},
        tables={
            "sweep": TableDefinition(
                id="sweep",
                columns=[
                    TableColumn(key="alpha", label="AoA", unit="deg"),
                    TableColumn(key="cl", label="CL"),
                ],
                data={"alpha": [0.0, 5.0], "cl": [0.2, 0.7]},
            )
        },
    )

    exported_csvs = result.export_csv(tmp_path)
    assert len(exported_csvs) == 2  # summary.csv and sweep.csv
    assert (tmp_path / "summary.csv").is_file()
    assert (tmp_path / "sweep.csv").is_file()
    assert "AoA [deg],CL" in (tmp_path / "sweep.csv").read_text(encoding="utf-8")


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
        summary={"cl": SummaryItem(key="cl", value=0.42)},
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
    assert res_reopened.summary["cl"].value == 0.42

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
        "kind": "analysis_config",
        "config_id": config.config_id,
    }
    editor = SolverConfigPropertyEditor(studio_api, selection)
    assert editor.general_table.rowCount() >= 2

    # Edits and undo must refresh the SolverConfigPropertyEditor display.
    editor._on_general_cell_changed(0, 1)  # no-op with same text
    name_item = editor.general_table.item(0, 1)
    assert name_item is not None
    name_item.setText("Aero Run 2")
    cfg = studio_api.get_solver_config(config.config_id)
    assert cfg is not None and cfg.name == "Aero Run 2"
    studio_api.undo()
    assert name_item.text() == "Aero Run 1"
    editor.deleteLater()


def test_result_panel_and_child_views() -> None:
    studio_api = StudioAPI()
    config = SolverConfig(solver_id="org.setuav.aero", name="Case A")
    result = SolverResult(
        solver_id="org.setuav.aero",
        config=config,
        name="Result A",
        status=SolverStatus.COMPLETED,
        summary={"efficiency": SummaryItem(key="efficiency", value=0.88, label="Efficiency")},
        tables={
            "summary_tbl": TableDefinition(
                id="summary_tbl",
                title="Summary Table",
                columns=[
                    TableColumn(key="param", label="Parameter"),
                    TableColumn(key="val", label="Value"),
                ],
                data={"param": ["eta"], "val": [0.88]},
            )
        },
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


def test_solver_default_parameters_follow_the_schema() -> None:
    from setuav_studio.api import ParameterField
    from setuav_studio.solver.base import AbstractSolver

    class _Solver(AbstractSolver):
        PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
            ParameterField(key="speed", default=12.0),
            ParameterField(key="mode", field_type=str, default="fast"),
        ]

        def run(self) -> SolverResult:
            raise NotImplementedError

    assert _Solver.default_parameters() == {"speed": 12.0, "mode": "fast"}
    assert AbstractSolver.default_parameters() == {}


def test_chart_draws_right_axis_series_and_shades_invalid_ranges() -> None:
    from PySide6.QtCharts import QAreaSeries, QLineSeries
    from PySide6.QtCore import Qt

    get_qapp()
    config = SolverConfig(solver_id="org.setuav.propulsion", name="Sweep")
    result = SolverResult(solver_id=config.solver_id, config=config)
    table = TableDefinition(
        id="sweep",
        columns=[
            TableColumn(key="speed", label="Speed", unit="m/s"),
            TableColumn(key="power", label="Power", unit="W"),
            TableColumn(key="current", label="Current", unit="A"),
            TableColumn(key="ok", label="Feasible"),
        ],
        data={
            "speed": [0.0, 1.0, 2.0, 3.0, 4.0],
            "power": [10.0, 20.0, 30.0, 40.0, 50.0],
            "current": [1.0, 2.0, 3.0, 4.0, 5.0],
            "ok": [False, True, True, False, False],
        },
    )
    result.tables[table.id] = table
    plot = PlotDefinition(
        id="power_current",
        table_id="sweep",
        x_column="speed",
        series=[
            PlotSeriesDef(y_column="power"),
            PlotSeriesDef(y_column="current", axis="right"),
        ],
        valid_column="ok",
    )
    restored = PlotDefinition.from_dict(plot.to_dict())
    assert restored == plot
    with pytest.raises(ValueError, match="'left' or 'right'"):
        PlotSeriesDef(y_column="power", axis="top")

    panel = AnalysisChartPanel(StudioAPI())
    panel.load_plot(plot, table, result)
    chart = panel._chart_widget.chart

    vertical_axes = chart.axes(Qt.Orientation.Vertical)
    assert {axis.titleText() for axis in vertical_axes} == {"Power [W]", "Current [A]"}
    lines = {s.name(): s for s in chart.series() if isinstance(s, QLineSeries)}
    sides = {
        name: {
            axis.alignment()
            for axis in line.attachedAxes()
            if axis.orientation() == Qt.Orientation.Vertical
        }
        for name, line in lines.items()
    }
    assert sides == {
        "Power": {Qt.AlignmentFlag.AlignLeft},
        "Current": {Qt.AlignmentFlag.AlignRight},
    }

    # Two runs are infeasible: 0 m/s, and 3 to 4 m/s; the shades meet the
    # feasible points halfway.
    shades = [s for s in chart.series() if isinstance(s, QAreaSeries)]
    assert len(shades) == 2
    spans = sorted((s.upperSeries().at(0).x(), s.upperSeries().at(1).x()) for s in shades)
    assert spans[0][1] == 0.5
    assert spans[1][0] == 2.5
    assert all(
        not marker.isVisible() for shade in shades for marker in chart.legend().markers(shade)
    )


def test_results_belong_to_their_own_configuration() -> None:
    project = ProjectDocument(Path("results.json"), "json", {"components": []})
    first = SolverConfig(solver_id="org.setuav.aero", name="Cruise")
    second = SolverConfig(solver_id="org.setuav.aero", name="Climb")
    project.add_solver_result(SolverResult(solver_id="org.setuav.aero", config=first))

    assert [r.config.config_id for r in project.results_of_config(first.config_id)] == [
        first.config_id
    ]
    assert project.results_of_config(second.config_id) == []


def test_solver_config_edits_are_undoable() -> None:
    api = StudioAPI()
    project = ProjectDocument(Path("configs.json"), "json", {"components": []})
    api._host.set_project(project)
    config = SolverConfig(solver_id="org.setuav.aero", name="Cruise")

    api.add_solver_config(config)
    assert project.get_solver_config(config.config_id) is not None
    api.undo()
    assert project.get_solver_config(config.config_id) is None
    api.redo()

    assert api.remove_solver_config(config.config_id)
    assert project.get_solver_config(config.config_id) is None
    api.undo()
    assert project.get_solver_config(config.config_id) is not None


def test_summary_and_table_display_unit_conversion() -> None:
    import math

    from setuav_studio.units import get_unit_manager

    um = get_unit_manager()
    um.set_active_preset("si")

    # Neutral point stored in meters must convert to SI display unit (mm): 0.25 m -> 250 mm
    np_item = SummaryItem(key="x_np", value=0.25, label="Neutral Point", unit="m")
    disp_val, disp_unit = np_item.display_value_and_unit()
    assert disp_unit == "mm"
    assert isinstance(disp_val, float)
    assert math.isclose(disp_val, 250.0, rel_tol=1e-12)

    # Boolean summary item must never be coerced to float even if quantity_id is set
    flag_item = SummaryItem(key="ok", value=True, quantity_id="length")
    assert flag_item.display_value_and_unit() == (True, "")

    # Table columns with display symbols ("°", "RPM") or empty unit must convert properly
    um.set_display_unit("angle", "rad")
    um.set_display_unit("frequency", "hz")
    um.set_display_unit("velocity", "km/h")
    table = TableDefinition(
        id="sweep",
        columns=[
            TableColumn(key="alpha", label="AoA", unit="°", quantity_id="angle"),
            TableColumn(key="rpm", label="RPM", unit="RPM", quantity_id="frequency"),
            TableColumn(key="v", label="Speed", unit="", quantity_id="velocity"),
            TableColumn(key="ok", label="OK", unit="", quantity_id="velocity"),
        ],
        data={
            "alpha": [180.0],
            "rpm": [6000.0],
            "v": [10.0],
            "ok": [True],
        },
    )
    assert math.isclose(table.get_column_display_values("alpha")[0], math.pi, rel_tol=1e-12)
    assert math.isclose(table.get_column_display_values("rpm")[0], 100.0, rel_tol=1e-12)
    assert math.isclose(table.get_column_display_values("v")[0], 36.0, rel_tol=1e-12)
    assert table.get_column_display_values("ok") == [True]


def test_analysis_plot_editor_updates_default_label_when_y_column_changes() -> None:
    api = StudioAPI()
    project = ProjectDocument(Path("plot.json"), "json", {"components": []})
    api._host.set_project(project)

    table = TableDefinition(
        id="sweep",
        columns=[
            TableColumn(key="alpha", label="Angle of Attack"),
            TableColumn(key="cl", label="Lift Coefficient"),
            TableColumn(key="cd", label="Drag Coefficient"),
        ],
        data={"alpha": [0.0, 2.0], "cl": [0.1, 0.3], "cd": [0.02, 0.03]},
    )
    plot = PlotDefinition(
        id="polar",
        title="Polar",
        table_id="sweep",
        x_column="alpha",
        series=[
            PlotSeriesDef(y_column="cl", label="Lift Coefficient"),
            PlotSeriesDef(y_column="cl", label="Custom Curve"),
        ],
    )
    result = SolverResult(
        solver_id="org.setuav.aero",
        config=SolverConfig(solver_id="org.setuav.aero"),
        tables={"sweep": table},
        plots={"polar": plot},
    )
    project.add_solver_result(result)

    editor = AnalysisPlotPropertyEditor(
        api,
        {"kind": "analysis_plot", "result_id": result.id, "plot_id": "polar"},
    )
    try:
        from PySide6.QtWidgets import QComboBox

        # Curve 0 has default label matching column label ("Lift Coefficient") -> must follow new Y
        # Curve 1 has custom label ("Custom Curve") -> must preserve custom label
        for idx, expected_label in ((0, "Drag Coefficient"), (1, "Custom Curve")):
            layout_item = editor._series_layout.itemAt(idx)
            assert layout_item is not None
            card = layout_item.widget()
            assert card is not None
            combos = card.findChildren(QComboBox)
            y_combo = combos[0]
            cd_idx = y_combo.findData("cd")
            assert cd_idx >= 0
            y_combo.setCurrentIndex(cd_idx)
            assert plot.series[idx].y_column == "cd"
            assert plot.series[idx].label == expected_label
    finally:
        editor.deleteLater()
