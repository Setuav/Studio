"""Unit and integration tests for the Aerodynamics Plugin."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QMenu, QMessageBox

from setuav_studio.plugin_system import (
    ActionContribution,
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
)
from setuav_studio.plugins.aerodynamics.airfoil_analysis_tool import (
    AirfoilAnalysisToolWindow,
)
from setuav_studio.plugins.aerodynamics.analysis_store import (
    RESULTS_VERSION,
    analysis_entries,
    load_analysis_result,
    migrate_analysis_extension,
)
from setuav_studio.plugins.aerodynamics.engine.base import (
    AeroResult,
    AnalysisMethod,
    ControlChannelAnalysis,
    FlightCondition,
    MultiDimensionalSweepResult,
    PolarPoint,
    ReferenceValues,
    SweepType,
    SweepVariable,
)
from setuav_studio.plugins.aerodynamics.engine.stability_models import (
    StabilityDerivatives,
)
from setuav_studio.plugins.aerodynamics.plugin import AerodynamicsPlugin
from setuav_studio.plugins.aerodynamics.results_dock import AeroResultsDock
from setuav_studio.plugins.core.ui.project_explorer import ProjectExplorer
from setuav_studio.project import ProjectDocument
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

        self.api._host.bind_panel_handlers(
            self.panels.append,
            remove_handler=self.removed_panels.append,
        )
        self.api._host.bind_workspace_handlers(
            self.workspaces.append,
            remove_handler=self.removed_workspaces.append,
        )
        self.api._host.bind_action_handlers(
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
        self.assertTrue(
            any(
                action.menu == "Tools/Aerodynamics" and action.title == "AeroSandbox 3D Snapshot…"
                for action in self.actions
            )
        )
        self.assertTrue(
            any(
                action.menu == "Tools/Aerodynamics" and action.title == "Airfoil Analysis…"
                for action in self.actions
            )
        )

    def test_legacy_result_schema_migrates_to_current_model(self) -> None:
        legacy_point = PolarPoint(
            alpha=2.0,
            beta=3.0,
            cl=0.4,
            cd=0.03,
            converged=True,
        ).to_dict()
        extension = {
            "results_version": 1,
            "results": [
                {
                    "id": "legacy",
                    "result": {
                        "method": "comprehensive",
                        "engine_name": "AeroSandbox",
                        "polar_points": [],
                        "beta_polar_points": [legacy_point],
                        "solver_results": {"vlm": [legacy_point]},
                    },
                }
            ],
        }

        self.assertTrue(migrate_analysis_extension(extension))
        self.assertEqual(extension["results_version"], RESULTS_VERSION)
        payload = extension["results"][0]["result"]
        self.assertEqual(payload["method"], "aero_buildup")
        self.assertEqual(len(payload["polar_points"]), 1)
        self.assertNotIn("beta_polar_points", payload)
        self.assertNotIn("solver_results", payload)
        restored = AeroResult.from_dict(payload)
        self.assertEqual(restored.method, AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(restored.polar_points[0].beta, 3.0)

        self.plugin.activate(self.api)
        project = ProjectDocument(
            path=Path("legacy-aero.json"),
            kind="json",
            data={
                "extensions": {
                    "org.setuav.studio.aerodynamics": {
                        "results_version": 1,
                        "results": [
                            {
                                "id": "legacy",
                                "result": {
                                    "method": "comprehensive",
                                    "polar_points": [],
                                    "beta_polar_points": [legacy_point],
                                    "solver_results": {},
                                },
                            }
                        ],
                    }
                }
            },
        )
        self.api._host.set_project(project)
        persisted = project.get_extension("org.setuav.studio.aerodynamics")
        self.assertEqual(persisted["results_version"], RESULTS_VERSION)
        self.assertEqual(persisted["results"][0]["result"]["method"], "aero_buildup")

    def test_result_without_converged_points_is_not_persisted(self) -> None:
        statuses: list[tuple[str, str, int]] = []
        self.api._host.bind_status_handler(
            lambda message, level, timeout: statuses.append((message, level, timeout))
        )
        self.plugin.activate(self.api)
        project = ProjectDocument(
            path=Path("failed-aero.json"),
            kind="json",
            data={"name": "Failed Aero", "components": []},
        )
        self.api._host.set_project(project)
        failed_result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            polar_points=[
                PolarPoint(
                    alpha=2.0,
                    cl=0.0,
                    cd=0.0,
                    converged=False,
                    notes="solver exploded",
                )
            ],
        )

        self.plugin._handle_analysis_result(failed_result)

        self.assertEqual(analysis_entries(project), ())
        self.assertIsNone(self.plugin._latest_result)
        self.assertEqual(statuses[-1][1], "error")

    def test_pitch_status_marks_two_percent_margin_as_marginal(self) -> None:
        result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            stability_derivatives=StabilityDerivatives(
                c_m_alpha_rad=-0.4,
                c_m_alpha_deg=-0.007,
                c_m_q=-1.0,
                static_margin=1.5,
                is_pitch_stable=True,
                is_pitch_damped=True,
            ),
        )
        metrics = AeroResultsDock._stability_metrics(result)
        self.assertEqual(metrics["pitch_status"], "MARGINAL")

    def test_airfoil_analysis_tool_is_standalone(self) -> None:
        tool = AirfoilAnalysisToolWindow(self.api)
        self.assertEqual(tool.airfoil_combo.currentText(), "NACA 2412")
        self.assertEqual(tool.model_combo.currentData(), "large")
        self.assertEqual(tool.results_table.columnCount(), 7)
        self.assertIsNone(self.api.current_project)

        tool._populate_results(
            [
                {
                    "alpha": 2.0,
                    "cl": 0.5,
                    "cd": 0.025,
                    "cm": -0.04,
                    "ld": 20.0,
                    "top_xtr": 0.4,
                    "bot_xtr": 0.6,
                }
            ]
        )
        self.assertEqual(tool.results_table.rowCount(), 1)
        self.assertEqual(tool.results_table.item(0, 0).text(), "2")
        tool.close()

    def test_alpha_beta_grid_uses_one_chart_series_per_beta(self) -> None:
        self.plugin.activate(self.api)
        panels_by_id = {panel.id: panel for panel in self.panels}
        controls = panels_by_id["aerodynamics.controls_dock"].factory()
        charts = panels_by_id["aerodynamics.charts_dock"].factory()
        self.assertGreaterEqual(
            controls.combo_mode.findData(SweepType.MULTI_GRID),
            0,
        )

        alpha_values = [-4.0, 0.0, 4.0]
        beta_values = [-5.0, 5.0]
        points = [
            PolarPoint(
                alpha=alpha,
                beta=beta,
                cl=0.1 * alpha + 0.01 * beta,
                cd=0.02 + 0.001 * alpha**2,
                cm=-0.02 * alpha,
                cy=0.02 * beta,
                cl_roll=0.01 * beta,
                cn=-0.015 * beta,
                cl_over_cd=10.0 + alpha,
            )
            for beta in beta_values
            for alpha in alpha_values
        ]
        condition = FlightCondition(
            sweep_type=SweepType.MULTI_GRID,
            sweep_variable="alpha",
            sweep_min=-4.0,
            sweep_max=4.0,
            sweep_steps=3,
            secondary_variable="beta",
            secondary_min=-5.0,
            secondary_max=5.0,
            secondary_steps=2,
        )
        result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            polar_points=points,
            condition=condition,
            sweep_result=MultiDimensionalSweepResult(
                variables=[
                    SweepVariable("beta", beta_values, "deg"),
                    SweepVariable("alpha", alpha_values, "deg"),
                ],
                points=points,
                grid_shape=(2, 3),
            ),
        )

        charts.plot_results(result)

        self.assertEqual(charts.combo_view_mode.currentData(), "alpha_beta_grid")
        for chart in (
            charts.chart_lift,
            charts.chart_polar,
            charts.chart_moment,
            charts.chart_ld,
        ):
            self.assertEqual(len(chart.chart.series()), 2)
            self.assertEqual(chart.chart.series()[0].count(), 3)
        self.assertEqual(charts.chart_lift.chart.series()[0].name(), "β=-5°")
        self.assertEqual(charts.chart_lift.chart.series()[1].name(), "β=+5°")

        lateral_index = charts.combo_view_mode.findData("alpha_beta_lateral")
        self.assertGreaterEqual(lateral_index, 0)
        charts.combo_view_mode.setCurrentIndex(lateral_index)
        self.assertEqual(charts.chart_lift.chart.title(), "Sideforce (CY vs α)")
        self.assertEqual(charts.chart_polar.chart.title(), "Roll Moment (Cl vs α)")
        self.assertEqual(charts.chart_moment.chart.title(), "Yaw Moment (Cn vs α)")
        for chart in (
            charts.chart_lift,
            charts.chart_polar,
            charts.chart_moment,
        ):
            self.assertEqual(len(chart.chart.series()), 2)

        controls.close()
        charts.close()

    def test_panel_factories_create_widgets_and_handle_results(self) -> None:
        self.plugin.activate(self.api)

        panels_by_id = {p.id: p for p in self.panels}
        controls_widget = panels_by_id["aerodynamics.controls_dock"].factory()
        results_widget = panels_by_id["aerodynamics.results_dock"].factory()
        charts_widget = panels_by_id["aerodynamics.charts_dock"].factory()

        self.assertIsNotNone(controls_widget)
        self.assertIsNotNone(results_widget)
        self.assertIsNotNone(charts_widget)
        project = ProjectDocument(
            path=Path("aero-results.json"),
            kind="json",
            data={"name": "Aero Results", "components": []},
        )
        self.api._host.set_project(project)
        sweep_modes = {
            controls_widget.combo_mode.itemText(index)
            for index in range(controls_widget.combo_mode.count())
        }
        self.assertNotIn("Airspeed Sweep", sweep_modes)
        self.assertNotIn("Altitude Sweep", sweep_modes)
        self.assertIn("Alpha x Beta (Grid)", sweep_modes)
        self.assertIn("Control Channel Analysis", sweep_modes)
        self.assertNotIn("Control Deflection Sweep", sweep_modes)
        solver_methods = {
            controls_widget.combo_solver.itemData(index)
            for index in range(controls_widget.combo_solver.count())
        }
        self.assertEqual(
            solver_methods,
            {
                AnalysisMethod.AERO_BUILDUP,
                AnalysisMethod.VLM,
                AnalysisMethod.LIFTING_LINE,
            },
        )
        vlm_index = controls_widget.combo_solver.findData(AnalysisMethod.VLM)
        controls_widget.combo_solver.setCurrentIndex(vlm_index)
        self.assertTrue(controls_widget.combo_mode.isEnabled())
        self.assertEqual(int(controls_widget.spin_span_res.maximum()), 50)

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
                PolarPoint(
                    alpha=-4.0,
                    cl=-0.1,
                    cd=0.012,
                    cm=0.01,
                    cy=0.0,
                    cl_roll=0.0,
                    cn=0.0,
                    cl_over_cd=-8.3,
                    raw={"_sweep_group": "alpha"},
                ),
                PolarPoint(
                    alpha=8.0,
                    cl=1.1,
                    cd=0.055,
                    cm=-0.09,
                    cy=0.0,
                    cl_roll=0.0,
                    cn=0.0,
                    cl_over_cd=20.0,
                    raw={"_sweep_group": "alpha"},
                ),
                PolarPoint(
                    alpha=2.0,
                    beta=-6.0,
                    cl=0.5,
                    cd=0.02,
                    cm=-0.04,
                    cy=-0.15,
                    cl_roll=-0.02,
                    cn=0.03,
                    cl_over_cd=25.0,
                    raw={"_sweep_group": "beta"},
                ),
                PolarPoint(
                    alpha=2.0,
                    beta=6.0,
                    cl=0.5,
                    cd=0.02,
                    cm=-0.04,
                    cy=0.15,
                    cl_roll=0.02,
                    cn=-0.03,
                    cl_over_cd=25.0,
                    raw={"_sweep_group": "beta"},
                ),
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

        # The result is persisted in the project and selected through the
        # plugin-owned Project Tree contribution.
        self.assertEqual(len(analysis_entries(project)), 1)
        self.assertEqual(len(self.api.project_tree_nodes(project)), 1)
        result_group = self.api.project_tree_nodes(project)[0]
        self.assertEqual(result_group.title, "Aero Analyses")
        result_nodes = result_group.children
        self.assertEqual(len(result_nodes), 1)
        self.assertEqual(result_nodes[0].title, "α–β Sweep")
        self.assertEqual(self.api.current_selection, result_nodes[0].selection)
        explorer = ProjectExplorer(self.api)
        self.assertIn("aerodynamics.analysis-results", explorer._item_map)
        self.assertIn(result_nodes[0].id, explorer._item_map)
        explorer._item_map[result_nodes[0].id].setText(0, "Cruise Envelope")
        self.assertEqual(analysis_entries(project)[0]["name"], "Cruise Envelope")
        self.assertEqual(
            self.api.project_tree_nodes(project)[0].children[0].title,
            "Cruise Envelope",
        )
        self.assertEqual(results_widget.current_result.cl_max, dummy_result.cl_max)
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
        # Project Tree entry restores both tables and charts to that result.
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
        self.assertEqual(len(analysis_entries(project)), 2)
        self.assertEqual(results_widget.current_result.cl_max, second_result.cl_max)
        self.assertEqual(results_widget.detail_table.rowCount(), 1)

        result_nodes = self.api.project_tree_nodes(project)[0].children
        self.api.set_selection(result_nodes[0].selection)
        self.assertEqual(results_widget.current_result.cl_max, dummy_result.cl_max)
        self.assertEqual(results_widget.detail_table.rowCount(), 4)
        self.assertEqual(charts_widget.chart_lift.chart.series()[0].count(), 2)

        results_widget.delete_result_button.click()
        self.assertEqual(len(analysis_entries(project)), 1)
        self.assertIsNone(results_widget.current_result)

        result_nodes = self.api.project_tree_nodes(project)[0].children
        self.api.set_selection(result_nodes[0].selection)
        self.assertEqual(results_widget.current_result.cl_max, second_result.cl_max)
        self.assertEqual(results_widget.detail_table.rowCount(), 1)
        self.assertEqual(charts_widget.chart_lift.chart.series()[0].count(), 1)

        results_widget.delete_result_button.click()
        self.assertEqual(len(analysis_entries(project)), 0)
        self.assertEqual(self.api.project_tree_nodes(project), ())
        self.assertIsNone(results_widget.current_result)
        self.assertEqual(results_widget.detail_table.rowCount(), 0)
        self.assertEqual(charts_widget.combo_view_mode.count(), 0)

        # The stored representation remains JSON-safe and reconstructs the
        # full result model after a project save/load boundary.
        self.plugin._handle_analysis_result(dummy_result)
        reloaded = ProjectDocument(
            path=Path("reloaded.json"),
            kind="json",
            data=json.loads(json.dumps(project.data)),
        )
        stored_id = str(analysis_entries(reloaded)[0]["id"])
        restored = load_analysis_result(reloaded, stored_id)
        self.assertIsNotNone(restored)
        self.assertEqual(len(restored.polar_points), 4)
        self.assertEqual(restored.condition.sweep_type, SweepType.DUAL_ALPHA_BETA)

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
        self.assertIn(
            ("Tools/Aerodynamics", "Airfoil Analysis…"),
            self.removed_actions,
        )
        self.assertNotIn(
            "aerodynamics.settings.airfoil_analysis",
            {page.id for page in self.api._host.settings_pages()},
        )
        self.assertIn("studio.workspace.aerodynamics", self.removed_workspaces)

    def test_controls_offer_aircraft_channels_not_surface_names(self) -> None:
        self.plugin.activate(self.api)
        controls = next(
            panel.factory() for panel in self.panels if panel.id == "aerodynamics.controls_dock"
        )
        self.api._host.set_project(
            ProjectDocument(
                path=Path("controls.json"),
                kind="json",
                data={
                    "components": [
                        {
                            "type": "org.setuav.core:control-surface",
                            "parameters": {
                                "geometry": {
                                    "type": "elevon",
                                    "tag": "left-elevon",
                                }
                            },
                        },
                        {
                            "type": "org.setuav.core:control-surface",
                            "parameters": {
                                "geometry": {
                                    "type": "ruddervator",
                                    "tag": "right-ruddervator",
                                }
                            },
                        },
                    ]
                },
            )
        )
        channels = tuple(
            controls.combo_ctrl.itemData(index) for index in range(controls.combo_ctrl.count())
        )
        self.assertEqual(channels, ("elevator", "aileron", "rudder"))
        self.assertNotIn("left-elevon", channels)
        self.assertNotIn("right-ruddervator", channels)

    def test_control_analysis_uses_dedicated_results_and_charts(self) -> None:
        self.plugin.activate(self.api)
        panels = {panel.id: panel.factory() for panel in self.panels}
        result = AeroResult(
            method=AnalysisMethod.VLM,
            engine_name="AeroSandbox",
            polar_points=[
                PolarPoint(
                    alpha=2.0,
                    cl=0.4 + deflection * 0.01,
                    cd=0.02 + abs(deflection) * 0.0002,
                    cm=-deflection * 0.015,
                    control_deflections={"elevator": deflection},
                )
                for deflection in (-10.0, 0.0, 10.0)
            ],
            condition=FlightCondition(
                alpha=2.0,
                sweep_type=SweepType.CONTROL_DEFLECTION,
                sweep_variable="elevator",
                sweep_min=-10.0,
                sweep_max=10.0,
                sweep_steps=3,
            ),
            control_analysis=ControlChannelAnalysis(
                channel="elevator",
                sample_count=3,
                deflection_min_deg=-10.0,
                deflection_max_deg=10.0,
                derivatives_per_deg={
                    "CL": 0.01,
                    "CD": 0.0,
                    "Cm": -0.015,
                    "CY": 0.0,
                    "Cl": 0.0,
                    "Cn": 0.0,
                },
                linearity_r2={"Cm": 1.0},
            ),
        )
        panels["aerodynamics.results_dock"].display_results(result)
        charts = panels["aerodynamics.charts_dock"]
        charts.plot_results(result)

        self.assertEqual(charts.combo_view_mode.count(), 1)
        self.assertEqual(charts.combo_view_mode.currentData(), "control_effectiveness")
        self.assertIn("Elevator Effectiveness", charts.chart_lift.chart.title())
        metrics = panels["aerodynamics.results_dock"]._control_analysis_metrics(result)
        self.assertIn("dCm/dδ=-0.01500/deg", metrics["control_effectiveness"])

    def test_project_tree_analysis_results_support_delete(self) -> None:
        self.plugin.activate(self.api)
        project = ProjectDocument(
            path=Path("aero-results.json"),
            kind="json",
            data={"name": "Aero Results", "components": []},
        )
        self.api._host.set_project(project)
        dummy_result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            polar_points=[
                PolarPoint(alpha=0.0, cl=0.2, cd=0.015, cm=0.0),
            ],
            reference=ReferenceValues(s_ref=0.6, b_ref=1.8, c_ref=0.33),
            condition=FlightCondition(alpha=0.0, alpha_steps=1),
        )
        self.plugin._handle_analysis_result(dummy_result)
        nodes = self.api.project_tree_nodes(project)
        self.assertEqual(len(nodes), 1)
        group_node = nodes[0]
        self.assertIsNotNone(group_node.delete)
        self.assertEqual(len(group_node.children), 1)
        result_node = group_node.children[0]
        self.assertIsNotNone(result_node.delete)

        explorer = ProjectExplorer(self.api)
        result_item = explorer._item_map[result_node.id]

        # Test delete via Delete key press
        explorer.setCurrentItem(result_item)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            event = QKeyEvent(
                QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
            )
            explorer.keyPressEvent(event)

        self.assertEqual(len(analysis_entries(project)), 0)
        self.assertEqual(self.api.project_tree_nodes(project), ())

    def test_project_tree_delete_all_results_group(self) -> None:
        self.plugin.activate(self.api)
        project = ProjectDocument(
            path=Path("aero-results.json"),
            kind="json",
            data={"name": "Aero Results", "components": []},
        )
        self.api._host.set_project(project)
        dummy_result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            polar_points=[
                PolarPoint(alpha=0.0, cl=0.2, cd=0.015, cm=0.0),
            ],
            reference=ReferenceValues(s_ref=0.6, b_ref=1.8, c_ref=0.33),
            condition=FlightCondition(alpha=0.0, alpha_steps=1),
        )
        self.plugin._handle_analysis_result(dummy_result)
        explorer = ProjectExplorer(self.api)
        group_item = explorer._item_map["aerodynamics.analysis-results"]

        explorer.setCurrentItem(group_item)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            event = QKeyEvent(
                QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
            )
            explorer.keyPressEvent(event)

        self.assertEqual(len(analysis_entries(project)), 0)
        self.assertEqual(self.api.project_tree_nodes(project), ())

    def test_project_tree_context_menu_has_delete_for_analysis_result(self) -> None:
        self.plugin.activate(self.api)
        project = ProjectDocument(
            path=Path("aero-results.json"),
            kind="json",
            data={"name": "Aero Results", "components": []},
        )
        self.api._host.set_project(project)
        dummy_result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            polar_points=[
                PolarPoint(alpha=0.0, cl=0.2, cd=0.015, cm=0.0),
            ],
            reference=ReferenceValues(s_ref=0.6, b_ref=1.8, c_ref=0.33),
            condition=FlightCondition(alpha=0.0, alpha_steps=1),
        )
        self.plugin._handle_analysis_result(dummy_result)
        explorer = ProjectExplorer(self.api)
        explorer.resize(400, 600)
        result_node = self.api.project_tree_nodes(project)[0].children[0]
        result_item = explorer._item_map[result_node.id]

        menu_actions: list[str] = []
        real_qmenu = QMenu

        class MockMenu(real_qmenu):
            def addAction(self, *args, **kwargs):
                action = super().addAction(*args, **kwargs)
                menu_actions.append(action.text())
                return action

            def exec(self, *args, **kwargs):
                return None

        with patch("setuav_studio.plugins.core.ui.project_explorer.QMenu", MockMenu):
            explorer._open_context_menu(explorer.visualItemRect(result_item).center())

        self.assertIn("Rename", menu_actions)
        self.assertIn("Delete", menu_actions)

    def test_project_tree_delete_key_deletes_component(self) -> None:
        component = {
            "id": "wing_main",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
        }
        project = ProjectDocument(
            path=Path("test_comp.json"),
            kind="json",
            data={"name": "Test Project", "components": [component]},
        )
        self.api._host.set_project(project)
        explorer = ProjectExplorer(self.api)
        wing_item = explorer._item_map["wing_main"]
        explorer.setCurrentItem(wing_item)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            event = QKeyEvent(
                QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
            )
            explorer.keyPressEvent(event)

        self.assertEqual(len(project.data["components"]), 0)

    def test_unsaved_analysis_result_is_marked_dirty_yellow(self) -> None:
        from setuav_studio.ui.theme import status_color

        self.plugin.activate(self.api)
        project = ProjectDocument(
            path=Path("aero-results.json"),
            kind="json",
            data={"name": "Aero Results", "components": []},
        )
        self.api._host.set_project(project)
        explorer = ProjectExplorer(self.api)

        # Run analysis (creates an unsaved result)
        dummy_result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            polar_points=[
                PolarPoint(alpha=0.0, cl=0.2, cd=0.015, cm=0.0),
            ],
            reference=ReferenceValues(s_ref=0.6, b_ref=1.8, c_ref=0.33),
            condition=FlightCondition(alpha=0.0, alpha_steps=1),
        )
        self.plugin._handle_analysis_result(dummy_result)
        result_node = self.api.project_tree_nodes(project)[0].children[0]
        result_item = explorer._item_map[result_node.id]

        # Should be colored warning (yellow)
        self.assertEqual(
            result_item.foreground(0).color().name().lower(),
            status_color("warning").lower(),
        )

        # After mark_project_saved / clean, dirty color is cleared
        self.api._host.mark_project_saved()
        result_item = explorer._item_map[result_node.id]
        self.assertNotEqual(
            result_item.foreground(0).color().name().lower(),
            status_color("warning").lower(),
        )
