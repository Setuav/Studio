"""Unit and integration tests for the Aerodynamics Plugin."""
from __future__ import annotations

import unittest
from setuav_studio.plugin_system import (
    ActionContribution,
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
)
from setuav_studio.plugins.aerodynamics.plugin import AerodynamicsPlugin
from setuav_studio.plugins.aerodynamics.engine.base import (
    AeroResult,
    AnalysisMethod,
    FlightCondition,
    PolarPoint,
    ReferenceValues,
    SweepType,
)
from tests._common import get_qapp


class AerodynamicsPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.panels: list[PanelContribution] = []
        self.workspaces: list[WorkspaceContribution] = []
        self.actions: list[ActionContribution] = []
        self.removed_panels: list[str] = []
        self.removed_workspaces: list[str] = []
        self.removed_actions: list[tuple[str, str]] = []

        self.api.set_panel_handler(
            self.panels.append,
            remove_handler=self.removed_panels.append,
        )
        self.api.set_workspace_handler(
            self.workspaces.append,
            remove_handler=self.removed_workspaces.append,
        )
        self.api.set_action_handler(
            self.actions.append,
            remove_handler=lambda menu, title: self.removed_actions.append((menu, title)),
        )

        self.plugin = AerodynamicsPlugin()

    def test_activation_registers_workspace_and_panels(self) -> None:
        self.plugin.activate(self.api)

        # Check Workspace
        workspace_ids = [w.id for w in self.workspaces]
        self.assertIn("studio.workspace.aerodynamics", workspace_ids)

        # Check Panels
        panel_ids = [p.id for p in self.panels]
        self.assertIn("aerodynamics.controls_dock", panel_ids)
        self.assertIn("aerodynamics.results_dock", panel_ids)
        self.assertIn("aerodynamics.charts_dock", panel_ids)
        self.assertNotIn("aerodynamics.aero_3d", panel_ids)
        self.assertTrue(any(
            action.menu == "Tools/Aerodynamics"
            and action.title == "AeroSandbox 3D Snapshot…"
            for action in self.actions
        ))

    def test_panel_factories_create_widgets_and_handle_results(self) -> None:
        self.plugin.activate(self.api)

        panels_by_id = {p.id: p for p in self.panels}
        controls_widget = panels_by_id["aerodynamics.controls_dock"].factory()
        results_widget = panels_by_id["aerodynamics.results_dock"].factory()
        charts_widget = panels_by_id["aerodynamics.charts_dock"].factory()

        self.assertIsNotNone(controls_widget)
        self.assertIsNotNone(results_widget)
        self.assertIsNotNone(charts_widget)
        sweep_modes = {
            controls_widget.combo_mode.itemText(index)
            for index in range(controls_widget.combo_mode.count())
        }
        self.assertNotIn("Airspeed Sweep", sweep_modes)
        self.assertNotIn("Altitude Sweep", sweep_modes)

        cond = FlightCondition(
            sweep_type=SweepType.DUAL_ALPHA_BETA,
            alpha=2.0,
            beta=0.0,
            alpha_steps=2,
            beta_steps=2,
        )
        dummy_result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            polar_points=[
                PolarPoint(alpha=-4.0, cl=-0.1, cd=0.012, cm=0.01, cy=0.0, cl_roll=0.0, cn=0.0, cl_over_cd=-8.3, raw={"_sweep_group": "alpha"}),
                PolarPoint(alpha=8.0, cl=1.1, cd=0.055, cm=-0.09, cy=0.0, cl_roll=0.0, cn=0.0, cl_over_cd=20.0, raw={"_sweep_group": "alpha"}),
                PolarPoint(alpha=2.0, beta=-6.0, cl=0.5, cd=0.02, cm=-0.04, cy=-0.15, cl_roll=-0.02, cn=0.03, cl_over_cd=25.0, raw={"_sweep_group": "beta"}),
                PolarPoint(alpha=2.0, beta=6.0, cl=0.5, cd=0.02, cm=-0.04, cy=0.15, cl_roll=0.02, cn=-0.03, cl_over_cd=25.0, raw={"_sweep_group": "beta"}),
            ],
            cl_max=1.1,
            cl_max_alpha=8.0,
            cd_min=0.012,
            ld_max=25.0,
            ld_max_alpha=4.0,
            reference=ReferenceValues(s_ref=0.6, b_ref=1.8, c_ref=0.33),
            reynolds=450000.0,
            oswald_efficiency=0.85,
            condition=cond,
        )

        self.plugin._handle_analysis_result(dummy_result)

        # Verify results dock populated
        self.assertEqual(results_widget.results_list.count(), 1)
        self.assertIs(results_widget.current_result, dummy_result)
        self.assertEqual(results_widget.detail_table.rowCount(), 4)
        self.assertEqual(results_widget.tab_widget.count(), 2)

        # Verify charts populated
        self.assertGreater(len(charts_widget.chart_lift.chart.series()), 0)
        self.assertGreater(len(charts_widget.chart_polar.chart.series()), 0)
        self.assertGreater(len(charts_widget.chart_moment.chart.series()), 0)
        self.assertGreater(len(charts_widget.chart_ld.chart.series()), 0)

        # Verify Dynamic Chart mode switching
        charts_widget.combo_view_mode.setCurrentIndex(1)  # Longitudinal Stability
        self.assertIn("Pitching Moment", charts_widget.chart_lift.chart.title())
        charts_widget.combo_view_mode.setCurrentIndex(2)  # Lateral-Directional
        self.assertIn("Sideforce", charts_widget.chart_lift.chart.title())
        charts_widget.combo_view_mode.setCurrentIndex(3)  # Forces & Moments
        self.assertIn("Lift Force", charts_widget.chart_lift.chart.title())

        # A second result is appended and becomes active. Selecting the first
        # history entry restores both tables and charts to that result.
        second_result = AeroResult(
            method=AnalysisMethod.VLM,
            engine_name="AeroSandbox",
            polar_points=[
                PolarPoint(alpha=3.0, cl=0.4, cd=0.02, cm=-0.02, cl_over_cd=20.0),
            ],
            cl_max=0.4,
            cl_max_alpha=3.0,
            cd_min=0.02,
            ld_max=20.0,
            ld_max_alpha=3.0,
            reference=ReferenceValues(s_ref=0.6, b_ref=1.8, c_ref=0.33),
            condition=FlightCondition(alpha=3.0, alpha_steps=1, sweep_steps=1),
        )
        self.plugin._handle_analysis_result(second_result)
        self.assertEqual(results_widget.results_list.count(), 2)
        self.assertIs(results_widget.current_result, second_result)
        self.assertEqual(results_widget.detail_table.rowCount(), 1)

        results_widget.results_list.setCurrentRow(0)
        self.assertIs(results_widget.current_result, dummy_result)
        self.assertEqual(results_widget.detail_table.rowCount(), 4)
        self.assertEqual(charts_widget.chart_lift.chart.series()[0].count(), 2)

        results_widget.delete_result_button.click()
        self.assertEqual(results_widget.results_list.count(), 1)
        self.assertIs(results_widget.current_result, second_result)
        self.assertEqual(results_widget.detail_table.rowCount(), 1)
        self.assertEqual(charts_widget.chart_lift.chart.series()[0].count(), 1)

        results_widget.delete_result_button.click()
        self.assertEqual(results_widget.results_list.count(), 0)
        self.assertIsNone(results_widget.current_result)
        self.assertEqual(results_widget.detail_table.rowCount(), 0)
        self.assertEqual(charts_widget.combo_view_mode.count(), 0)

    def test_deactivation_cleans_up(self) -> None:
        self.plugin.activate(self.api)
        self.plugin.deactivate(self.api)

        self.assertIn("aerodynamics.controls_dock", self.removed_panels)
        self.assertIn("aerodynamics.results_dock", self.removed_panels)
        self.assertIn("aerodynamics.charts_dock", self.removed_panels)
        self.assertNotIn("aerodynamics.aero_3d", self.removed_panels)
        self.assertIn(
            ("Tools/Aerodynamics", "AeroSandbox 3D Snapshot…"),
            self.removed_actions,
        )
        self.assertIn("studio.workspace.aerodynamics", self.removed_workspaces)
