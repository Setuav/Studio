"""Unit tests for the Electrical Propulsion plugin and component property editors."""

from __future__ import annotations

import unittest

from setuav_studio.plugin_system import PluginManager, StudioAPI
from setuav_studio.plugins.core import CorePlugin
from setuav_studio.plugins.electrical_propulsion.editors import (
    BatteryEditor,
    ElectricPropulsionSystemEditor,
    EscEditor,
    MotorEditor,
    PropellerEditor,
)
from setuav_studio.project import open_project
from tests._common import TEST_PROJECT_PATH, get_qapp


class TestElectricalPropulsion(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_plugin_discovery_and_registration(self) -> None:
        from setuav_studio.shell import MainWindow

        api = StudioAPI()
        _win = MainWindow(api)
        pm = PluginManager(api)
        pm.activate(CorePlugin())
        issues = pm.discover()
        self.assertEqual(len(issues), 0)
        self.assertIn("org.setuav.studio.electrical_propulsion", pm._plugins)

        # Check registered editors
        self.assertIn("org.setuav.core:motor", api._component_editors)
        self.assertIn("org.setuav.core:propeller", api._component_editors)
        self.assertIn("org.setuav.core:esc", api._component_editors)
        self.assertIn("org.setuav.core:battery", api._component_editors)
        self.assertIn("org.setuav.core:electric-propulsion-system", api._component_editors)

    def test_motor_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api.set_project(doc)

        motor_comp = next(
            c for c in doc.data["components"] if c.get("type") == "org.setuav.core:motor"
        )
        editor = MotorEditor(api, motor_comp)

        self.assertEqual(editor._property_text(editor.general_table, 0), motor_comp.get("name"))
        self.assertEqual(editor._property_text(editor.parameters_table, 0), "900")

        # Edit KV (row 0 in parameters_table)
        editor.parameters_table.item(0, 1).setText("1050")
        self.assertEqual(motor_comp["parameters"]["kv"], 1050.0)

        # Undo
        api.undo()
        self.assertEqual(motor_comp["parameters"]["kv"], 900.0)

    def test_battery_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api.set_project(doc)

        battery_comp = next(
            c for c in doc.data["components"] if c.get("type") == "org.setuav.core:battery"
        )
        editor = BatteryEditor(api, battery_comp)

        self.assertEqual(editor._property_text(editor.cell_table, 0), "LiPo")

        # Change Series Count to 6S; the editor derives mass from the fixture's
        # cell mass, parallel count, and packaging mass values.
        editor.pack_table.item(0, 1).setText("6")
        params = battery_comp["parameters"]
        expected_mass = 6 * int(params.get("parallel_count", 1)) * float(
            params["cell_mass"]
        ) + float(params.get("packaging_mass", 40.0))
        self.assertEqual(battery_comp["mass"], expected_mass)
        self.assertEqual(editor._property_text(editor.general_table, 2), f"{expected_mass:.1f}")

    def test_esc_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api.set_project(doc)

        esc_comp = next(c for c in doc.data["components"] if c.get("type") == "org.setuav.core:esc")
        editor = EscEditor(api, esc_comp)

        self.assertEqual(editor._property_text(editor.parameters_table, 0), "50.0")

    def test_propeller_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api.set_project(doc)

        prop_comp = next(
            c for c in doc.data["components"] if c.get("type") == "org.setuav.core:propeller"
        )
        editor = PropellerEditor(api, prop_comp)

        dia = str(prop_comp["parameters"]["diameter"])
        pitch = str(prop_comp["parameters"]["pitch"])
        self.assertEqual(editor._property_text(editor.parameters_table, 0), dia)
        self.assertEqual(editor._property_text(editor.parameters_table, 1), pitch)
        self.assertEqual(editor._property_text(editor.parameters_table, 2), "2")

    def test_assembly_editor(self) -> None:
        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api.set_project(doc)

        asm = doc.data["assemblies"][0]
        editor = ElectricPropulsionSystemEditor(api, asm)

        self.assertEqual(editor._property_text(editor.general_table, 0), "Main Propulsion")
        self.assertEqual(editor._property_text(editor.members_table, 0), "battery-main")
        self.assertEqual(editor._property_text(editor.members_table, 2), "motor-cruise")
        self.assertEqual(editor._property_text(editor.members_table, 3), "propeller-cruise")

    def test_catalog_database_and_dialog(self) -> None:
        from setuav_studio.plugins.electrical_propulsion.catalog_dialog import (
            ComponentCatalogDialog,
        )
        from setuav_studio.plugins.electrical_propulsion.database import (
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

    def test_propulsion_controls_and_analysis_run(self) -> None:
        from setuav_studio.plugins.core import CorePlugin
        from setuav_studio.plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
        from setuav_studio.shell import MainWindow

        api = StudioAPI()
        win = MainWindow(api)
        pm = PluginManager(api)
        pm.activate(CorePlugin())
        pm.activate(ElectricalPropulsionPlugin())
        pm.discover()
        win.restore_window_layout()

        doc = open_project(TEST_PROJECT_PATH)
        win.open_project(doc.location)
        api.switch_workspace("studio.workspace.propulsion")

        controls = self._dock_content(win._panels["propulsion.controls_dock"][1])
        results = self._dock_content(win._panels["propulsion.results_dock"][1])
        charts = self._dock_content(win._panels["propulsion.charts_dock"][1])

        # Run analysis (background worker via QThreadPool)
        controls.run_button.click()
        self._drain_events()

        # Verify summary results are populated
        static_thrust_str = results.summary_table.item(0, 1).text()
        self.assertIn("N", static_thrust_str)
        self.assertNotEqual(static_thrust_str, "-")

        # Verify charts are plotted
        self.assertGreater(len(charts.chart_thrust_power.series()), 0)
        self.assertGreater(len(charts.chart_electrical.series()), 0)
        self.assertGreater(len(charts.chart_efficiency.series()), 0)

    def test_analysis_posts_status_messages(self) -> None:
        from setuav_studio.plugins.core import CorePlugin
        from setuav_studio.plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
        from setuav_studio.shell import MainWindow

        api = StudioAPI()
        win = MainWindow(api)
        pm = PluginManager(api)
        pm.activate(CorePlugin())
        pm.activate(ElectricalPropulsionPlugin())
        pm.discover()
        win.restore_window_layout()

        doc = open_project(TEST_PROJECT_PATH)
        win.open_project(doc.location)
        api.switch_workspace("studio.workspace.propulsion")

        controls = self._dock_content(win._panels["propulsion.controls_dock"][1])
        controls.run_button.click()
        self._drain_events()
        self.assertIn("Analysis complete", win._status_label.text())

        for comp in api.current_project.data["components"]:
            if comp["id"] == "motor-cruise":
                comp["parameters"]["max_current"] = 0.001
        controls.run_button.click()
        self._drain_events()
        self.assertIn("Current limit exceeded", win._status_label.text())

    def test_propulsion_worker_and_solver_modes(self) -> None:
        from PySide6.QtCore import QThreadPool
        from pythrust.propulsion.models.motor import MotorSpec
        from pythrust.propulsion.models.propeller import PropellerSpec

        from setuav_studio.plugins.electrical_propulsion.engine import PropulsionSolverEngine
        from setuav_studio.plugins.electrical_propulsion.worker import PropulsionWorker

        motor_spec = MotorSpec(
            kv_rpm_per_v=900.0, resistance_ohm=0.035, no_load_current_a=1.2, current_max_a=45.0
        )
        prop_spec = PropellerSpec(diameter_m=0.3302, pitch_m=0.1651, blade_count=2)
        prop_entry = PropulsionSolverEngine.fallback_propeller(13.0, 6.5, 2)

        context = {
            "mode": "airspeed_sweep",
            "params": {"throttle": 100.0, "v_min": 0.0, "v_max": 20.0, "v_step": 5.0},
            "motor_spec": motor_spec,
            "motor_params": {"max_power": 1000.0},
            "prop_spec": prop_spec,
            "prop_entry": prop_entry,
            "total_voltage": 22.2,
            "capacity_mah": 5000.0,
            "rho": 1.225,
            "diameter_in": 13.0,
            "pitch_in": 6.5,
        }

        # Test solver engine directly
        res_sweep = PropulsionSolverEngine.run_airspeed_sweep(context)
        self.assertEqual(res_sweep["mode"], "airspeed_sweep")
        self.assertGreater(len(res_sweep["x_values"]), 3)

        context["mode"] = "throttle_sweep"
        context["params"] = {"airspeed": 15.0, "t_min": 20.0, "t_max": 100.0, "t_step": 20.0}
        res_throttle = PropulsionSolverEngine.run_throttle_sweep(context)
        self.assertEqual(res_throttle["mode"], "throttle_sweep")
        self.assertGreater(len(res_throttle["x_values"]), 3)

        context["mode"] = "operating_point"
        context["params"] = {"airspeed": 18.0, "throttle": 80.0}
        res_point = PropulsionSolverEngine.run_operating_point(context)
        self.assertEqual(res_point["mode"], "operating_point")
        self.assertEqual(len(res_point["x_values"]), 1)

        # Test PropulsionWorker execution in QThreadPool
        received_results = []
        progress_steps = []

        worker = PropulsionWorker(context)
        worker.signals.finished.connect(received_results.append)
        worker.signals.progress.connect(lambda c, t, m: progress_steps.append((c, t, m)))

        QThreadPool.globalInstance().start(worker)
        QThreadPool.globalInstance().waitForDone()
        self.app.processEvents()

        self.assertEqual(len(received_results), 1)
        self.assertIn("static_thrust", received_results[0])
        self.assertGreater(len(progress_steps), 0)

    def test_pythrust_data_dir_resolution(self) -> None:
        """5.17: hardcoded path is gone; resolution prefers env var, then QSettings, then relatives."""
        import os
        import tempfile
        from pathlib import Path

        from PySide6.QtCore import QSettings

        from setuav_studio.plugins.core.settings import StudioSettings
        from setuav_studio.plugins.electrical_propulsion import database as db_module

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

    def test_propulsion_solver_engine_calculation(self) -> None:
        from pythrust.propulsion.models.motor import MotorSpec
        from pythrust.propulsion.models.propeller import PropellerSpec

        from setuav_studio.plugins.electrical_propulsion.engine import (
            PropulsionPoint,
            PropulsionSolverEngine,
        )

        motor_spec = MotorSpec(
            kv_rpm_per_v=900.0, resistance_ohm=0.035, no_load_current_a=1.2, current_max_a=45.0
        )
        prop_spec = PropellerSpec(diameter_m=0.3302, pitch_m=0.1651, blade_count=2)
        prop_entry = PropulsionSolverEngine.fallback_propeller(13.0, 6.5, 2)

        pt = PropulsionSolverEngine.solve_point(
            motor_spec=motor_spec,
            prop_spec=prop_spec,
            prop_entry=prop_entry,
            total_voltage=22.2,
            rho=1.225,
            v_mps=15.0,
            throttle_val=1.0,
            x_val=15.0,
        )

        self.assertIsInstance(pt, PropulsionPoint)
        self.assertGreater(pt.rpm, 1000.0)
        self.assertGreater(pt.thrust, 0.0)
        self.assertGreater(pt.power, 0.0)
        self.assertGreater(pt.current, 0.0)
        self.assertTrue(0.0 <= pt.eta_sys <= 1.0)

    def _drain_events(self, iterations: int = 15) -> None:
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().waitForDone()
        for _ in range(iterations):
            self.app.processEvents()

    @staticmethod
    def _dock_content(dock) -> object:
        widget = dock.widget()
        if widget.objectName() == "studioDockPanel":
            return widget.layout().itemAt(0).widget()
        return widget


if __name__ == "__main__":
    unittest.main()
