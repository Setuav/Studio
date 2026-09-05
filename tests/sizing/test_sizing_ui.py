"""Unit tests for the preliminary sizing UI docks and plugin integration."""

from __future__ import annotations

import sys
import unittest

from PySide6.QtWidgets import QApplication

from plugins.sizing import SizingPlugin
from plugins.sizing.engine.solver import compute_matching_chart
from plugins.sizing.engine.weight import converge_sizing
from plugins.sizing.presets import CARGO_PRESET, SURVEILLANCE_PRESET
from plugins.sizing.ui.matching_chart import SizingChartDock
from plugins.sizing.ui.requirements_dock import SizingRequirementsDock
from plugins.sizing.ui.results_dock import SizingResultsDock
from setuav_studio.api import StudioAPI
from setuav_studio.ui.widget.table import ExpressionPropertyCell
from setuav_studio.units import get_unit_manager


class TestSizingUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_requirements_dock(self) -> None:
        dock = SizingRequirementsDock()
        self.assertIsNotNone(dock.mission_table)
        self.assertIsNotNone(dock.field_table)
        self.assertIsNotNone(dock.aero_table)
        self.assertIsNotNone(dock.powertrain_table)

        # Verify cells are ExpressionPropertyCells equipped with fx buttons
        self.assertIsInstance(dock.cell_payload, ExpressionPropertyCell)
        self.assertIsNotNone(dock.cell_payload.fx_button)
        self.assertTrue(dock.cell_payload.fx_button.isVisibleTo(dock.cell_payload))

        # Verify initial values match surveillance preset
        mission, aero, _battery = dock.get_current_configuration()
        self.assertAlmostEqual(mission.payload_mass_kg, SURVEILLANCE_PRESET.mission.payload_mass_kg)
        self.assertAlmostEqual(aero.aspect_ratio, SURVEILLANCE_PRESET.aero.aspect_ratio)

        # Test formula expression input
        dock.cell_payload.setText("=1000 + 500")
        self.assertAlmostEqual(dock.cell_payload.value(), 1500.0)
        updated_mission, _, _ = dock.get_current_configuration()
        self.assertAlmostEqual(updated_mission.payload_mass_kg, 1.5)

        # Test preset switching
        dock._apply_preset(CARGO_PRESET.id)
        cargo_m, cargo_a, _cargo_b = dock.get_current_configuration()
        self.assertAlmostEqual(cargo_m.payload_mass_kg, CARGO_PRESET.mission.payload_mass_kg)
        self.assertAlmostEqual(cargo_a.aspect_ratio, CARGO_PRESET.aero.aspect_ratio)

    def test_chart_dock(self) -> None:
        chart_dock = SizingChartDock()
        mission = SURVEILLANCE_PRESET.mission
        aero = SURVEILLANCE_PRESET.aero

        analysis = compute_matching_chart(mission, aero)
        chart_dock.chart_widget.plot_analysis(analysis)

        self.assertGreater(len(chart_dock.chart_widget.chart.series()), 5)

        # Toggle view mode
        chart_dock._on_mode_changed(1)  # T/W mode
        self.assertEqual(chart_dock.chart_widget._view_mode, "tw")

        chart_dock._on_mode_changed(0)  # P/W mode
        self.assertEqual(chart_dock.chart_widget._view_mode, "pw")

    def test_results_dock(self) -> None:
        um = get_unit_manager()
        orig_mass_unit = um.get_display_unit("mass")
        try:
            um.set_display_unit("mass", "kg")
            um.units_changed.emit()

            results_dock = SizingResultsDock()
            mission = SURVEILLANCE_PRESET.mission
            aero = SURVEILLANCE_PRESET.aero

            res = converge_sizing(
                mission=mission,
                aero=aero,
                design_wing_loading_pa=85.0,
                design_power_loading_wn=12.0,
            )
            results_dock.set_results(res)

            mtow_item = results_dock.summary_table.item(0, 1)
            self.assertIsNotNone(mtow_item)
            assert mtow_item is not None
            self.assertIn("kg", mtow_item.text())

            energy_item = results_dock.battery_table.item(0, 1)
            self.assertIsNotNone(energy_item)
            assert energy_item is not None
            self.assertIn("Wh", energy_item.text())

            self.assertGreater(results_dock.motor_table.rowCount(), 0)
            self.assertGreater(results_dock.prop_table.rowCount(), 0)

            # Test dynamic unit update via UnitManager signal
            um.set_display_unit("mass", "g")
            um.units_changed.emit()

            mtow_item_g = results_dock.summary_table.item(0, 1)
            self.assertIsNotNone(mtow_item_g)
            assert mtow_item_g is not None
            self.assertIn("g", mtow_item_g.text())
            self.assertNotIn("kg", mtow_item_g.text())
        finally:
            um.set_display_unit("mass", orig_mass_unit)
            um.units_changed.emit()

    def test_plugin_lifecycle_and_contributions(self) -> None:
        from typing import Any, cast

        api = StudioAPI()
        panels = []
        workspaces = []
        api._host.bind_panel_handlers(panels.append)
        api._host.bind_workspace_handlers(workspaces.append)

        plugin = SizingPlugin()
        plugin.activate(cast(Any, api))

        # Check workspace registered
        sizing_ws = next((w for w in workspaces if w.id == "studio.workspace.sizing"), None)
        self.assertIsNotNone(sizing_ws)
        assert sizing_ws is not None
        self.assertEqual(sizing_ws.title, "Sizing")

        # Check panels registered
        panel_ids = [p.id for p in panels]
        self.assertIn("sizing.requirements_dock", panel_ids)
        self.assertIn("sizing.chart_dock", panel_ids)
        self.assertIn("sizing.results_dock", panel_ids)


if __name__ == "__main__":
    unittest.main()
