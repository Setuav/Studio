"""Unit tests for the Electrical Propulsion plugin and component property editors."""

from __future__ import annotations

import unittest
from copy import deepcopy
from typing import Any
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from plugins.electrical_propulsion.editors import (
    BatteryEditor,
    EscEditor,
    MotorEditor,
    PropellerEditor,
    PropulsionSystemEditor,
)
from setuav_studio.api import ActionContribution, StudioAPI
from setuav_studio.plugin import PluginManager
from setuav_studio.project import open_project
from tests._common import TEST_PROJECT_PATH, get_qapp


class _MotorCatalogSelection:
    """Catalog dialog stand-in that accepts a preselected motor entry."""

    selected_motor: Any = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted


class _RecordingToken:
    """Cancellation token stand-in that records solver progress reports."""

    def __init__(self) -> None:
        self.progress: list[tuple[int, int, str]] = []

    @property
    def is_cancelled(self) -> bool:
        return False

    def check_cancelled(self) -> None:
        return None

    def report_progress(self, current: int, total: int, message: str = "") -> None:
        self.progress.append((current, total, message))

    def cancel(self) -> None:
        return None


class TestElectricalPropulsion(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_plugin_discovery_and_registration(self) -> None:
        from setuav_studio.ui.shell import MainWindow

        api = StudioAPI()
        _win = MainWindow(api)
        pm = PluginManager(api)
        issues = pm.discover()
        propulsion_issues = [
            issue for issue in issues if issue.source == "plugins.electrical_propulsion"
        ]
        self.assertEqual(len(propulsion_issues), 0)
        self.assertIn("org.setuav.studio.electrical_propulsion", pm._plugins)

        # Check registered editors
        self.assertIn("org.setuav.core:motor", api._component_editors)
        self.assertIn("org.setuav.core:propeller", api._component_editors)
        self.assertIn("org.setuav.core:esc", api._component_editors)
        self.assertIn("org.setuav.core:battery", api._component_editors)
        self.assertIn("org.setuav.core:propulsion-system", api._component_editors)
        _win.close()
        _win.deleteLater()

    def test_plugin_can_be_deactivated_and_reactivated(self) -> None:
        from plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
        from setuav_studio.ui.shell import MainWindow

        api = StudioAPI()
        window = MainWindow(api)
        manager = PluginManager(api)
        plugin = ElectricalPropulsionPlugin()
        manager.activate(plugin)

        self.assertIn("org.setuav.core:motor", api._component_editors)
        self.assertIn("tools/electrical propulsion", window.action_manager.menus)
        self.assertIn("studio:project-explorer", window._panels)
        self.assertIn("studio:properties", window._panels)

        manager.deactivate(plugin.id)

        self.assertNotIn("org.setuav.core:motor", api._component_editors)
        self.assertNotIn("org.setuav.core:motor", api._component_icons)
        self.assertNotIn("tools/electrical propulsion", window.action_manager.menus)
        self.assertIn("studio:project-explorer", window._panels)
        self.assertIn("studio:properties", window._panels)

        manager.activate_plugin(plugin.id)
        self.assertIn("org.setuav.core:motor", api._component_editors)
        window.close()
        window.deleteLater()

    def test_motor_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)

        motor_comp = next(
            c for c in doc.data["components"] if c.get("type") == "org.setuav.core:motor"
        )
        editor = MotorEditor(api, motor_comp)
        self.addCleanup(editor.deleteLater)

        self.assertEqual(editor._property_text(editor.general_table, 0), motor_comp.get("name"))
        # Motor specs come from the catalog and are shown read-only with their unit.
        kv_item = editor.parameters_table.item(0, 1)
        self.assertEqual(kv_item.text(), "900.0 RPM/V")
        self.assertFalse(kv_item.flags() & Qt.ItemFlag.ItemIsEditable)

        from plugins.electrical_propulsion.database import get_motor_database

        motor_db = get_motor_database()
        catalog_motor = next(
            entry
            for entry in (motor_db.get(name) for name in motor_db.list_motors())
            if entry is not None and float(entry.kv) != 900.0
        )
        _MotorCatalogSelection.selected_motor = catalog_motor
        with patch(
            "plugins.electrical_propulsion.editors.motor.ComponentCatalogDialog",
            _MotorCatalogSelection,
        ):
            editor._open_catalog()

        self.assertEqual(motor_comp["parameters"]["kv"], float(catalog_motor.kv))
        self.assertEqual(motor_comp["model"], catalog_motor.name)
        self.assertEqual(
            editor.parameters_table.item(0, 1).text(), f"{float(catalog_motor.kv)} RPM/V"
        )

        api.undo()
        self.assertEqual(motor_comp["parameters"]["kv"], 900.0)
        self.assertEqual(motor_comp["model"], "X2814 KV900 3-4S")
        editor.close()

    def test_battery_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)

        battery_comp = next(
            c for c in doc.data["components"] if c.get("type") == "org.setuav.core:battery"
        )
        editor = BatteryEditor(api, battery_comp)

        self.assertEqual(editor._property_text(editor.cell_table, 0), "LiPo")

        # Change Series Count to 6S; the editor derives mass from the fixture's
        # cell mass, parallel count, and packaging mass values.
        cell_widget = editor.pack_table.cellWidget(0, 1)
        if cell_widget is not None and hasattr(cell_widget, "setValue"):
            cell_widget.setValue(6)
        else:
            editor.pack_table.item(0, 1).setText("6")
        params = battery_comp["parameters"]
        expected_mass = 6 * int(params.get("parallel_count", 1)) * float(
            params["cell_mass"]
        ) + float(params.get("packaging_mass", 40.0))
        self.assertEqual(battery_comp["mass"], expected_mass)
        self.assertEqual(editor._property_text(editor.general_table, 2), f"{expected_mass:.1f}")
        editor.close()
        editor.deleteLater()

    def test_esc_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)

        esc_comp = next(c for c in doc.data["components"] if c.get("type") == "org.setuav.core:esc")
        editor = EscEditor(api, esc_comp)

        self.assertEqual(editor._property_text(editor.parameters_table, 0), "50.0")
        editor.close()
        editor.deleteLater()

    def test_propeller_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)

        prop_comp = next(
            c for c in doc.data["components"] if c.get("type") == "org.setuav.core:propeller"
        )
        editor = PropellerEditor(api, prop_comp)

        # Propeller specs come from the catalog and are shown read-only with their unit.
        self.assertEqual(editor._property_text(editor.parameters_table, 0), "304.8 mm")
        self.assertEqual(editor._property_text(editor.parameters_table, 1), "152.4 mm")
        self.assertEqual(editor._property_text(editor.parameters_table, 2), "2")
        for row in range(3):
            item = editor.parameters_table.item(row, 1)
            self.assertFalse(item.flags() & Qt.ItemFlag.ItemIsEditable)
        editor.close()
        editor.deleteLater()

    def test_propulsion_system_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)

        propulsion = next(c for c in doc.data["components"] if c["id"] == "propulsion")
        editor = PropulsionSystemEditor(api, propulsion)

        self.assertEqual(editor._property_text(editor.general_table, 0), "Propulsion")
        self.assertIn("battery", editor._property_text(editor.structure_table, 0).lower())
        self.assertIn("sunnysky", editor._property_text(editor.structure_table, 2).lower())
        self.assertIn("apc", editor._property_text(editor.structure_table, 3).lower())
        editor.close()
        editor.deleteLater()

    def test_catalog_database_and_dialog(self) -> None:
        from plugins.electrical_propulsion.catalog_dialog import (
            ComponentCatalogDialog,
        )
        from plugins.electrical_propulsion.database import (
            get_motor_database,
            get_propeller_database,
        )

        mot_db = get_motor_database()
        self.assertGreater(mot_db.motor_count, 100)

        prop_db = get_propeller_database()
        self.assertGreater(prop_db.propeller_count, 100)

        dialog = ComponentCatalogDialog(component_type="all")
        self.assertIsNotNone(dialog)
        dialog.motor_search.setText("Tiger")
        self.assertLessEqual(dialog.motor_table.rowCount(), 400)
        dialog.close()
        dialog.deleteLater()

    def test_analysis_tools_add_solver_configs(self) -> None:
        from plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_AIRSPEED_SWEEP,
            SOLVER_ID_OPERATING_POINT,
            SOLVER_ID_THROTTLE_SWEEP,
            AirspeedSweepSolver,
            OperatingPointSolver,
            ThrottleSweepSolver,
        )

        api, actions, statuses = self._headless_api()
        plugin = ElectricalPropulsionPlugin()
        plugin.activate(api)
        self.addCleanup(plugin.deactivate, api)
        tools = {
            action.title: action
            for action in actions
            if action.menu == "Tools/Electrical Propulsion"
        }

        tools["Add Airspeed Sweep Analysis"].callback()
        self.assertEqual(api.get_solver_configs(), {})
        self.assertEqual(statuses[-1][:2], ("Open or create a project first.", "warning"))

        api._host.set_project(open_project(TEST_PROJECT_PATH))
        expected = [
            ("Throttle Sweep Analysis", SOLVER_ID_THROTTLE_SWEEP, ThrottleSweepSolver),
            ("Airspeed Sweep Analysis", SOLVER_ID_AIRSPEED_SWEEP, AirspeedSweepSolver),
            ("Operating Point Analysis", SOLVER_ID_OPERATING_POINT, OperatingPointSolver),
        ]
        for name, solver_id, solver_cls in expected:
            tools[f"Add {name}"].callback()
            config = api.get_current_solver_config()
            assert config is not None
            self.assertEqual(config.solver_id, solver_id)
            self.assertEqual(config.name, name)
            self.assertIs(api.solvers.get_solver_class(solver_id), solver_cls)
            self.assertEqual(statuses[-1][:2], (f"Added {name} configuration.", "success"))
        self.assertEqual(len(api.get_solver_configs()), len(expected))

    def test_analysis_runs_through_core_solver_runner(self) -> None:
        from plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
        from setuav_studio.solver import SolverResult, SolverStatus

        api, actions, _statuses = self._headless_api()
        plugin = ElectricalPropulsionPlugin()
        plugin.activate(api)
        self.addCleanup(plugin.deactivate, api)
        api._host.set_project(open_project(TEST_PROJECT_PATH))
        add_airspeed_sweep = next(
            action for action in actions if action.title == "Add Airspeed Sweep Analysis"
        )
        add_airspeed_sweep.callback()

        config = api.get_current_solver_config()
        assert config is not None
        solver_cls = api.solvers.get_solver_class(config.solver_id)
        assert solver_cls is not None
        completed: list[SolverResult] = []
        api.run_solver(solver_cls(config), on_complete=completed.append)
        self._drain_events()

        self.assertEqual(len(completed), 1)
        result = completed[0]
        self.assertEqual(result.status, SolverStatus.COMPLETED)
        self.assertIsNotNone(api.get_solver_result(result.id))

        table = result.tables["propulsion_data"]
        airspeeds = table.get_column("airspeed")
        self.assertEqual(len(airspeeds), 36)
        self.assertEqual((airspeeds[0], airspeeds[-1]), (0.0, 35.0))
        static_thrust = result.summary["static_thrust"]
        self.assertGreater(float(static_thrust.value), 0.0)
        self.assertEqual(static_thrust.unit, "N")
        self.assertEqual(
            set(result.plots),
            {"plot_thrust", "plot_power_current", "plot_rpm", "plot_efficiency"},
        )
        for plot in result.plots.values():
            self.assertGreater(len(plot.series), 0)
            for series in plot.series:
                self.assertEqual(len(table.get_column(series.y_column)), len(airspeeds))

    def test_sweep_solvers_report_progress_per_point(self) -> None:
        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_AIRSPEED_SWEEP,
            SOLVER_ID_OPERATING_POINT,
            SOLVER_ID_THROTTLE_SWEEP,
            AirspeedSweepSolver,
            OperatingPointSolver,
            ThrottleSweepSolver,
        )
        from setuav_studio.solver import SolverConfig, SolverStatus, execute_solver

        doc = open_project(TEST_PROJECT_PATH)
        cases = [
            (
                ThrottleSweepSolver,
                SOLVER_ID_THROTTLE_SWEEP,
                {"airspeed": 15.0, "t_min": 20.0, "t_max": 100.0, "t_step": 20.0},
                "throttle",
                [20.0, 40.0, 60.0, 80.0, 100.0],
            ),
            (
                AirspeedSweepSolver,
                SOLVER_ID_AIRSPEED_SWEEP,
                {"v_min": 0.0, "v_max": 20.0, "v_step": 5.0, "throttle": 100.0},
                "airspeed",
                [0.0, 5.0, 10.0, 15.0, 20.0],
            ),
            (
                OperatingPointSolver,
                SOLVER_ID_OPERATING_POINT,
                {"airspeed": 18.0, "throttle": 80.0},
                "airspeed",
                [18.0],
            ),
        ]
        for solver_cls, solver_id, parameters, x_column, x_values in cases:
            with self.subTest(solver=solver_cls.__name__):
                config = SolverConfig(solver_id=solver_id, name="Propulsion", parameters=parameters)
                token = _RecordingToken()
                result = execute_solver(solver_cls(config, doc), token)

                self.assertEqual(result.status, SolverStatus.COMPLETED)
                table = result.tables["propulsion_data"]
                self.assertEqual(table.get_column(x_column), x_values)
                self.assertEqual(table.row_count(), len(x_values))
                point_reports = [(current, total) for current, total, _ in token.progress[1:-1]]
                self.assertEqual(
                    point_reports,
                    [(index + 1, len(x_values)) for index in range(len(x_values))],
                )

    def test_motor_current_limit_marks_operating_point_infeasible(self) -> None:
        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_OPERATING_POINT,
            OperatingPointSolver,
        )
        from setuav_studio.solver import SolverConfig

        doc = open_project(TEST_PROJECT_PATH)
        config = SolverConfig(
            solver_id=SOLVER_ID_OPERATING_POINT,
            name="Cruise Point",
            parameters={"airspeed": 18.0, "throttle": 80.0},
        )

        within_limit = OperatingPointSolver(config, doc).run()
        self.assertEqual(within_limit.tables["propulsion_data"].get_column("feasible"), [True])

        motor = next(c for c in doc.data["components"] if c["id"] == "motor-cruise")
        motor["parameters"]["max_current"] = 0.001
        over_limit = OperatingPointSolver(config, doc).run()
        self.assertEqual(over_limit.tables["propulsion_data"].get_column("feasible"), [False])

    def test_pythrust_data_dir_resolution(self) -> None:
        """5.17: hardcoded path is gone; resolution prefers env var, then QSettings, then relatives."""
        import os
        import tempfile
        from pathlib import Path

        from PySide6.QtCore import QSettings

        from plugins.electrical_propulsion import database as db_module
        from setuav_studio.ui.settings.settings_pages import StudioSettings

        # 1. Hardcoded user-home absolute path is gone.
        source = Path(db_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("/home/huseyin", source)
        self.assertIn("PYTHRUST_DATA_DIR", source)
        self.assertIn("pythrust_data_dir", source)

        # 2. StudioSettings round-trips the field through QSettings.
        get_qapp()
        original = StudioSettings.load()
        try:
            StudioSettings(
                reopen_last_project=original.reopen_last_project,
                recent_project_limit=original.recent_project_limit,
                pythrust_data_dir="/nonexistent/path",
            ).save()
            reloaded = StudioSettings.load()
            self.assertEqual(reloaded.pythrust_data_dir, "/nonexistent/path")

            # 3. When env is unset and QSettings points at a real tempdir, resolution follows it.
            env = os.environ.pop("PYTHRUST_DATA_DIR", None)
            with tempfile.TemporaryDirectory() as tmp:
                QSettings().setValue("propulsion/pythrust_data_dir", tmp)
                resolved = db_module._resolve_pythrust_data_dir()
                self.assertIsNotNone(resolved)
                self.assertEqual(resolved, Path(tmp))
            # 4. When env + setting are both unset/invalid, resolution may still find a sibling
            #    PyThrust checkout in this dev environment, but never raises.
            QSettings().remove("propulsion/pythrust_data_dir")
            resolved = db_module._resolve_pythrust_data_dir()
            self.assertTrue(resolved is None or isinstance(resolved, Path))
        finally:
            StudioSettings(
                reopen_last_project=original.reopen_last_project,
                recent_project_limit=original.recent_project_limit,
                pythrust_data_dir=original.pythrust_data_dir,
            ).save()
            if env is not None:
                os.environ["PYTHRUST_DATA_DIR"] = env

    @staticmethod
    def _fixture_components() -> list[dict[str, Any]]:
        doc = open_project(TEST_PROJECT_PATH)
        return [c for c in doc.data["components"] if isinstance(c, dict)]

    def test_powertrain_solves_fixture_propulsion_system(self) -> None:
        from plugins.electrical_propulsion.powertrain import (
            build_powertrain,
            find_propulsion_system,
        )

        members = find_propulsion_system(self._fixture_components())
        assert members is not None
        powertrain = build_powertrain(members)

        self.assertEqual(powertrain.unit_count, 1)
        self.assertEqual(powertrain.propeller_data.metadata.id, "APC_12x6")
        point = powertrain.solve(rho=1.225, airspeed_mps=15.0, throttle=1.0)
        self.assertGreater(point.rpm, 1000.0)
        self.assertGreater(point.thrust_n, 0.0)
        self.assertGreater(point.battery_current_a, 0.0)
        self.assertTrue(0.0 <= point.system_efficiency <= 1.0)

    def test_powertrain_scales_totals_with_identical_motor_units(self) -> None:
        from plugins.electrical_propulsion.powertrain import (
            build_powertrain,
            find_propulsion_system,
        )

        components = self._fixture_components()
        single_members = find_propulsion_system(components)
        assert single_members is not None
        single = build_powertrain(single_members)

        motor = next(c for c in components if c["id"] == "motor-cruise")
        propeller = next(c for c in components if c["id"] == "propeller-cruise")
        second_motor = {**deepcopy(motor), "id": "motor-2"}
        second_propeller = {**deepcopy(propeller), "id": "propeller-2", "parent": "motor-2"}
        twin_members = find_propulsion_system([*components, second_motor, second_propeller])
        assert twin_members is not None
        twin = build_powertrain(twin_members)

        self.assertEqual(twin.unit_count, 2)
        self.assertAlmostEqual(twin.current_limit_a, 2.0 * single.current_limit_a)
        one = single.solve(rho=1.225, airspeed_mps=15.0, throttle=0.8)
        two = twin.solve(rho=1.225, airspeed_mps=15.0, throttle=0.8)
        self.assertAlmostEqual(two.rpm, one.rpm)
        self.assertAlmostEqual(two.thrust_n, 2.0 * one.thrust_n)
        self.assertAlmostEqual(two.battery_current_a, 2.0 * one.battery_current_a)
        self.assertAlmostEqual(two.battery_power_w, 2.0 * one.battery_power_w)

    def test_powertrain_rejects_unanalysable_systems(self) -> None:
        from plugins.electrical_propulsion.powertrain import (
            PowertrainError,
            build_powertrain,
            find_propulsion_system,
        )

        components = self._fixture_components()
        propeller = next(c for c in components if c["id"] == "propeller-cruise")
        motor = next(c for c in components if c["id"] == "motor-cruise")

        unlinked = [c for c in components if c is not propeller]
        unlinked.append({k: v for k, v in propeller.items() if k != "catalog_id"})
        members = find_propulsion_system(unlinked)
        assert members is not None
        with self.assertRaisesRegex(PowertrainError, "not linked to catalog data"):
            build_powertrain(members)

        other_motor = deepcopy(motor)
        other_motor["id"] = "motor-2"
        other_motor["parameters"]["kv"] = 1200.0
        other_propeller = {**deepcopy(propeller), "id": "propeller-2", "parent": "motor-2"}
        members = find_propulsion_system([*components, other_motor, other_propeller])
        assert members is not None
        with self.assertRaisesRegex(PowertrainError, "identical motor and propeller units"):
            build_powertrain(members)

        bare_motor = {**deepcopy(motor), "id": "motor-2"}
        members = find_propulsion_system([*components, bare_motor])
        assert members is not None
        with self.assertRaisesRegex(PowertrainError, "exactly one propeller"):
            build_powertrain(members)

    def test_propulsion_results_convert_to_display_units(self) -> None:
        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_AIRSPEED_SWEEP,
            AirspeedSweepSolver,
        )
        from setuav_studio.solver import SolverConfig
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        saved_units = {
            quantity: um.get_display_unit(quantity) for quantity in ("velocity", "force")
        }

        def restore_units() -> None:
            for quantity, unit in saved_units.items():
                um.set_display_unit(quantity, unit)

        self.addCleanup(restore_units)

        config = SolverConfig(
            solver_id=SOLVER_ID_AIRSPEED_SWEEP,
            name="Airspeed Sweep",
            parameters={"v_min": 0.0, "v_max": 20.0, "v_step": 5.0, "throttle": 100.0},
        )
        result = AirspeedSweepSolver(config, open_project(TEST_PROJECT_PATH)).run()
        table = result.tables["propulsion_data"]
        airspeed_column = table.get_column_def("airspeed")
        thrust_column = table.get_column_def("thrust")
        assert airspeed_column is not None
        assert thrust_column is not None

        um.set_display_unit("velocity", "m/s")
        um.set_display_unit("force", "N")
        self.assertEqual(airspeed_column.header_text(use_display_units=True), "Airspeed [m/s]")
        self.assertEqual(thrust_column.header_text(use_display_units=True), "Thrust [N]")
        self.assertEqual(table.get_column_display_values("thrust"), table.get_column("thrust"))

        um.set_display_unit("velocity", "ft/s")
        um.set_display_unit("force", "lbf")
        self.assertEqual(airspeed_column.header_text(use_display_units=True), "Airspeed [ft/s]")
        self.assertEqual(thrust_column.header_text(use_display_units=True), "Thrust [lbf]")
        for key, quantity in (("airspeed", "velocity"), ("thrust", "force")):
            for shown, stored in zip(
                table.get_column_display_values(key), table.get_column(key), strict=True
            ):
                self.assertAlmostEqual(shown, um.to_display(stored, quantity))

        static_thrust = result.summary["static_thrust"]
        shown_thrust, shown_unit = static_thrust.display_value_and_unit()
        self.assertEqual(shown_unit, "lbf")
        self.assertAlmostEqual(
            float(shown_thrust), um.to_display(float(static_thrust.value), "force")
        )

    def _drain_events(self, iterations: int = 15) -> None:
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().waitForDone()
        for _ in range(iterations):
            self.app.processEvents()

    @staticmethod
    def _headless_api() -> tuple[StudioAPI, list[ActionContribution], list[tuple[str, str, int]]]:
        api = StudioAPI()
        actions: list[ActionContribution] = []
        statuses: list[tuple[str, str, int]] = []
        api._host.bind_action_handlers(actions.append)
        api._host.bind_status_handler(
            lambda message, level, timeout_ms: statuses.append((message, level, timeout_ms))
        )
        return api, actions, statuses


if __name__ == "__main__":
    unittest.main()
