"""Unit tests for the Electrical Propulsion plugin and component property editors."""

from __future__ import annotations

import itertools
import unittest
from copy import deepcopy
from typing import Any
from unittest.mock import patch

from PySide6.QtWidgets import QDialog

from plugins.electrical_propulsion.editors import BatteryEditor, PropulsorEditor
from plugins.electrical_propulsion.editors.propulsor import (
    PropulsorMotorEditor,
    PropulsorPropellerEditor,
)
from plugins.electrical_propulsion.models.propulsor import PROPULSOR_TYPE, propulsor_mass
from setuav_studio.api import StudioAPI, ToolbarContribution
from setuav_studio.plugin import PluginManager
from setuav_studio.project import open_project
from tests._common import TEST_PROJECT_PATH, get_qapp


class _CatalogSelection:
    """Catalog dialog stand-in that accepts a preselected motor or propeller entry."""

    selected_motor: Any = None
    selected_propeller: Any = None

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

        self.assertIn(PROPULSOR_TYPE, api._component_editors)
        self.assertIn("org.setuav.core:battery", api._component_editors)
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

        self.assertIn(PROPULSOR_TYPE, api._component_editors)
        self.assertIn("tools/electrical propulsion", window.action_manager.menus)
        self.assertIn("studio:project-explorer", window._panels)
        self.assertIn("studio:properties", window._panels)

        manager.deactivate(plugin.id)

        self.assertNotIn(PROPULSOR_TYPE, api._component_editors)
        self.assertNotIn(PROPULSOR_TYPE, api._component_icons)
        self.assertNotIn("tools/electrical propulsion", window.action_manager.menus)
        self.assertIn("studio:project-explorer", window._panels)
        self.assertIn("studio:properties", window._panels)

        manager.activate_plugin(plugin.id)
        self.assertIn(PROPULSOR_TYPE, api._component_editors)
        window.close()
        window.deleteLater()

    def _propulsor(self) -> tuple[StudioAPI, dict[str, Any]]:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)
        propulsor = next(c for c in doc.data["components"] if c["type"] == PROPULSOR_TYPE)
        return api, propulsor

    def _page(self, page: Any) -> Any:
        self.addCleanup(page.deleteLater)
        return page

    def test_propulsor_page_sums_up_its_motor_and_propeller(self) -> None:
        api, propulsor = self._propulsor()
        editor = self._page(PropulsorEditor(api, propulsor))

        self.assertEqual(editor._property_value(editor.general_table, "name"), propulsor["name"])
        self.assertEqual(editor._property_value(editor.general_table, "mass"), "136.0")
        self.assertEqual(editor._property_value(editor.general_table, "motor"), "X2814 KV900 3-4S")
        self.assertEqual(editor._property_value(editor.general_table, "propeller"), "APC_12x6")

    def test_motor_and_propeller_pages_show_catalog_values_read_only(self) -> None:
        api, propulsor = self._propulsor()
        motor = self._page(PropulsorMotorEditor(api, propulsor))
        propeller = self._page(PropulsorPropellerEditor(api, propulsor))

        self.assertEqual(motor._property_value(motor.motor_table, "motor_manufacturer"), "SunnySky")
        for table, key, text, unit in (
            (motor.motor_table, "motor_kv", "900", "RPM/V"),
            (propeller.propeller_table, "propeller_diameter", "304.8", "mm"),
            (propeller.propeller_table, "propeller_pitch", "152.4", "mm"),
            (propeller.propeller_table, "propeller_blade_count", "2", ""),
        ):
            cell = motor._property_cell(table, key)
            assert cell is not None
            self.assertTrue(cell.isReadOnly(), key)
            self.assertEqual(cell.line_edit.text(), text)
            self.assertEqual(cell.unit_label.text(), unit)
        for page, table, key in (
            (motor, motor.motor_table, "motor_mass"),
            (propeller, propeller.propeller_table, "propeller_mass"),
        ):
            cell = page._property_cell(table, key)
            assert cell is not None
            self.assertFalse(cell.isReadOnly(), key)

    def test_new_propulsor_pages_wait_for_catalog_picks(self) -> None:
        from plugins.electrical_propulsion.creation import new_propulsor

        api, _propulsor = self._propulsor()
        empty = new_propulsor("propulsor-2", "Propulsor 2")
        assert api.project is not None
        api.project.data["components"].append(empty)
        motor = self._page(PropulsorMotorEditor(api, empty))
        propeller = self._page(PropulsorPropellerEditor(api, empty))

        self.assertIn("Not selected", motor._property_value(motor.motor_table, "motor_model"))
        self.assertIn(
            "Not selected",
            propeller._property_value(propeller.propeller_table, "propeller_catalog_id"),
        )
        for page, table, key in (
            (motor, motor.motor_table, "motor_kv"),
            (motor, motor.motor_table, "motor_mass"),
            (propeller, propeller.propeller_table, "propeller_mass"),
        ):
            cell = page._property_cell(table, key)
            assert cell is not None
            self.assertTrue(cell.isReadOnly(), key)
            self.assertEqual(cell.line_edit.text(), "")
        self.assertEqual(empty["mass"], 0.0)

    def test_catalog_picks_fill_the_pages_with_undo(self) -> None:
        from plugins.electrical_propulsion.database import (
            get_motor_database,
            get_propeller_database,
        )

        api, propulsor = self._propulsor()
        opened = deepcopy(propulsor)
        motor_page = self._page(PropulsorMotorEditor(api, propulsor))
        propeller_page = self._page(PropulsorPropellerEditor(api, propulsor))
        motor_db = get_motor_database()
        _CatalogSelection.selected_motor = next(
            entry
            for entry in (motor_db.get(name) for name in motor_db.list_motors())
            if entry is not None and float(entry.kv) != 900.0
        )
        _CatalogSelection.selected_propeller = get_propeller_database().get("APC_13x6.5E")
        with patch(
            "plugins.electrical_propulsion.editors.propulsor.ComponentCatalogDialog",
            _CatalogSelection,
        ):
            motor_page._open_catalog()
            propeller_page._open_catalog()

        motor = _CatalogSelection.selected_motor
        params = propulsor["parameters"]
        self.assertEqual(params["motor_kv"], float(motor.kv))
        self.assertEqual(params["motor_model"], motor.name)
        self.assertEqual(params["motor_mass"], float(motor.weight_g))
        self.assertEqual(propulsor["mass"], propulsor_mass(params))
        self.assertEqual(params["propeller_catalog_id"], "APC_13x6.5E")
        self.assertEqual(params["propeller_diameter"], 330.2)
        # The propeller mass is the user's and stays as entered.
        self.assertEqual(params["propeller_mass"], 28.0)
        kv_cell = motor_page._property_cell(motor_page.motor_table, "motor_kv")
        assert kv_cell is not None
        self.assertEqual(kv_cell.line_edit.text(), str(round(float(motor.kv))))

        api.undo()
        api.undo()
        self.assertEqual(propulsor, opened)
        kv_cell = motor_page._property_cell(motor_page.motor_table, "motor_kv")
        assert kv_cell is not None
        self.assertEqual(kv_cell.line_edit.text(), "900")

    def test_propeller_mass_sums_into_the_component_mass(self) -> None:
        api, propulsor = self._propulsor()
        page = self._page(PropulsorPropellerEditor(api, propulsor))
        cell = page._property_cell(page.propeller_table, "propeller_mass")
        assert cell is not None
        cell.setValue(35.0)

        self.assertEqual(propulsor["parameters"]["propeller_mass"], 35.0)
        self.assertEqual(propulsor["mass"], 108.0 + 35.0)
        api.undo()
        self.assertEqual(propulsor["mass"], 136.0)

    def test_explorer_lists_the_motor_and_propeller_under_their_propulsor(self) -> None:
        from plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
        from setuav_studio.ui.panels.project_explorer.tree import ProjectExplorer

        api, _propulsor = self._propulsor()
        plugin = ElectricalPropulsionPlugin()
        plugin.activate(api)
        self.addCleanup(plugin.deactivate, api)
        explorer = self._page(ProjectExplorer(api))
        explorer.set_project(api.project)

        item = explorer._item_map["propulsor-cruise"]
        children = [item.child(index).text(0) for index in range(item.childCount())]
        self.assertEqual(children, ["Motor", "Propeller"])
        motor_item = explorer._item_map["propulsor-cruise:motor"]
        editor = api.create_component_editor(explorer._element_map[motor_item])
        self.assertIsInstance(editor, PropulsorMotorEditor)
        assert editor is not None
        editor.deleteLater()

    def _battery_editor(self) -> tuple[StudioAPI, dict[str, Any], BatteryEditor]:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)
        battery_comp = next(
            c for c in doc.data["components"] if c.get("type") == "org.setuav.core:battery"
        )
        editor = BatteryEditor(api, battery_comp)
        self.addCleanup(editor.deleteLater)
        return api, battery_comp, editor

    def test_battery_editor(self) -> None:
        from PySide6.QtCore import Qt

        from plugins.electrical_propulsion.models.battery import BATTERY_OVERRIDES, battery_pack

        api, battery_comp, editor = self._battery_editor()
        opened = deepcopy(battery_comp)
        params = battery_comp["parameters"]

        # Opening the editor leaves the project untouched; derived values are read-only.
        self.assertEqual(battery_comp, opened)
        self.assertFalse(api.can_undo)
        self.assertEqual(editor._property_value(editor.config_table, "chemistry"), "LiPo")
        for key in BATTERY_OVERRIDES:
            label = editor._label_item(editor.cell_table, key)
            self.assertEqual(label.checkState(), Qt.CheckState.Unchecked)
            cell = editor._property_cell(editor.cell_table, key)
            assert cell is not None
            self.assertTrue(cell.isReadOnly())

        # 6S: the pack mass and values follow the chemistry's scaling rules.
        cell_count = editor._property_cell(editor.config_table, "cell_count")
        assert cell_count is not None
        cell_count.setValue(6)
        self.assertEqual(params["cell_count"], 6)
        derived_mass = battery_pack(params).mass_g
        self.assertAlmostEqual(derived_mass, 2 * float(opened["mass"]))
        self.assertEqual(battery_comp["mass"], derived_mass)
        self.assertEqual(editor._property_text(editor.general_table, 2), f"{derived_mass:.1f}")
        nominal = editor._property_cell(editor.pack_table, "nominal_voltage")
        assert nominal is not None
        self.assertTrue(nominal.isReadOnly())
        self.assertEqual(nominal.line_edit.text(), "22.2")

        # Overriding the pack mass starts from the derived value and makes it editable.
        editor._label_item(editor.cell_table, "pack_mass").setCheckState(Qt.CheckState.Checked)
        self.assertEqual(params["pack_mass"], derived_mass)
        pack_mass = editor._property_cell(editor.cell_table, "pack_mass")
        assert pack_mass is not None
        self.assertFalse(pack_mass.isReadOnly())
        pack_mass.setValue(1200.0)
        self.assertEqual(params["pack_mass"], 1200.0)
        self.assertEqual(battery_comp["mass"], 1200.0)

        # Clearing the override returns to the derived mass.
        editor._label_item(editor.cell_table, "pack_mass").setCheckState(Qt.CheckState.Unchecked)
        self.assertIsNone(params["pack_mass"])
        self.assertEqual(battery_comp["mass"], derived_mass)

        while api.can_undo:
            api.undo()
        self.assertEqual(battery_comp, opened)

    def test_battery_editor_follows_undo(self) -> None:
        api, battery_comp, editor = self._battery_editor()
        cell = editor._property_cell(editor.config_table, "cell_count")
        assert cell is not None
        cell.setValue(6)
        self.assertEqual(battery_comp["parameters"]["cell_count"], 6)

        api.undo()
        cell = editor._property_cell(editor.config_table, "cell_count")
        assert cell is not None
        self.assertEqual(cell.line_edit.text(), "3")

    def test_battery_editor_chemistry_change_clears_overrides(self) -> None:
        from PySide6.QtCore import Qt

        from plugins.electrical_propulsion.chemistry import chemistry_profile

        api, battery_comp, editor = self._battery_editor()
        opened = deepcopy(battery_comp)
        params = battery_comp["parameters"]

        editor._label_item(editor.cell_table, "c_rate").setCheckState(Qt.CheckState.Checked)
        self.assertEqual(params["c_rate"], chemistry_profile("LiPo").c_rate)
        editor._on_chemistry_changed("Li-Ion")
        li_ion = chemistry_profile("Li-Ion")
        self.assertEqual(params["chemistry"], "Li-Ion")
        self.assertIsNone(params["c_rate"])
        self.assertAlmostEqual(battery_comp["mass"], 3 * li_ion.pack_mass_per_cell_g(6.0))
        self.assertEqual(editor._property_value(editor.config_table, "chemistry"), "Li-Ion")
        charge = editor._property_cell(editor.cell_table, "charge_voltage")
        assert charge is not None
        self.assertEqual(charge.line_edit.text(), "4.2")

        while api.can_undo:
            api.undo()
        self.assertEqual(battery_comp, opened)

    def test_battery_model_derives_the_pack_from_its_chemistry(self) -> None:
        from plugins.electrical_propulsion.models import BatteryModel

        doc = open_project(TEST_PROJECT_PATH)
        battery_comp = next(
            c for c in doc.data["components"] if c.get("type") == "org.setuav.core:battery"
        )
        self.assertEqual(
            {f.key for f in BatteryModel.get_fields()}, set(battery_comp["parameters"])
        )

        model = BatteryModel(deepcopy(battery_comp))
        pack = model.pack
        profile = pack.profile
        self.assertEqual(profile.chemistry, "LiPo")
        self.assertAlmostEqual(pack.capacity_mah, 6000.0)
        self.assertAlmostEqual(pack.nominal_voltage_v, 3 * 3.7)
        self.assertAlmostEqual(pack.full_voltage_v, 3 * 4.2)
        self.assertAlmostEqual(
            pack.internal_resistance_ohm, 3 * profile.resistance_mohm_ah / 1000.0 / 6.0
        )
        self.assertAlmostEqual(pack.max_current_a, profile.c_rate * 6.0)
        self.assertAlmostEqual(pack.energy_wh, pack.curves.mean_ocv_v * 6.0 * 3)
        self.assertAlmostEqual(pack.mass_g, 3 * profile.pack_mass_per_cell_g(6.0))
        self.assertEqual(pack.mass_g, battery_comp["mass"])
        props = model.get_exposed_properties()
        self.assertEqual(props["chemistry"], "LiPo")
        self.assertAlmostEqual(props["capacity"], pack.capacity_mah)
        self.assertAlmostEqual(props["pack_mass"], pack.mass_g)

        rate_map = pack.rate_map()
        self.assertEqual((rate_map.series, rate_map.parallel), (3, 1))
        self.assertEqual(rate_map.capacity_ah, 6.0)

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

    def test_analysis_buttons_add_solver_configs(self) -> None:
        from plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_AIRSPEED_SWEEP,
            SOLVER_ID_OPERATING_POINT,
            SOLVER_ID_THROTTLE_SWEEP,
            AirspeedSweepSolver,
            OperatingPointSolver,
            ThrottleSweepSolver,
        )

        api, buttons, statuses = self._headless_api()
        plugin = ElectricalPropulsionPlugin()
        plugin.activate(api)
        self.addCleanup(plugin.deactivate, api)

        self._press(buttons, "Add Airspeed Sweep Analysis")
        self.assertEqual(api.get_solver_configs(), {})
        self.assertEqual(statuses[-1][:2], ("Open or create a project first.", "warning"))

        api._host.set_project(open_project(TEST_PROJECT_PATH))
        expected = [
            ("Throttle Sweep Analysis", SOLVER_ID_THROTTLE_SWEEP, ThrottleSweepSolver),
            ("Airspeed Sweep Analysis", SOLVER_ID_AIRSPEED_SWEEP, AirspeedSweepSolver),
            ("Operating Point Analysis", SOLVER_ID_OPERATING_POINT, OperatingPointSolver),
        ]
        button_titles = {
            "Operating Point Analysis": "Add Propulsion Operating Point Analysis",
        }
        for name, solver_id, solver_cls in expected:
            self._press(buttons, button_titles.get(name, f"Add {name}"))
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

        api, buttons, _statuses = self._headless_api()
        plugin = ElectricalPropulsionPlugin()
        plugin.activate(api)
        self.addCleanup(plugin.deactivate, api)
        api._host.set_project(open_project(TEST_PROJECT_PATH))
        self._press(buttons, "Add Airspeed Sweep Analysis")

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
                config = SolverConfig(
                    solver_id=solver_id,
                    name="Propulsion",
                    parameters={**solver_cls.default_parameters(), **parameters},
                )
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
            parameters={
                **OperatingPointSolver.default_parameters(),
                "airspeed": 18.0,
                "throttle": 80.0,
            },
        )

        within_limit = OperatingPointSolver(config, doc).run()
        table = within_limit.tables["propulsion_data"]
        self.assertEqual(table.get_column("feasible"), [True])
        self.assertEqual(within_limit.summary["feasible_points"].value, 1)
        self.assertEqual(within_limit.summary["endurance"].value, table.get_column("endurance")[0])
        self.assertNotIn("static_thrust", within_limit.summary)

        propulsor = next(c for c in doc.data["components"] if c["id"] == "propulsor-cruise")
        propulsor["parameters"]["motor_max_current"] = 0.001
        over_limit = OperatingPointSolver(config, doc).run()
        self.assertEqual(over_limit.tables["propulsion_data"].get_column("feasible"), [False])
        self.assertEqual(over_limit.summary["feasible_points"].value, 0)
        self.assertNotIn("max_thrust", over_limit.summary)

    def test_throttle_sweep_summary_reports_its_own_points(self) -> None:
        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_THROTTLE_SWEEP,
            ThrottleSweepSolver,
        )
        from setuav_studio.solver import SolverConfig

        config = SolverConfig(
            solver_id=SOLVER_ID_THROTTLE_SWEEP,
            name="Throttle Sweep",
            parameters={**ThrottleSweepSolver.default_parameters(), "airspeed": 15.0},
        )
        result = ThrottleSweepSolver(config, open_project(TEST_PROJECT_PATH)).run()
        table = result.tables["propulsion_data"]
        thrust = table.get_column("thrust")
        endurance = table.get_column("endurance")
        feasible = table.get_column("feasible")

        # A sweep in flight has no static point and no cruise of its own.
        self.assertNotIn("static_thrust", result.summary)
        self.assertNotIn("endurance", result.summary)
        self.assertEqual(
            result.summary["max_thrust"].value,
            max(t for t, ok in zip(thrust, feasible, strict=True) if ok),
        )
        self.assertTrue(0.0 < float(result.summary["best_efficiency"].value) < 1.0)
        self.assertIn(result.summary["best_efficiency_at"].value, table.get_column("throttle"))
        # More throttle draws more power and so empties the pack sooner.
        flying = [e for e, ok in zip(endurance, feasible, strict=True) if ok]
        self.assertGreater(len(flying), 2)
        self.assertTrue(all(b < a for a, b in itertools.pairwise(flying)))

    def test_powertrain_loads_only_its_own_propeller(self) -> None:
        from plugins.electrical_propulsion import database

        database._PROP_ENTRIES.clear()
        with patch.object(database, "_PROP_DB", None):
            entry = database.get_propeller_entry("APC_13x6.5E")
            assert entry is not None
            self.assertEqual(entry.metadata.id, "APC_13x6.5E")
            self.assertIsNone(database._PROP_DB)
            self.assertEqual(list(database._PROP_ENTRIES), ["APC_13x6.5E"])
            self.assertIsNone(database.get_propeller_entry("APC_does_not_exist"))

    def test_pythrust_data_dir_resolution(self) -> None:
        """5.17: hardcoded path is gone; resolution prefers env var, then QSettings, then relatives."""
        import os
        import tempfile
        from pathlib import Path

        from PySide6.QtCore import QSettings

        from plugins.electrical_propulsion import database as db_module

        # 1. Hardcoded user-home absolute path is gone.
        source = Path(db_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("/home/huseyin", source)
        self.assertIn("PYTHRUST_DATA_DIR", source)
        self.assertIn("pythrust_data_dir", source)

        get_qapp()
        env = os.environ.pop("PYTHRUST_DATA_DIR", None)
        try:
            # 2. When env is unset and QSettings points at a real tempdir, resolution follows it.
            with tempfile.TemporaryDirectory() as tmp:
                QSettings().setValue("propulsion/pythrust_data_dir", tmp)
                resolved = db_module._resolve_pythrust_data_dir()
                self.assertIsNotNone(resolved)
                self.assertEqual(resolved, Path(tmp))
            # 3. When env + setting are both unset/invalid, resolution may still find a sibling
            #    PyThrust checkout in this dev environment, but never raises.
            QSettings().remove("propulsion/pythrust_data_dir")
            resolved = db_module._resolve_pythrust_data_dir()
            self.assertTrue(resolved is None or isinstance(resolved, Path))
        finally:
            if env is not None:
                os.environ["PYTHRUST_DATA_DIR"] = env

    @staticmethod
    def _fixture_components() -> list[dict[str, Any]]:
        doc = open_project(TEST_PROJECT_PATH)
        return [c for c in doc.data["components"] if isinstance(c, dict)]

    @staticmethod
    def _powertrain(components: list[dict[str, Any]], state_of_charge: float = 1.0) -> Any:
        from plugins.electrical_propulsion.powertrain import (
            build_powertrain,
            find_powertrain_members,
        )

        members = find_powertrain_members(components)
        assert members is not None
        return build_powertrain(members, state_of_charge=state_of_charge)

    def test_powertrain_solves_fixture_propulsor(self) -> None:
        powertrain = self._powertrain(self._fixture_components())

        self.assertEqual(len(powertrain.units), 1)
        (unit,) = powertrain.units
        self.assertEqual(unit.prop_entry.metadata.id, "APC_12x6")
        (pack,) = powertrain.network.packs
        self.assertEqual((pack.series, pack.parallel), (3, 1))
        point = powertrain.solve(rho=1.225, airspeed_mps=15.0, throttle=1.0)
        self.assertTrue(point.feasible)
        self.assertGreater(point.rpm, 1000.0)
        self.assertGreater(point.thrust_n, 0.0)
        self.assertGreater(point.battery_current_a, 0.0)
        self.assertTrue(0.0 <= point.system_efficiency <= 1.0)
        # The pack voltage sags below its open-circuit value under load.
        self.assertLess(point.battery_voltage_v, powertrain.open_circuit_voltage_v)

        half = self._powertrain(self._fixture_components(), state_of_charge=0.5).solve(
            rho=1.225, airspeed_mps=15.0, throttle=1.0
        )
        self.assertLess(half.battery_voltage_v, point.battery_voltage_v)
        self.assertLess(half.thrust_n, point.thrust_n)

    def test_powertrain_without_an_operating_point_is_infeasible(self) -> None:
        powertrain = self._powertrain(self._fixture_components())
        # At a small throttle and a high airspeed the propeller would windmill.
        point = powertrain.solve(rho=1.225, airspeed_mps=30.0, throttle=0.05)
        self.assertFalse(point.feasible)
        self.assertEqual(point.units[0].infeasible_reason, "no_bracket")

    def test_powertrain_discharge_time_at_constant_power(self) -> None:
        from plugins.electrical_propulsion.powertrain import PowertrainError

        powertrain = self._powertrain(self._fixture_components())

        light = powertrain.discharge_time_s(power_w=30.0, final_soc=0.2)
        heavy = powertrain.discharge_time_s(power_w=300.0, final_soc=0.2)
        # At 30 W the resistive loss is small: the time approaches the open-circuit
        # energy between 100 % and 20 % state of charge divided by the power.
        (battery,) = powertrain.network.packs
        steps = 800
        ocv_energy_wh = (
            battery.capacity_ah
            * battery.series
            * battery.parallel
            * sum(battery.ocv(0.8 * (k + 0.5) / steps) for k in range(steps))
            * 0.8
            / steps
        )
        self.assertLess(light / 3600.0, ocv_energy_wh / 30.0)
        self.assertGreater(light / 3600.0, 0.98 * ocv_energy_wh / 30.0)
        self.assertLess(heavy * 10.0, light)
        with self.assertRaisesRegex(PowertrainError, "not below"):
            self._powertrain(self._fixture_components(), state_of_charge=0.2).discharge_time_s(
                power_w=30.0, final_soc=0.2
            )

    def test_propulsors_share_one_bus(self) -> None:
        components = self._fixture_components()
        single = self._powertrain(components)
        propulsor = next(c for c in components if c["id"] == "propulsor-cruise")
        twin = self._powertrain([*components, {**deepcopy(propulsor), "id": "propulsor-2"}])

        self.assertEqual(len(twin.units), 2)
        one = single.solve(rho=1.225, airspeed_mps=15.0, throttle=0.6)
        two = twin.solve(rho=1.225, airspeed_mps=15.0, throttle=0.6)
        # Both units load the same pack: its voltage sags further, so each unit
        # turns slightly slower than a single unit would.
        self.assertLess(two.battery_voltage_v, one.battery_voltage_v)
        self.assertLess(two.rpm, one.rpm)
        self.assertLess(two.thrust_n, 2.0 * one.thrust_n)
        ocv_v, resistance_ohm = twin.network.thevenin(twin.network_state)
        for point in (one, two):
            self.assertAlmostEqual(
                point.battery_voltage_v,
                ocv_v - point.battery_current_a * resistance_ohm,
                delta=1e-6,
            )
        self.assertAlmostEqual(
            two.battery_power_w, two.battery_voltage_v * two.battery_current_a, delta=1e-6
        )

    def test_batteries_feed_the_bus_in_parallel(self) -> None:
        components = self._fixture_components()
        single = self._powertrain(components)
        battery = next(c for c in components if c["id"] == "battery-main")
        double = self._powertrain([*components, {**deepcopy(battery), "id": "battery-2"}])

        self.assertEqual(len(double.network.packs), 2)
        # Two packs halve the source resistance and double the charge.
        self.assertAlmostEqual(
            double.network.thevenin(double.network_state)[1],
            0.5 * single.network.thevenin(single.network_state)[1],
        )
        one = single.solve(rho=1.225, airspeed_mps=15.0, throttle=0.6)
        two = double.solve(rho=1.225, airspeed_mps=15.0, throttle=0.6)
        self.assertGreater(two.battery_voltage_v, one.battery_voltage_v)
        # Each pack carries half the current, so the pair loses less than twice the
        # single pack's resistive energy and lasts a little longer than twice as long.
        single_s = single.discharge_time_s(power_w=30.0, final_soc=0.2)
        double_s = double.discharge_time_s(power_w=30.0, final_soc=0.2)
        self.assertGreater(double_s, 2.0 * single_s)
        self.assertLess(double_s, 2.01 * single_s)

    def test_powertrain_rejects_unanalysable_systems(self) -> None:
        from plugins.electrical_propulsion.powertrain import (
            PowertrainError,
            build_powertrain,
            find_powertrain_members,
        )

        components = self._fixture_components()
        propulsor = next(c for c in components if c["id"] == "propulsor-cruise")
        battery = next(c for c in components if c["id"] == "battery-main")
        self.assertIsNone(find_powertrain_members([]))

        cases = []
        for catalog_id, message in ((None, "has no propeller"), ("APC_none", "no data")):
            unlinked = deepcopy(propulsor)
            unlinked["parameters"]["propeller_catalog_id"] = catalog_id
            cases.append(([unlinked, battery], message))
        motorless = deepcopy(propulsor)
        motorless["parameters"]["motor_model"] = None
        cases.append(([motorless, battery], "has no motor"))
        cases.append(([propulsor], "requires: Battery"))
        cases.append(([battery], "requires: Propulsor"))
        four_cell = deepcopy(battery)
        four_cell["id"] = "battery-4s"
        four_cell["parameters"]["cell_count"] = 4
        cases.append(([propulsor, battery, four_cell], "cannot share one bus"))
        for members_components, message in cases:
            with self.subTest(message=message):
                members = find_powertrain_members(members_components)
                assert members is not None
                with self.assertRaisesRegex(PowertrainError, message):
                    build_powertrain(members, state_of_charge=1.0)

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
            parameters={
                **AirspeedSweepSolver.default_parameters(),
                "v_min": 0.0,
                "v_max": 20.0,
                "v_step": 5.0,
                "throttle": 100.0,
            },
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
    def _headless_api() -> tuple[StudioAPI, list[ToolbarContribution], list[tuple[str, str, int]]]:
        api = StudioAPI()
        buttons: list[ToolbarContribution] = []
        statuses: list[tuple[str, str, int]] = []
        api._host.bind_toolbar_handlers(buttons.append)
        api._host.bind_status_handler(
            lambda message, level, timeout_ms: statuses.append((message, level, timeout_ms))
        )
        return api, buttons, statuses

    @staticmethod
    def _press(buttons: list[ToolbarContribution], title: str) -> None:
        button = next(button for button in buttons if button.title == title)
        assert button.callback is not None
        button.callback()


if __name__ == "__main__":
    unittest.main()
