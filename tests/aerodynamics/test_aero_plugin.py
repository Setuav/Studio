"""Unit and integration tests for the Aerodynamics Plugin."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QMenu, QMessageBox

from plugins.aerodynamics.airfoil_analysis_tool import (
    AirfoilAnalysisToolWindow,
)
from plugins.aerodynamics.engine.aerosandbox_engine import (
    HAS_AEROSANDBOX,
    AeroSandboxEngine,
)
from plugins.aerodynamics.engine.base import (
    CONTROL_CHANNELS,
    AeroAnalysisError,
    AeroForcesMoments,
    AeroResult,
    AnalysisMethod,
    FlightCondition,
    PolarPoint,
    control_channels_for_components,
)
from plugins.aerodynamics.engine.stability_models import (
    StabilityDerivatives,
)
from plugins.aerodynamics.plugin import AerodynamicsPlugin
from plugins.aerodynamics.solver import (
    SOLVER_ID_ALPHA_SWEEP,
    SOLVER_ID_BETA_SWEEP,
    SOLVER_ID_CONTROL_DEFLECTION,
    SOLVER_ID_OPERATING_POINT,
    AlphaSweepSolver,
    BaseAerodynamicsSolver,
    BetaSweepSolver,
    ControlDeflectionSolver,
    OperatingPointSolver,
)
from setuav_studio.api import (
    ActionContribution,
    StudioAPI,
    ToolbarContribution,
)
from setuav_studio.project import ProjectDocument
from setuav_studio.solver import SolverConfig
from setuav_studio.solver.base import SolverStatus
from setuav_studio.solver.results import SolverResult
from setuav_studio.ui.panels.project_explorer import ProjectExplorer
from tests._common import get_qapp

ANALYSIS_TOOLBAR_IDS = (
    "aerodynamics.add-alpha-sweep",
    "aerodynamics.add-beta-sweep",
    "aerodynamics.add-control-deflection",
    "aerodynamics.add-operating-point",
)
SOLVER_CLASSES = {
    SOLVER_ID_ALPHA_SWEEP: AlphaSweepSolver,
    SOLVER_ID_BETA_SWEEP: BetaSweepSolver,
    SOLVER_ID_CONTROL_DEFLECTION: ControlDeflectionSolver,
    SOLVER_ID_OPERATING_POINT: OperatingPointSolver,
}
ANALYSIS_TITLES = (
    "Add Alpha Sweep (Polar) Analysis",
    "Add Beta Sweep (Sideslip) Analysis",
    "Add Control Deflection Analysis",
    "Add Aero Operating Point Analysis",
)
# The analyses are toolbar buttons only; the Tools menu keeps the standalone tool.
TOOL_TITLES = ("Airfoil Analysis…",)
WING = {"id": "wing", "name": "Main Wing", "type": "org.setuav.core:lifting-surface"}


def _control_surface(component_id: str, surface_type: str) -> dict[str, Any]:
    return {
        "id": component_id,
        "name": component_id,
        "type": "org.setuav.core:control-surface",
        "attach_to": "wing",
        "parameters": {"geometry": {"type": surface_type}},
    }


def _enabled(item: ToolbarContribution) -> bool:
    assert item.enabled_when is not None
    return item.enabled_when()


def _trigger(item: ToolbarContribution) -> None:
    assert item.callback is not None
    item.callback()


def _project(components: list[dict[str, Any]] | None = None) -> ProjectDocument:
    return ProjectDocument(
        path=Path("aero-analysis.json"),
        kind="json",
        data={"name": "Aero Analysis", "components": list(components or [])},
    )


def _point(alpha: float, **values: Any) -> PolarPoint:
    cl = 0.1 * alpha + 0.2
    cd = 0.02 + 0.001 * alpha**2
    return PolarPoint(
        alpha=alpha,
        cl=cl,
        cd=cd,
        cm=-0.01 * alpha,
        cl_over_cd=cl / cd,
        cd_induced=0.5 * cd,
        cd_profile=0.5 * cd,
        forces_moments=AeroForcesMoments(lift=100.0 * cl, drag=100.0 * cd),
        **values,
    )


class AerodynamicsPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.toolbar_items: list[ToolbarContribution] = []
        self.removed_toolbar_items: list[str] = []
        self.actions: list[ActionContribution] = []
        self.removed_actions: list[tuple[str, str]] = []
        self.statuses: list[tuple[str, str, int]] = []

        self.api._host.bind_toolbar_handlers(
            self.toolbar_items.append,
            unregister_handler=self.removed_toolbar_items.append,
        )
        self.api._host.bind_action_handlers(
            self.actions.append,
            unregister_handler=lambda menu, title: self.removed_actions.append((menu, title)),
        )
        self.api._host.bind_status_handler(
            lambda message, level, timeout: self.statuses.append((message, level, timeout))
        )

        self.plugin = AerodynamicsPlugin()

    def tearDown(self) -> None:
        self._app.processEvents()

    def _analysis_buttons(self) -> list[ToolbarContribution]:
        by_id = {item.id: item for item in self.toolbar_items}
        return [by_id[toolbar_id] for toolbar_id in ANALYSIS_TOOLBAR_IDS]

    def _add_alpha_sweep_analysis(self) -> SolverConfig:
        _trigger(self._analysis_buttons()[0])
        config = self.api.get_current_solver_config()
        assert config is not None
        return config

    @staticmethod
    def _run_solver(
        solver_cls: type[BaseAerodynamicsSolver],
        parameters: dict[str, Any],
        aero_result: AeroResult,
        components: list[dict[str, Any]] | None = None,
    ) -> tuple[SolverResult, dict[str, Any]]:
        config = SolverConfig(
            solver_id="aero-test",
            name="Aero Test",
            parameters={**solver_cls.default_parameters(), **parameters},
        )
        solver = solver_cls(config)
        solver.project = _project(components or [WING])
        calls: list[dict[str, Any]] = []

        def analyze(**kwargs: Any) -> AeroResult:
            calls.append(kwargs)
            return aero_result

        with patch.object(solver.engine, "analyze", side_effect=analyze):
            result = solver.run()
        return result, calls[0]

    def test_activation_registers_solvers_toolbar_and_tools(self) -> None:
        self.plugin.activate(self.api)

        for solver_id, solver_cls in SOLVER_CLASSES.items():
            self.assertIs(self.api.solvers.get_solver_class(solver_id), solver_cls)

        self.assertEqual(
            tuple(item.title for item in self._analysis_buttons()),
            ANALYSIS_TITLES,
        )
        self.assertEqual(
            tuple(action.title for action in self.actions if action.menu == "Tools/Aerodynamics"),
            TOOL_TITLES,
        )

    def test_add_analysis_buttons_create_default_solver_configs(self) -> None:
        self.plugin.activate(self.api)
        buttons = self._analysis_buttons()

        self.assertFalse(any(_enabled(item) for item in buttons))
        _trigger(buttons[0])
        self.assertEqual(self.statuses[-1][1], "warning")

        self.api._host.set_project(_project())
        self.assertTrue(all(_enabled(item) for item in buttons))
        for item in buttons:
            _trigger(item)

        configs = list(self.api.get_solver_configs().values())
        self.assertEqual(
            [config.solver_id for config in configs],
            list(SOLVER_CLASSES),
        )
        self.assertEqual(self.api.current_solver_config_id, configs[-1].config_id)
        for config in configs:
            solver_cls = SOLVER_CLASSES[config.solver_id]
            self.assertEqual(
                config.parameters,
                {field.key: field.default for field in solver_cls.PARAMETER_FIELDS},
            )

    def test_deactivation_cleans_up(self) -> None:
        self.plugin.activate(self.api)
        self.plugin.deactivate(self.api)

        for solver_id in SOLVER_CLASSES:
            self.assertIsNone(self.api.solvers.get_solver_class(solver_id))
        for toolbar_id in ANALYSIS_TOOLBAR_IDS:
            self.assertIn(toolbar_id, self.removed_toolbar_items)
        self.assertEqual(
            tuple(title for menu, title in self.removed_actions if menu == "Tools/Aerodynamics"),
            TOOL_TITLES,
        )

    def test_airfoil_analysis_tool_is_standalone(self) -> None:
        tool = AirfoilAnalysisToolWindow(self.api)
        self.assertEqual(tool.airfoil_combo.currentText(), "NACA 2412")
        self.assertEqual(tool.model_combo.currentData(), "large")
        self.assertEqual(tool.results_table.columnCount(), 7)
        self.assertIsNone(self.api.project)

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
        first_cell = tool.results_table.item(0, 0)
        assert first_cell is not None
        self.assertEqual(first_cell.text(), "2")
        tool.close()

    def test_airfoil_analysis_runs_as_a_studio_task(self) -> None:
        from unittest import mock

        from PySide6.QtCore import QDeadlineTimer
        from PySide6.QtTest import QTest

        row = {
            "alpha": 2.0,
            "cl": 0.5,
            "cd": 0.025,
            "cm": -0.04,
            "ld": 20.0,
            "top_xtr": 0.4,
            "bot_xtr": 0.6,
        }
        tool = AirfoilAnalysisToolWindow(self.api)

        def run(result: object) -> None:
            with mock.patch(
                "plugins.aerodynamics.airfoil_analysis_tool.analyze_airfoil_request",
                side_effect=[result],
            ):
                tool._run_analysis()
                self.assertFalse(tool.run_button.isEnabled())
                deadline = QDeadlineTimer(5000)
                while not tool.run_button.isEnabled() and not deadline.hasExpired():
                    QTest.qWait(10)
            self.assertTrue(tool.run_button.isEnabled())

        if not HAS_AEROSANDBOX:
            self.skipTest("AeroSandbox not installed")
        run(
            {
                "engine": "NeuralFoil (large)",
                "airfoil": "NACA 2412",
                "cache_hit": False,
                "rows": [row],
            }
        )
        self.assertEqual(tool.results_table.rowCount(), 1)

        with mock.patch("plugins.aerodynamics.airfoil_analysis_tool.QMessageBox.critical"):
            run(RuntimeError("no converged points"))
        self.assertIn("no converged points", tool.status_label.text())
        tool.close()

    def test_controls_offer_aircraft_channels_not_surface_names(self) -> None:
        components = [
            WING,
            _control_surface("left-elevon", "elevon"),
            _control_surface("right-ruddervator", "ruddervator"),
        ]
        self.assertEqual(
            control_channels_for_components(components),
            ("elevator", "aileron", "rudder"),
        )

        channel_field = next(
            field for field in ControlDeflectionSolver.PARAMETER_FIELDS if field.key == "channel"
        )
        assert channel_field.options is not None
        offered = tuple(value for value, _label in channel_field.options)
        self.assertEqual(offered, CONTROL_CHANNELS)
        self.assertNotIn("elevon", offered)
        self.assertNotIn("ruddervator", offered)

    def test_option_values_are_what_the_solvers_read(self) -> None:
        """Options are (value, label): the editor stores the value the solver parses."""
        from plugins.aerodynamics.engine.base import AnalysisMethod

        for solver_cls in SOLVER_CLASSES.values():
            for field in solver_cls.PARAMETER_FIELDS:
                if not field.options:
                    continue
                values = [option[0] for option in field.options if isinstance(option, tuple)]
                if field.key == "method":
                    for value in values:
                        self.assertEqual(AnalysisMethod.from_value(value).value, value)
                if field.key == "channel":
                    self.assertEqual(tuple(values), CONTROL_CHANNELS)

    def test_sweep_solver_rejects_reversed_bounds(self) -> None:
        parameters = {
            **AlphaSweepSolver.default_parameters(),
            "alpha_min": 8.0,
            "alpha_max": -4.0,
        }
        with self.assertRaisesRegex(ValueError, "alpha maximum .* must exceed its minimum"):
            self._run_solver(
                AlphaSweepSolver,
                parameters,
                AeroResult(method=AnalysisMethod.VLM, engine_name="AeroSandbox"),
            )

    def test_alpha_sweep_solver_builds_polar_table_plots_and_summary(self) -> None:
        aero_result = AeroResult(
            method=AnalysisMethod.VLM,
            engine_name="AeroSandbox",
            polar_points=[
                _point(-4.0),
                _point(0.0),
                _point(4.0, converged=False, notes="solver diverged"),
                _point(8.0),
            ],
            cl_max=1.0,
            cl_max_alpha=8.0,
            cd_min=0.02,
            ld_max=12.5,
            ld_max_alpha=4.0,
            oswald_efficiency=0.82,
            stability_derivatives=StabilityDerivatives(x_np=0.31, static_margin=12.5),
        )

        result, call = self._run_solver(
            AlphaSweepSolver,
            {
                "alpha_min": -4.0,
                "alpha_max": 8.0,
                "alpha_step": 4.0,
                "velocity": 20.0,
                "altitude": 100.0,
                "beta": 1.5,
                "method": "vlm",
                "spanwise_resolution": 16.0,
                "chordwise_resolution": 6.0,
            },
            aero_result,
        )

        condition: FlightCondition = call["condition"]
        self.assertEqual(condition.sweep_variable, "alpha")
        self.assertEqual((condition.sweep_min, condition.sweep_max), (-4.0, 8.0))
        self.assertEqual(condition.sweep_steps, 4)
        self.assertEqual(
            (condition.velocity, condition.altitude, condition.beta), (20.0, 100.0, 1.5)
        )
        self.assertEqual(call["method"], AnalysisMethod.VLM)
        self.assertEqual(call["settings"]["spanwise_resolution"], 16)
        self.assertEqual(call["settings"]["chordwise_resolution"], 6)

        self.assertEqual(result.status, SolverStatus.COMPLETED)
        table = result.tables["alpha_polar"]
        self.assertEqual(table.get_column("alpha"), [-4.0, 0.0, 8.0])
        self.assertEqual(table.get_column("lift"), [100.0 * _point(a).cl for a in (-4, 0, 8)])
        quantities = {column.key: column.quantity_id for column in table.columns}
        self.assertEqual(quantities["alpha"], "angle")
        self.assertEqual(quantities["lift"], "force")
        self.assertEqual(quantities["drag"], "force")
        self.assertEqual(
            set(result.plots),
            {"cl_alpha", "cd_alpha", "drag_polar", "cl_over_cd", "cm_alpha"},
        )
        self.assertTrue(all(plot.table_id == "alpha_polar" for plot in result.plots.values()))
        self.assertEqual(result.summary["cl_max"].value, 1.0)
        self.assertEqual(result.summary["ld_max_alpha"].value, 4.0)
        self.assertEqual(result.summary["oswald_e"].value, 0.82)
        self.assertEqual(result.summary["x_np"].value, 0.31)
        self.assertEqual(result.summary["static_margin"].value, 12.5)

    def test_beta_sweep_solver_builds_lateral_table_and_derivatives(self) -> None:
        aero_result = AeroResult(
            method=AnalysisMethod.AERO_BUILDUP,
            engine_name="AeroSandbox",
            polar_points=[
                _point(3.0, beta=beta, cy=-0.01 * beta, cl_roll=-0.002 * beta, cn=0.003 * beta)
                for beta in (-10.0, 0.0, 10.0)
            ],
            stability_derivatives=StabilityDerivatives(
                c_Y_beta_deg=-0.01,
                c_l_beta_deg=-0.002,
                c_n_beta_deg=0.003,
            ),
        )

        result, call = self._run_solver(
            BetaSweepSolver,
            {"beta_min": -10.0, "beta_max": 10.0, "beta_step": 10.0, "alpha": 3.0},
            aero_result,
        )

        condition: FlightCondition = call["condition"]
        self.assertEqual(condition.sweep_variable, "beta")
        self.assertEqual((condition.sweep_min, condition.sweep_max), (-10.0, 10.0))
        self.assertEqual(condition.sweep_steps, 3)
        self.assertEqual(condition.alpha, 3.0)
        self.assertEqual(call["method"], AnalysisMethod.AERO_BUILDUP)

        table = result.tables["beta_polar"]
        self.assertEqual(table.get_column("beta"), [-10.0, 0.0, 10.0])
        self.assertEqual(table.get_column("cn"), [0.003 * beta for beta in (-10.0, 0.0, 10.0)])
        self.assertEqual(set(result.plots), {"cy_beta", "cl_roll_beta", "cn_beta"})
        self.assertEqual(result.summary["cy_beta"].value, -0.01)
        self.assertEqual(result.summary["cl_beta"].value, -0.002)
        self.assertEqual(result.summary["cn_beta"].value, 0.003)

    def test_control_analysis_uses_dedicated_results(self) -> None:
        points = [
            PolarPoint(
                alpha=2.0,
                cl=0.4 + deflection * 0.01,
                cd=0.02 + abs(deflection) * 0.0002,
                cm=-deflection * 0.015,
                cl_roll=deflection * 0.002,
                cn=-deflection * 0.0005,
                control_deflections={"elevator": deflection},
            )
            for deflection in (-10.0, 0.0, 10.0)
        ]
        aero_result = AeroResult(
            method=AnalysisMethod.VLM,
            engine_name="AeroSandbox",
            polar_points=points,
            control_analysis=AeroSandboxEngine._fit_control_channel_analysis(points, "elevator"),
        )

        result, call = self._run_solver(
            ControlDeflectionSolver,
            {
                "channel": "elevator",
                "deflection_min": -10.0,
                "deflection_max": 10.0,
                "deflection_step": 10.0,
                "alpha": 2.0,
                "method": "vlm",
            },
            aero_result,
            components=[WING, _control_surface("left-elevon", "elevon")],
        )

        condition: FlightCondition = call["condition"]
        self.assertEqual(condition.sweep_variable, "elevator")
        self.assertEqual(condition.control_deflections, {"elevator": 0.0})
        self.assertEqual(condition.sweep_steps, 3)

        table = result.tables["control_polar"]
        self.assertEqual(table.get_column("deflection"), [-10.0, 0.0, 10.0])
        self.assertEqual(set(result.plots), {"cm_delta", "cl_delta", "roll_yaw_delta"})
        self.assertEqual(result.summary["channel"].value, "Elevator")
        self.assertEqual(result.summary["cm_delta"].value, -0.015)
        self.assertEqual(result.summary["cl_delta"].value, 0.01)
        self.assertEqual(result.summary["cl_roll_delta"].value, 0.002)
        self.assertEqual(result.summary["cn_delta"].value, -0.0005)

    def test_operating_point_solver_reports_single_state(self) -> None:
        point = _point(
            5.0,
            beta=2.0,
            cy=0.01,
            dynamic_pressure=245.0,
            mach=0.06,
            reynolds=3.2e5,
        )
        aero_result = AeroResult(
            method=AnalysisMethod.LIFTING_LINE,
            engine_name="AeroSandbox",
            polar_points=[point],
        )

        result, call = self._run_solver(
            OperatingPointSolver,
            {"alpha": 5.0, "beta": 2.0, "velocity": 20.0, "method": "lifting_line"},
            aero_result,
        )

        condition: FlightCondition = call["condition"]
        self.assertEqual(condition.sweep_values(), [5.0])
        self.assertEqual(condition.beta, 2.0)
        self.assertEqual(call["method"], AnalysisMethod.LIFTING_LINE)

        table = result.tables["operating_point_data"]
        self.assertEqual(table.row_count(), 1)
        self.assertEqual(table.get_column("cl"), [point.cl])
        self.assertEqual(result.summary["lift"].value, round(100.0 * point.cl, 2))
        self.assertEqual(result.summary["q_inf"].value, 245.0)
        self.assertEqual(result.summary["reynolds"].value, "3.20e+05")

    @unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
    def test_control_analysis_rejects_channel_missing_on_aircraft(self) -> None:
        aero_result = AeroResult(method=AnalysisMethod.VLM, engine_name="AeroSandbox")
        with self.assertRaisesRegex(AeroAnalysisError, "no 'aileron' control channel"):
            self._run_solver(ControlDeflectionSolver, {"channel": "aileron"}, aero_result)

    def test_unknown_solver_method_is_rejected(self) -> None:
        aero_result = AeroResult(method=AnalysisMethod.VLM, engine_name="AeroSandbox")
        with self.assertRaises(ValueError):
            self._run_solver(AlphaSweepSolver, {"method": "llt"}, aero_result)

    def test_analysis_without_converged_points_fails(self) -> None:
        wing = {
            "id": "wing",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "mirror": True,
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "airfoil": "2412",
                        },
                        {
                            "position": {"x": 20.0, "y": 600.0, "z": 0.0},
                            "chord": 150.0,
                            "airfoil": "2412",
                        },
                    ],
                }
            },
        }
        config = SolverConfig(
            solver_id=SOLVER_ID_ALPHA_SWEEP,
            name="Diverging Polar",
            parameters={
                **AlphaSweepSolver.default_parameters(),
                "alpha_min": 0.0,
                "alpha_max": 4.0,
                "alpha_step": 2.0,
            },
        )
        solver = AlphaSweepSolver(config)
        solver.project = _project([wing])

        with (
            patch.object(
                AeroSandboxEngine,
                "_run_solver",
                side_effect=RuntimeError("solver exploded"),
            ),
            self.assertRaisesRegex(AeroAnalysisError, "solver exploded"),
        ):
            solver.run()

    def test_project_tree_lists_analysis_and_deletes_it_with_results(self) -> None:
        self.plugin.activate(self.api)
        project = _project()
        self.api._host.set_project(project)
        config = self._add_alpha_sweep_analysis()
        self.api.add_solver_result(
            SolverResult(solver_id=config.solver_id, config=config, name=config.name)
        )

        explorer = ProjectExplorer(self.api)
        config_item = explorer._item_map[config.config_id]
        self.assertEqual(config_item.text(0), "Alpha Sweep Analysis")
        analyses_group = config_item.parent()
        assert analyses_group is not None
        self.assertEqual(analyses_group.text(0), "Analyses")

        explorer.setCurrentItem(config_item)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            explorer.keyPressEvent(
                QKeyEvent(
                    QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
                )
            )

        self.assertEqual(project.solver_configs, {})
        self.assertEqual(project.solver_results, {})
        self.assertNotIn(config.config_id, explorer._item_map)

    def test_project_tree_context_menu_has_delete_for_analysis(self) -> None:
        self.plugin.activate(self.api)
        self.api._host.set_project(_project())
        config = self._add_alpha_sweep_analysis()
        explorer = ProjectExplorer(self.api)
        explorer.resize(400, 600)
        explorer.expandAll()
        config_item = explorer._item_map[config.config_id]

        menu_actions: list[str] = []
        real_qmenu = QMenu

        class MockMenu(real_qmenu):
            def addAction(self, *args, **kwargs):
                action = super().addAction(*args, **kwargs)
                menu_actions.append(action.text())
                return action

            # Qt returns no action when a menu is dismissed; the PySide6 stub
            # declares QMenu.exec as always returning a QAction.
            def exec(self, *args, **kwargs):  # pyright: ignore[reportIncompatibleMethodOverride]
                return None

        with patch("setuav_studio.ui.panels.project_explorer.context_menu.QMenu", MockMenu):
            explorer._open_context_menu(explorer.visualItemRect(config_item).center())

        self.assertIn("Run Analysis", menu_actions)
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
            data={"components": [component]},
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

    def test_unsaved_analysis_is_marked_dirty_yellow(self) -> None:
        from setuav_studio.ui.style.theme import status_color

        self.plugin.activate(self.api)
        self.api._host.set_project(_project())
        explorer = ProjectExplorer(self.api)
        config = self._add_alpha_sweep_analysis()

        warning = status_color("warning").lower()
        config_item = explorer._item_map[config.config_id]
        self.assertEqual(config_item.foreground(0).color().name().lower(), warning)

        self.api._host.mark_project_saved()
        config_item = explorer._item_map[config.config_id]
        self.assertNotEqual(config_item.foreground(0).color().name().lower(), warning)
