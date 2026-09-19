"""Tests for AnalysisResult, SummaryItem, TableDefinition, PlotDefinition, and export utilities."""

import json
import tempfile
import unittest
from pathlib import Path

from setuav_studio.solver.base import SolverConfig, SolverStatus
from setuav_studio.solver.results import (
    AnalysisResult,
    PlotDefinition,
    PlotSeriesDef,
    SummaryItem,
    TableColumn,
    TableDefinition,
)
from setuav_studio.units import get_unit_manager


class TestAnalysisResultComponents(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SolverConfig(solver_id="vlm_solver", name="VLM Baseline")

    def test_summary_item_and_units(self) -> None:
        # Auto-label from key
        item = SummaryItem(key="max_lift_to_drag", value=18.4)
        self.assertEqual(item.label, "Max Lift To Drag")
        self.assertIsNone(item.quantity_id)

        # Quantity resolution from unit
        speed_item = SummaryItem(key="cruise_speed", value=25.0, unit="m/s")
        self.assertEqual(speed_item.quantity_id, "velocity")

        disp_val, disp_unit = speed_item.display_value_and_unit()
        self.assertEqual(disp_val, 25.0)
        self.assertEqual(disp_unit, "m/s")

        # Serialization round-trip
        d = speed_item.to_dict()
        restored = SummaryItem.from_dict(d)
        self.assertEqual(restored.key, speed_item.key)
        self.assertEqual(restored.value, speed_item.value)
        self.assertEqual(restored.unit, speed_item.unit)
        self.assertEqual(restored.quantity_id, speed_item.quantity_id)

    def test_table_column_and_header(self) -> None:
        col_alpha = TableColumn(key="alpha", label="AoA", unit="deg")
        self.assertEqual(col_alpha.quantity_id, "angle")
        self.assertEqual(col_alpha.header_text(use_display_units=False), "AoA [deg]")

        # UnitManager display setting test
        um = get_unit_manager()
        original_disp = um.get_display_unit("angle")
        try:
            um.set_display_unit("angle", "rad")
            self.assertEqual(col_alpha.header_text(use_display_units=True), "AoA [rad]")
        finally:
            um.set_display_unit("angle", original_disp)

        # Dimensionless column
        col_cl = TableColumn(key="cl", label="Lift Coefficient")
        self.assertEqual(col_cl.header_text(), "Lift Coefficient")

        # Serialization round-trip
        col_dict = col_alpha.to_dict()
        restored_col = TableColumn.from_dict(col_dict)
        self.assertEqual(restored_col.key, "alpha")
        self.assertEqual(restored_col.label, "AoA")
        self.assertEqual(restored_col.unit, "deg")

    def test_table_definition_columnar_and_rows(self) -> None:
        cols = [
            TableColumn(key="alpha", label="Alpha", unit="deg"),
            TableColumn(key="cl", label="CL"),
            TableColumn(key="cd", label="CD"),
        ]
        data = {
            "alpha": [0.0, 2.0, 4.0],
            "cl": [0.2, 0.4, 0.6],
            "cd": [0.015, 0.018, 0.025],
        }
        table = TableDefinition(id="polar", title="Polar Curve", columns=cols, data=data)

        self.assertEqual(table.row_count(), 3)
        self.assertEqual(len(table), 3)
        self.assertEqual(table.get_column("alpha"), [0.0, 2.0, 4.0])

        # Row indexing and iteration
        row_0 = table[0]
        self.assertEqual(row_0["alpha"], 0.0)
        self.assertEqual(row_0["cl"], 0.2)

        rows = list(table)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["cd"], 0.025)

        # CSV Export
        csv_str = table.to_csv()
        lines = [line.strip() for line in csv_str.strip().splitlines()]
        self.assertEqual(lines[0], "Alpha [deg],CL,CD")
        self.assertEqual(lines[1], "0.0,0.2,0.015")
        self.assertEqual(lines[2], "2.0,0.4,0.018")
        self.assertEqual(lines[3], "4.0,0.6,0.025")

        # Serialization round-trip
        t_dict = table.to_dict()
        restored = TableDefinition.from_dict(t_dict)
        self.assertEqual(restored.id, "polar")
        self.assertEqual(restored.title, "Polar Curve")
        self.assertEqual(restored.get_column("cl"), [0.2, 0.4, 0.6])

    def test_plot_definition_derived_from_table(self) -> None:
        table = TableDefinition(
            id="aero_data",
            columns=[
                TableColumn(key="alpha", label="Angle of Attack", unit="deg"),
                TableColumn(key="cl", label="Lift Coefficient"),
                TableColumn(key="cd", label="Drag Coefficient"),
            ],
            data={
                "alpha": [-2.0, 0.0, 2.0],
                "cl": [-0.1, 0.2, 0.5],
                "cd": [0.012, 0.010, 0.014],
            },
        )

        plot = PlotDefinition(
            id="cl_vs_alpha",
            title="Lift Curve",
            table_id="aero_data",
            x_column="alpha",
            series=[
                PlotSeriesDef(y_column="cl", label="CL (Inviscid)", style="solid"),
            ],
        )

        label, unit = plot.get_x_label_and_unit(table)
        self.assertEqual(label, "Angle of Attack")
        self.assertEqual(unit, "deg")

        # Serialization round-trip
        p_dict = plot.to_dict()
        restored = PlotDefinition.from_dict(p_dict)
        self.assertEqual(restored.id, "cl_vs_alpha")
        self.assertEqual(restored.table_id, "aero_data")
        self.assertEqual(restored.x_column, "alpha")
        self.assertEqual(len(restored.series), 1)
        self.assertEqual(restored.series[0].y_column, "cl")
        self.assertEqual(restored.series[0].style, "solid")

    def test_analysis_result_builders_and_exports(self) -> None:
        result = AnalysisResult(
            solver_id="vlm",
            config=self.config,
            name="Test Result",
            status=SolverStatus.COMPLETED,
            execution_time_ms=150.0,
        )

        # Add summary items
        result.add_summary("cl_max", 1.45, label="Max CL")
        result.add_summary("stall_speed", 14.2, label="Stall Speed", unit="m/s")
        self.assertIn("cl_max", result.summary)
        self.assertEqual(result.summary["stall_speed"].unit, "m/s")

        # Add table
        table = result.add_table(
            table_id="sweep",
            title="AoA Sweep",
            columns=[
                ("alpha", "AoA", "deg"),
                ("cl", "Lift Coeff", ""),
                ("cd", "Drag Coeff", ""),
            ],
            data={
                "alpha": [0.0, 5.0, 10.0],
                "cl": [0.2, 0.7, 1.2],
                "cd": [0.015, 0.035, 0.085],
            },
        )
        self.assertEqual(len(table), 3)

        # Add plot linked to table
        plot = result.add_plot(
            plot_id="polar_plot",
            table_id="sweep",
            x_column="cd",
            y_columns=["cl"],
            title="Drag Polar",
        )
        self.assertEqual(plot.table_id, "sweep")
        self.assertEqual(plot.x_column, "cd")
        self.assertEqual(plot.series[0].y_column, "cl")

        # Export testing via temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Export all CSVs
            exported_csvs = result.export_csv(temp_path)
            self.assertEqual(len(exported_csvs), 2)  # summary.csv and sweep.csv

            summary_csv = temp_path / "summary.csv"
            self.assertTrue(summary_csv.is_file())
            summary_content = summary_csv.read_text(encoding="utf-8")
            self.assertIn("cl_max,Max CL,1.45,", summary_content)
            self.assertIn("stall_speed,Stall Speed,14.2,m/s", summary_content)

            sweep_csv = temp_path / "sweep.csv"
            self.assertTrue(sweep_csv.is_file())
            sweep_content = sweep_csv.read_text(encoding="utf-8")
            self.assertIn("AoA [deg],Lift Coeff,Drag Coeff", sweep_content)
            self.assertIn("0.0,0.2,0.015", sweep_content)

            # Export JSON
            json_path = temp_path / "result.json"
            result.export_json(json_path)
            self.assertTrue(json_path.is_file())

            # Verify JSON can be deserialized back to an identical AnalysisResult
            with open(json_path, encoding="utf-8") as f:
                loaded_dict = json.load(f)
            restored = AnalysisResult.from_dict(loaded_dict)
            self.assertEqual(restored.id, result.id)
            self.assertEqual(restored.solver_id, result.solver_id)
            self.assertEqual(restored.status, SolverStatus.COMPLETED)
            self.assertEqual(len(restored.summary), 2)
            self.assertEqual(len(restored.tables), 1)
            self.assertEqual(len(restored.plots), 1)
            self.assertEqual(restored.tables["sweep"][1]["cl"], 0.7)


if __name__ == "__main__":
    unittest.main()
