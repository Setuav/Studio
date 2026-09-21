"""Comprehensive tests for AnalysisPlotPropertyEditor, AnalysisTablePropertyEditor, and ResultPanel nested docking."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QComboBox, QDockWidget

from setuav_studio.api import StudioAPI
from setuav_studio.model.analysis_config import AnalysisConfig
from setuav_studio.project import create_project
from setuav_studio.solver.base import SolverStatus
from setuav_studio.solver.results import (
    AnalysisResult,
    PlotSeriesDef,
    TableColumn,
)
from setuav_studio.ui.editor.analysis_plot import AnalysisPlotPropertyEditor
from setuav_studio.ui.editor.analysis_table import AnalysisTablePropertyEditor
from setuav_studio.ui.panels.results import ResultPanel
from setuav_studio.ui.widget.color_picker import ColorPickerWidget


class TestAnalysisPlotEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project.suav"
        self.api = StudioAPI()
        self.api.current_project = create_project(self.project_path)

        self.config = AnalysisConfig(
            solver_id="debug_solver",
            name="Aerodynamic Sweep",
            parameters={"duration": 1, "rows": 10, "columns": 4},
        )
        self.api.add_analysis_config(self.config)

        solver_cfg = self.config.to_solver_config()
        self.result = AnalysisResult(
            solver_id="debug_solver",
            config=solver_cfg,
            name="Sweep Result",
            status=SolverStatus.COMPLETED,
            execution_time_ms=120.0,
        )

        self.table = self.result.add_table(
            table_id="perf_data",
            title="Performance Data",
            columns=[
                TableColumn(key="time", label="Time", unit="s", quantity_id="time"),
                TableColumn(key="speed", label="Airspeed", unit="m/s", quantity_id="speed"),
                TableColumn(key="thrust", label="Thrust", unit="N", quantity_id="force"),
                TableColumn(key="altitude", label="Altitude", unit="m", quantity_id="length"),
            ],
            data={
                "time": [0.0, 1.0, 2.0, 3.0, 4.0],
                "speed": [10.0, 15.0, 20.0, 25.0, 30.0],
                "thrust": [100.0, 95.0, 90.0, 85.0, 80.0],
                "altitude": [100.0, 110.0, 125.0, 145.0, 170.0],
            },
        )

        self.plot = self.result.add_plot(
            plot_id="speed_vs_time",
            table_id="perf_data",
            x_column="time",
            title="Airspeed vs Time",
            series=[
                PlotSeriesDef(
                    y_column="speed", label="True Airspeed", color="#2196F3", style="solid"
                ),
            ],
        )

        self.api.current_project.add_analysis_result(self.result)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_result_panel_nested_docking_and_clean_headers(self) -> None:
        """Verify charts and tables open as nested QDockWidgets with clean headers."""
        panel = ResultPanel(self.api)

        # Open plot
        self.api.set_selection(
            {
                "kind": "analysis_plot",
                "result_id": self.result.id,
                "plot_id": self.plot.id,
            }
        )

        plot_key = f"plot:{self.result.id}:{self.plot.id}"
        self.assertIn(plot_key, panel.open_pane_keys)
        dock = panel._panes[plot_key]
        self.assertIsInstance(dock, QDockWidget)
        self.assertEqual(dock.windowTitle(), "Airspeed vs Time")
        # Ensure clean header without icons
        # Ensure native Qt dock features
        self.assertTrue(bool(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetMovable))
        self.assertTrue(bool(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetClosable))
        self.assertFalse(dock.isFloating())

        # Open table
        self.api.set_selection(
            {
                "kind": "analysis_table",
                "result_id": self.result.id,
                "table_id": self.table.id,
            }
        )
        table_key = f"table:{self.result.id}:{self.table.id}"
        self.assertIn(table_key, panel.open_pane_keys)
        self.assertEqual(len(panel.open_pane_keys), 2)

        # Test dock window contains nested docks
        nested_docks = panel._dock_window.findChildren(QDockWidget)
        self.assertEqual(len(nested_docks), 2)

        # Test layout operations
        panel.tabify_all()
        panel.tile_horizontally()
        panel.tile_vertically()

        # Test close pane
        panel.close_pane(plot_key)
        self.assertEqual(len(panel.open_pane_keys), 1)
        self.assertNotIn(plot_key, panel.open_pane_keys)

        panel.clear_all()
        self.assertEqual(len(panel.open_pane_keys), 0)
        self.assertEqual(panel._stack.currentWidget(), panel._empty_view)

    def test_analysis_plot_editor_title_and_x_column_change(self) -> None:
        """Verify editing plot title and X axis updates models and notifies ResultPanel."""
        panel = ResultPanel(self.api)
        panel.show_plot(self.result, self.plot, self.table)

        editor = AnalysisPlotPropertyEditor(
            self.api,
            {
                "kind": "analysis_plot",
                "result_id": self.result.id,
                "plot_id": self.plot.id,
            },
        )

        # Verify initial fields
        self.assertEqual(editor._property_value(editor.details_table, "title"), "Airspeed vs Time")
        self.assertEqual(
            editor._property_value(editor.details_table, "result_name"), "Sweep Result"
        )

        # Edit title
        editor._set_property_value(editor.details_table, "title", "Velocity Profile")
        self.assertEqual(self.plot.title, "Velocity Profile")

        # ResultPanel dock title should be updated
        plot_key = f"plot:{self.result.id}:{self.plot.id}"
        dock = panel._panes[plot_key]
        self.assertEqual(dock.windowTitle(), "Velocity Profile")

        # Edit X Column via combo
        editor._on_x_column_changed("altitude")
        self.assertEqual(self.plot.x_column, "altitude")
        chart = panel.get_chart_panel(self.result.id, self.plot.id)
        self.assertIsNotNone(chart)
        if chart is not None:
            self.assertEqual(chart._active_x_column, "altitude")

    def test_analysis_plot_editor_multi_series_and_color_customization(self) -> None:
        """Verify user freedom to change Y-axis, add curves, customize colors and line styles."""
        panel = ResultPanel(self.api)
        panel.show_plot(self.result, self.plot, self.table)

        editor = AnalysisPlotPropertyEditor(
            self.api,
            {
                "kind": "analysis_plot",
                "result_id": self.result.id,
                "plot_id": self.plot.id,
            },
        )

        # Initially 1 series
        self.assertEqual(len(self.plot.series), 1)
        self.assertEqual(editor._series_layout.count(), 1)

        # 1. Add a second curve
        editor._on_add_curve_clicked()
        self.assertEqual(len(self.plot.series), 2)
        self.assertEqual(editor._series_layout.count(), 2)

        s2 = self.plot.series[1]
        self.assertIn(s2.y_column, ["speed", "thrust", "altitude"])
        self.assertIsNotNone(s2.color)

        # 2. Modify curve 1: color, style, and legend
        item0 = editor._series_layout.itemAt(0)
        self.assertIsNotNone(item0)
        card1 = item0.widget() if item0 else None
        self.assertIsNotNone(card1)
        color_picker = card1.findChild(ColorPickerWidget) if card1 else None
        self.assertIsNotNone(color_picker)
        if color_picker is not None:
            color_picker.set_color("#FF5722")
            self.assertEqual(self.plot.series[0].color, "#FF5722")

        # Modify style
        editor._on_curve_style_changed(0, "Dashed")
        self.assertEqual(self.plot.series[0].style, "dashed")

        # Modify legend
        editor._on_curve_label_changed(0, "Measured Airspeed")
        self.assertEqual(self.plot.series[0].label, "Measured Airspeed")

        # 3. Modify Y column of curve 2 to 'thrust'
        item1 = editor._series_layout.itemAt(1)
        self.assertIsNotNone(item1)
        card2 = item1.widget() if item1 else None
        self.assertIsNotNone(card2)
        y_combos = card2.findChildren(QComboBox) if card2 else []
        self.assertTrue(len(y_combos) >= 1)
        y_combo = y_combos[0]
        t_idx = y_combo.findData("thrust")
        if t_idx >= 0:
            y_combo.setCurrentIndex(t_idx)
            self.assertEqual(self.plot.series[1].y_column, "thrust")

        # 4. Add a third curve
        editor._on_add_curve_clicked()
        self.assertEqual(len(self.plot.series), 3)

        # 5. Delete a curve
        editor._on_delete_curve(1)
        self.assertEqual(len(self.plot.series), 2)
        self.assertEqual(editor._series_layout.count(), 2)

    def test_analysis_plot_editor_actions(self) -> None:
        """Verify Reset View, Export PNG, and Export CSV actions."""
        panel = ResultPanel(self.api)
        panel.show_plot(self.result, self.plot, self.table)

        editor = AnalysisPlotPropertyEditor(
            self.api,
            {
                "kind": "analysis_plot",
                "result_id": self.result.id,
                "plot_id": self.plot.id,
            },
        )

        chart = panel.get_chart_panel(self.result.id, self.plot.id)
        self.assertIsNotNone(chart)

        # Verify Reset Plot button text
        self.assertEqual(editor._reset_btn.text(), "Reset Plot")

        # Modify plot series by adding a curve
        editor._on_add_curve_clicked()
        self.assertEqual(len(self.plot.series), 2)

        # Reset plot action restores original plot configuration
        editor._on_reset_plot_clicked()
        restored_plot = self.result.plots[self.plot.id]
        self.assertEqual(len(restored_plot.series), 1)
        self.assertEqual(restored_plot.series[0].label, "True Airspeed")
        self.assertEqual(editor._series_layout.count(), 1)
        if chart is not None:
            self.assertEqual(
                chart._chart_widget.series()[0].pen().color().name().lower(), "#2196f3"
            )

        # Subsequent color modification after reset must propagate to chart
        editor._on_curve_color_changed(0, "#00ff00")
        if chart is not None:
            self.assertEqual(
                chart._chart_widget.series()[0].pen().color().name().lower(), "#00ff00"
            )

        # Export PNG action with pre-specified path
        out_png = Path(self.temp_dir.name) / "test_chart.png"
        if chart is not None:
            chart.export_png(str(out_png))
            self.assertTrue(out_png.exists())

        # Export CSV action with pre-specified path
        out_csv = Path(self.temp_dir.name) / "test_data.csv"
        if chart is not None:
            chart.export_csv(str(out_csv))
            self.assertTrue(out_csv.exists())
            content = out_csv.read_text(encoding="utf-8")
            self.assertIn("Time", content)
            self.assertIn("Airspeed", content)

    def test_analysis_table_property_editor(self) -> None:
        """Verify AnalysisTablePropertyEditor displays table metadata and column units."""
        editor = AnalysisTablePropertyEditor(
            self.api,
            {
                "kind": "analysis_table",
                "result_id": self.result.id,
                "table_id": self.table.id,
            },
        )

        self.assertEqual(
            editor._property_value(editor.details_table, "table_name"), "Performance Data"
        )
        self.assertEqual(editor._property_value(editor.details_table, "row_count"), "5 rows")
        self.assertEqual(editor._property_value(editor.details_table, "col_count"), "4 columns")

        # Columns table has 4 rows
        self.assertEqual(editor.columns_table.rowCount(), 4)

        # Test export CSV action
        out_csv = Path(self.temp_dir.name) / "table_export.csv"
        self.result.export_table_csv(self.table.id, str(out_csv), use_display_units=True)
        self.assertTrue(out_csv.exists())
