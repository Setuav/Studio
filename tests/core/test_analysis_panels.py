"""Tests for AnalysisChartPanel, AnalysisTablePanel, and Project Explorer integration."""

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from setuav_studio.api import StudioAPI
from setuav_studio.model.analysis_config import AnalysisConfig
from setuav_studio.project import create_project
from setuav_studio.solver.base import SolverStatus
from setuav_studio.solver.results import (
    AnalysisResult,
    PlotSeriesDef,
    TableColumn,
)
from setuav_studio.ui.editor.analysis_config import AnalysisConfigPropertyEditor
from setuav_studio.ui.panels.project_explorer.panel import ProjectExplorerPanel
from setuav_studio.ui.panels.results import AnalysisChartPanel, AnalysisTablePanel


class TestAnalysisPanels(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project.suav"
        self.api = StudioAPI()
        self.api.current_project = create_project(self.project_path)

        self.config = AnalysisConfig(
            solver_id="vlm_solver",
            name="VLM Baseline Run",
            parameters={"velocity": 20.0},
        )
        self.api.add_analysis_config(self.config)

        # Build an AnalysisResult matching this config
        solver_cfg = self.config.to_solver_config()
        self.result = AnalysisResult(
            solver_id="vlm_solver",
            config=solver_cfg,
            name="VLM Baseline Result",
            status=SolverStatus.COMPLETED,
            execution_time_ms=85.0,
        )
        self.result.add_summary("cl_max", 1.45, label="Max CL")
        self.result.add_summary("stall_speed", 14.5, label="Stall Speed", unit="m/s")

        self.table = self.result.add_table(
            table_id="polar_data",
            title="Polar Data",
            columns=[
                TableColumn(key="alpha", label="AoA", unit="deg"),
                TableColumn(key="cl", label="Lift Coeff"),
                TableColumn(key="cd", label="Drag Coeff"),
            ],
            data={
                "alpha": [0.0, 2.0, 4.0],
                "cl": [0.25, 0.50, 0.75],
                "cd": [0.012, 0.018, 0.028],
            },
        )

        self.plot = self.result.add_plot(
            plot_id="cl_vs_alpha",
            table_id="polar_data",
            x_column="alpha",
            title="CL vs Alpha",
            series=[PlotSeriesDef(y_column="cl", label="CL Curve")],
        )

        self.api.current_project.add_analysis_result(self.result)

        # Track show_panel calls
        self.shown_panels: list[str] = []
        self.api._show_panel = lambda p_id: self.shown_panels.append(p_id)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_analysis_chart_panel_load_and_replot(self) -> None:
        panel = AnalysisChartPanel(self.api)
        self.assertEqual(panel._stack.currentWidget(), panel._empty_view)

        # Load plot
        panel.load_plot(self.plot, self.table, self.result)
        self.assertEqual(panel._stack.currentWidget(), panel._chart_widget)
        self.assertEqual(panel._title_label.text(), "CL vs Alpha")
        self.assertEqual(panel._x_combo.count(), 3)
        self.assertEqual(panel._x_combo.currentData(), "alpha")

        # Dynamically change X axis to 'cd'
        idx = panel._x_combo.findData("cd")
        self.assertGreaterEqual(idx, 0)
        panel._x_combo.setCurrentIndex(idx)
        self.assertEqual(panel._active_x_column, "cd")

    def test_analysis_chart_panel_selection_response(self) -> None:
        panel = AnalysisChartPanel(self.api)
        selection = {
            "kind": "analysis_plot",
            "result_id": self.result.id,
            "plot_id": self.plot.id,
        }
        self.api.set_selection(selection)

        self.assertEqual(panel._stack.currentWidget(), panel._chart_widget)
        self.assertEqual(panel._title_label.text(), "CL vs Alpha")

    def test_analysis_table_panel_load_and_units_toggle(self) -> None:
        panel = AnalysisTablePanel(self.api)
        self.assertEqual(panel._stack.currentWidget(), panel._empty_view)

        # Load table
        panel.load_table(self.table, self.result)
        self.assertEqual(panel._stack.currentWidget(), panel._table_view)
        self.assertIsNotNone(panel._model)
        self.assertEqual(panel._model.rowCount(), 3)
        self.assertEqual(panel._model.columnCount(), 3)

        # Header with display units
        header_0 = panel._model.headerData(0, orientation=self.horizontalHeaderOrientation())
        self.assertEqual(header_0, "AoA [°]")

        # Values
        val_0_0 = panel._model.data(panel._model.index(0, 0))
        self.assertEqual(val_0_0, "0.0000")

        # Toggle to SI units
        panel._toggle_units()
        self.assertFalse(panel._use_display_units)
        self.assertEqual(panel._units_toggle_btn.text(), "Units: SI")
        header_si = panel._model.headerData(0, orientation=self.horizontalHeaderOrientation())
        self.assertEqual(header_si, "AoA [deg]")

    def test_analysis_table_panel_selection_response(self) -> None:
        panel = AnalysisTablePanel(self.api)
        selection = {
            "kind": "analysis_table",
            "result_id": self.result.id,
            "table_id": self.table.id,
        }
        self.api.set_selection(selection)

        self.assertEqual(panel._stack.currentWidget(), panel._table_view)
        self.assertEqual(panel._title_label.text(), "Polar Data")

    def test_analysis_config_editor_shows_results_summary(self) -> None:
        selection = {
            "kind": "analysis_config",
            "id": self.config.config_id,
            "config_id": self.config.config_id,
        }
        editor = AnalysisConfigPropertyEditor(self.api, selection)
        self.assertFalse(editor._results_section_widget.isHidden())

        # Test View Plot button
        editor._open_chart_btn.click()
        self.assertIn("core:analysis-chart", self.shown_panels)

        # Test View Table button
        editor._open_table_btn.click()
        self.assertIn("core:analysis-table", self.shown_panels)

    def test_project_explorer_tree_shows_tables_and_plots(self) -> None:
        panel = ProjectExplorerPanel(self.api)
        tree = panel.explorer

        # Find table and plot items in the tree
        table_elem_id = f"{self.result.id}:table:{self.table.id}"
        plot_elem_id = f"{self.result.id}:plot:{self.plot.id}"

        self.assertIn(table_elem_id, tree._item_map)
        self.assertIn(plot_elem_id, tree._item_map)

        # Verify analysis item itself is the config
        analysis_item = tree._item_map[self.config.config_id]
        tree.setCurrentItem(analysis_item)
        self.assertEqual(self.api.current_selection.get("kind"), "analysis_config")
        self.assertEqual(self.api.current_selection.get("config_id"), self.config.config_id)

        # Editor with this selection loads the configuration and results
        cfg_editor = AnalysisConfigPropertyEditor(self.api, self.api.current_selection)
        self.assertEqual(
            cfg_editor._property_text(cfg_editor.general_table, 0),
            "VLM Baseline Run",
        )
        self.assertEqual(
            cfg_editor._property_text(cfg_editor.parameters_table, 0),
            "20.0",
        )

        # Clicking table item triggers show_panel
        table_item = tree._item_map[table_elem_id]
        tree.setCurrentItem(table_item)
        self.assertIn("core:analysis-table", self.shown_panels)

        # Clicking plot item triggers show_panel
        plot_item = tree._item_map[plot_elem_id]
        tree.setCurrentItem(plot_item)
        self.assertIn("core:analysis-chart", self.shown_panels)

    def test_analysis_config_rename(self) -> None:
        panel = ProjectExplorerPanel(self.api)
        tree = panel.explorer
        ops = tree._ops

        analysis_item = tree._item_map[self.config.config_id]
        self.assertEqual(analysis_item.text(0), "VLM Baseline Run")

        # In Qt, editing item text emits itemChanged -> ops.rename_item automatically
        analysis_item.setText(0, "Renamed Polar Run")
        updated_cfg = self.api.get_analysis_config(self.config.config_id)
        self.assertIsNotNone(updated_cfg)
        self.assertEqual(updated_cfg.name, "Renamed Polar Run")

        # Test empty name restoration using ops.rename_item directly
        refreshed_item = tree._item_map[self.config.config_id]
        tree.blockSignals(True)
        refreshed_item.setText(0, "")
        tree.blockSignals(False)
        ops.rename_item(refreshed_item, 0)
        self.assertEqual(refreshed_item.text(0), "Renamed Polar Run")

    def test_analysis_config_delete_cascades_results(self) -> None:
        panel = ProjectExplorerPanel(self.api)
        tree = panel.explorer
        ops = tree._ops

        # Mock confirm_delete to True
        ops.confirm_delete = lambda title, details=None: True

        # Ensure config and result exist before delete
        self.assertIn(self.config.config_id, self.api.get_analysis_configs())
        self.assertIn(self.result.id, self.api.get_analysis_results())

        # Delete the main analysis config item
        analysis_item = tree._item_map[self.config.config_id]
        ops.delete_item(analysis_item)

        # Both config and associated results should be deleted
        self.assertNotIn(self.config.config_id, self.api.get_analysis_configs())
        self.assertNotIn(self.result.id, self.api.get_analysis_results())

    def test_analysis_operations_run(self) -> None:
        panel = ProjectExplorerPanel(self.api)
        ops = panel.explorer._ops

        run_called = []
        self.api.run_solver = (  # type: ignore
            lambda solver, on_complete=None, on_error=None, priority=None: run_called.append(solver)
        )

        class MockSolver:
            def __init__(self, config):
                self.config = config

        self.api.register_solver("vlm_solver", MockSolver)

        ops.run_analysis(self.config.config_id)
        self.assertEqual(len(run_called), 1)
        self.assertEqual(run_called[0].config.config_id, self.config.config_id)

    @staticmethod
    def horizontalHeaderOrientation():
        from PySide6.QtCore import Qt

        return Qt.Orientation.Horizontal


if __name__ == "__main__":
    unittest.main()
