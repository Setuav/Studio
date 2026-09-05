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

    def test_wizard_card_and_grid(self) -> None:
        from plugins.sizing.ui.wizard_dialog import WizardCardGrid, WizardOption, WizardOptionCard

        opt1 = WizardOption(
            id="opt1",
            title="Option 1",
            subtitle="Sub 1",
            badge="Badge 1",
            details=["Pro 1", "Con 1"],
        )
        opt2 = WizardOption(id="opt2", title="Option 2", subtitle="Sub 2")

        card = WizardOptionCard(opt1)
        self.assertFalse(card.is_selected())
        card.set_selected(True)
        self.assertTrue(card.is_selected())

        grid = WizardCardGrid([opt1, opt2])
        self.assertEqual(grid.selected_id(), "opt1")

        received: list[str] = []
        grid.selection_changed.connect(received.append)
        grid.select("opt2")
        self.assertEqual(grid.selected_id(), "opt2")
        self.assertIn("opt2", received)

    def test_sizing_wizard_dialog_flow(self) -> None:
        from plugins.sizing.ui.wizard_dialog import SizingWizardDialog

        dlg = SizingWizardDialog()
        self.assertEqual(dlg.stack.currentIndex(), 0)
        self.assertFalse(dlg.btn_back.isEnabled())

        # Test stepping forward
        dlg.next_step()
        self.assertEqual(dlg.stack.currentIndex(), 1)
        self.assertTrue(dlg.btn_back.isEnabled())

        # Navigate through all steps
        for step in range(2, dlg.stack.count()):
            dlg.go_to_step(step)
            self.assertEqual(dlg.stack.currentIndex(), step)

        # On last step, button text changes
        self.assertIn("Başlat", dlg.btn_next.text())

        # Step back
        dlg.prev_step()
        self.assertEqual(dlg.stack.currentIndex(), dlg.stack.count() - 2)

        # Test changing inputs
        dlg.go_to_step(0)
        dlg.input_payload.setText("1200")
        self.assertAlmostEqual(dlg.state["payload_kg"], 1.2)
        self.assertEqual(dlg.sum_payload.text(), "1.20 kg")

        dlg.input_endurance.setText("60")
        self.assertAlmostEqual(dlg.state["endurance_min"], 60.0)

        # Test card selections
        dlg.grid_arch.select("flying_wing")
        self.assertEqual(dlg.state["config_type"], "flying_wing")
        self.assertEqual(dlg.sum_config.text(), "Uçan Kanat")

        dlg.grid_wing_loc.select("low")
        self.assertEqual(dlg.state["wing_location"], "low")
        self.assertEqual(dlg.sum_wing_loc.text(), "Alttan")

        dlg.grid_wing_plan.select("swept")
        self.assertEqual(dlg.state["wing_planform"], "swept")
        self.assertEqual(dlg.sum_planform.text(), "Ok Açılı")

        dlg.grid_tail.select("v_tail")
        self.assertEqual(dlg.state["tail_type"], "v_tail")
        self.assertEqual(dlg.sum_tail.text(), "V-Kuyruk")

        dlg.grid_prop.select("twin")
        self.assertEqual(dlg.state["propulsion_layout"], "twin")
        self.assertEqual(dlg.sum_prop.text(), "Çift Motor")

        dlg.grid_battery.select("li_ion_18650")
        self.assertEqual(dlg.state["battery_chemistry"], "li_ion_18650")
        self.assertIn("18650", dlg.sum_battery.text())

    def test_requirements_dock_apply_wizard_state(self) -> None:
        dock = SizingRequirementsDock()
        self.assertIsNotNone(dock.wizard_btn)

        state = {
            "payload_kg": 2.5,
            "endurance_min": 75.0,
            "cruise_speed_ms": 22.0,
            "cruise_alt_m": 250.0,
            "stall_speed_ms": 14.0,
            "takeoff_run_m": 40.0,
            "climb_rate_ms": 4.5,
            "battery_chemistry": "li_ion_21700",
        }
        dock._apply_wizard_state(state)
        mission, _aero, battery = dock.get_current_configuration()
        self.assertAlmostEqual(mission.payload_mass_kg, 2.5)
        self.assertAlmostEqual(mission.endurance_min, 75.0)
        self.assertAlmostEqual(mission.v_cruise_mps, 22.0)
        self.assertAlmostEqual(mission.cruise_altitude_m, 250.0)
        self.assertAlmostEqual(mission.v_stall_mps, 14.0)
        self.assertAlmostEqual(mission.ground_roll_takeoff_m, 40.0)
        self.assertAlmostEqual(mission.roc_mps, 4.5)
        self.assertAlmostEqual(battery.specific_energy_wh_kg, 260.0)


if __name__ == "__main__":
    unittest.main()
