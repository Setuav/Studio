"""Unit tests for the Flight Performance Envelope plugin and solver."""
from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np
from PySide6.QtCore import QThreadPool

from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec
from setuav_studio.plugin_system import PluginManager, StudioAPI
from setuav_studio.plugins.core import CorePlugin
from setuav_studio.plugins.electrical_propulsion.engine.solver import PropulsionSolverEngine
from setuav_studio.plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
from setuav_studio.plugins.flight_performance.analysis_store import (
    get_stored_performance_result,
    store_performance_result,
)
from setuav_studio.plugins.flight_performance.engine.models import (
    CruisePerformance,
    FlightCurves,
    FlightEnvelopeResult,
    OptimalSpeeds,
    PerformanceMetrics,
)
from setuav_studio.plugins.flight_performance.engine.solver import FlightPerformanceSolver
from setuav_studio.plugins.flight_performance.plugin import FlightPerformancePlugin
from setuav_studio.plugins.flight_performance.worker import FlightPerformanceWorker
from setuav_studio.project import open_project
from tests._common import TEST_PROJECT_PATH, get_qapp


class TestFlightPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def _drain_events(self, iterations: int = 15) -> None:
        QThreadPool.globalInstance().waitForDone()
        for _ in range(iterations):
            self.app.processEvents()

    @staticmethod
    def _dock_content(dock: object) -> object:
        widget = dock.widget()  # type: ignore
        if widget.objectName() == "studioDockPanel":
            return widget.layout().itemAt(0).widget()
        return widget

    def test_models_serialization(self) -> None:
        opt = OptimalSpeeds(best_endurance=12.0, best_range=15.0, best_climb=14.0, best_ld=16.0)
        met = PerformanceMetrics(
            stall_speed=9.5,
            max_speed=30.0,
            max_ld_ratio=13.5,
            glide_ratio=13.5,
            best_climb_angle_deg=12.0,
            min_power_required=45.0,
            max_range_km=42.0,
            max_endurance_hours=1.2,
            max_rate_of_climb=4.5,
        )
        cru = CruisePerformance(
            speed=15.0,
            power=60.0,
            current=4.0,
            throttle=55.0,
            endurance=1.1,
            range=38.0,
            feasible=True,
        )
        curves = FlightCurves(
            velocities=[10.0, 15.0, 20.0],
            power_required=[50.0, 60.0, 80.0],
            power_available=[120.0, 110.0, 95.0],
            thrust_required=[5.0, 4.0, 4.0],
            thrust_available=[12.0, 7.3, 4.75],
            rate_of_climb=[3.5, 2.5, 0.75],
            climb_angle_deg=[15.0, 9.5, 2.1],
            range_km=[30.0, 38.0, 25.0],
            endurance_hours=[0.8, 1.1, 0.6],
            electrical_power=[75.0, 60.0, 110.0],
            current_draw=[5.0, 4.0, 7.3],
            throttle_pct=[45.0, 55.0, 85.0],
            feasible=[True, True, True],
        )
        res = FlightEnvelopeResult(
            mass_kg=2.0,
            area_m2=0.5,
            air_density=1.225,
            cl_max=1.3,
            optimal_speeds=opt,
            metrics=met,
            cruise=cru,
            curves=curves,
            feasible=True,
        )

        d = res.to_dict()
        res_restored = FlightEnvelopeResult.from_dict(d)

        self.assertEqual(res_restored.mass_kg, 2.0)
        self.assertEqual(res_restored.metrics.stall_speed, 9.5)
        self.assertEqual(res_restored.optimal_speeds.best_range, 15.0)
        self.assertEqual(res_restored.cruise.power, 60.0)
        self.assertEqual(len(res_restored.curves.velocities), 3)

    def test_solver_stall_and_drag_fitting(self) -> None:
        # V_stall = sqrt(2 * (2.0 * 9.81) / (1.225 * 0.5 * 1.2)) = sqrt(39.24 / 0.735) ~= 7.307 m/s
        v_stall = FlightPerformanceSolver.compute_stall_speed(
            mass_kg=2.0,
            area_m2=0.5,
            cl_max=1.2,
            rho=1.225,
        )
        self.assertAlmostEqual(v_stall, 7.307, places=2)

        # Parabolic drag polar fit
        cl_pts = [0.0, 0.4, 0.8, 1.2]
        cd_pts = [0.02, 0.02 + 0.04 * (0.4**2), 0.02 + 0.04 * (0.8**2), 0.02 + 0.04 * (1.2**2)]
        cd0, k_ind = FlightPerformanceSolver.fit_parabolic_cd(cl_pts, cd_pts)
        self.assertIsNotNone(cd0)
        self.assertIsNotNone(k_ind)
        self.assertAlmostEqual(cd0, 0.02, places=3)
        self.assertAlmostEqual(k_ind, 0.04, places=3)

    def test_resolve_max_speed_interpolates_thrust_crossing(self) -> None:
        speed, bounded = FlightPerformanceSolver.resolve_max_speed(
            velocities=np.array([10.0, 15.0, 20.0]),
            thrust_available=np.array([10.0, 8.0, 4.0]),
            thrust_required=np.array([5.0, 7.0, 6.0]),
            feasible_points=np.array([True, True, False]),
        )
        self.assertTrue(bounded)
        self.assertAlmostEqual(speed, 16.67, places=2)

    def test_solver_full_analysis(self) -> None:
        motor_spec = MotorSpec(kv_rpm_per_v=900.0, resistance_ohm=0.035, no_load_current_a=1.2, current_max_a=45.0)
        prop_spec = PropellerSpec(diameter_m=0.3302, pitch_m=0.1651, blade_count=2)
        prop_entry = PropulsionSolverEngine.fallback_propeller(13.0, 6.5, 2)

        context = {
            "mass_kg": 2.5,
            "area_m2": 0.6,
            "air_density": 1.225,
            "cl_max": 1.25,
            "cd_min": 0.030,
            "v_min": 8.0,
            "v_max": 30.0,
            "v_step": 1.0,
            "stall_margin": 1.15,
            "motor_spec": motor_spec,
            "prop_spec": prop_spec,
            "prop_entry": prop_entry,
            "battery_capacity_mah": 5000.0,
            "battery_voltage": 22.2,
            "usable_battery_ratio": 0.85,
        }

        result = FlightPerformanceSolver.run_analysis(context)
        self.assertTrue(result.feasible)
        self.assertGreater(result.metrics.stall_speed, 5.0)
        self.assertGreater(result.metrics.max_speed, result.metrics.stall_speed)
        self.assertGreater(result.optimal_speeds.best_range, 0.0)
        self.assertGreater(result.optimal_speeds.best_endurance, 0.0)
        self.assertGreater(result.optimal_speeds.best_climb, 0.0)
        self.assertGreater(result.metrics.max_range_km, 0.0)
        self.assertGreater(result.metrics.max_endurance_hours, 0.0)
        self.assertGreater(result.metrics.max_rate_of_climb, 0.0)
        self.assertGreater(len(result.curves.velocities), 5)

    def test_solver_limits_throttle_by_motor_current(self) -> None:
        """A current-limited motor may still solve a lower-throttle thrust point."""
        motor_spec = MotorSpec(
            kv_rpm_per_v=900.0,
            resistance_ohm=0.035,
            no_load_current_a=1.2,
            current_max_a=45.0,
        )
        prop_spec = PropellerSpec(diameter_m=0.3302, pitch_m=0.1651, blade_count=2)
        prop_entry = PropulsionSolverEngine.fallback_propeller(13.0, 6.5, 2)

        throttle, _power, current, feasible = FlightPerformanceSolver.solve_propulsion_for_thrust(
            motor_spec=motor_spec,
            prop_spec=prop_spec,
            prop_entry=prop_entry,
            total_voltage=22.2,
            rho=1.225,
            v_mps=10.0,
            thrust_req=2.0,
        )

        self.assertTrue(feasible)
        self.assertLess(throttle, 100.0)
        self.assertLessEqual(current, motor_spec.current_max_a)

    def test_solver_without_propulsion_does_not_fabricate_values(self) -> None:
        result = FlightPerformanceSolver.run_analysis(
            {
                "mass_kg": 2.0,
                "area_m2": 0.5,
                "air_density": 1.225,
                "cl_max": 1.2,
                "cd_min": 0.035,
                "v_min": 8.0,
                "v_max": 20.0,
                "v_step": 1.0,
            }
        )

        self.assertTrue(result.feasible)
        self.assertFalse(result.propulsion_available)
        self.assertIsNone(result.propulsion_feasible)
        self.assertEqual(result.curves.power_available, [])
        self.assertEqual(result.curves.electrical_power, [])
        self.assertEqual(result.metrics.max_range_km, 0.0)
        self.assertTrue(any("Propulsion data unavailable" in note for note in result.notes))

    def test_flight_performance_worker_and_signals(self) -> None:
        motor_spec = MotorSpec(kv_rpm_per_v=900.0, resistance_ohm=0.035, no_load_current_a=1.2, current_max_a=45.0)
        prop_spec = PropellerSpec(diameter_m=0.3302, pitch_m=0.1651, blade_count=2)
        prop_entry = PropulsionSolverEngine.fallback_propeller(13.0, 6.5, 2)

        context = {
            "mass_kg": 2.0,
            "area_m2": 0.5,
            "air_density": 1.225,
            "cl_max": 1.2,
            "cd_min": 0.035,
            "v_min": 8.0,
            "v_max": 25.0,
            "v_step": 1.0,
            "motor_spec": motor_spec,
            "prop_spec": prop_spec,
            "prop_entry": prop_entry,
            "battery_capacity_mah": 4000.0,
            "battery_voltage": 14.8,
        }

        received: list[FlightEnvelopeResult] = []
        progress_calls: list[int] = []

        worker = FlightPerformanceWorker(context)
        worker.signals.progress.connect(lambda c, t, m: progress_calls.append(c))
        worker.signals.finished.connect(lambda res: received.append(res))

        QThreadPool.globalInstance().start(worker)
        self._drain_events()

        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].feasible)
        self.assertGreater(len(progress_calls), 0)

    def test_flight_performance_plugin_and_ui(self) -> None:
        from setuav_studio.shell import MainWindow

        api = StudioAPI()
        win = MainWindow(api)
        pm = PluginManager(api)
        pm.activate(CorePlugin())
        pm.activate(ElectricalPropulsionPlugin())
        pm.activate(FlightPerformancePlugin())
        pm.discover()
        win.restore_window_layout()

        doc = open_project(TEST_PROJECT_PATH)
        win.open_project(doc.location)

        # Switch workspace
        api.switch_workspace("studio.workspace.flight_performance")
        self._drain_events()

        controls = self._dock_content(win._panels["flight_performance.controls_dock"][1])
        charts = self._dock_content(win._panels["flight_performance.charts_dock"][1])
        results = self._dock_content(win._panels["flight_performance.results_dock"][1])

        # Click run analysis
        controls.btn_run.click()  # type: ignore
        self._drain_events()

        # Check results table populated
        stall_str = results.summary_table.item(0, 1).text()  # type: ignore
        self.assertIn("m/s", stall_str)
        self.assertNotEqual(stall_str, "-")

        # Check charts plotted
        self.assertGreater(len(charts.chart_power.series()), 0)  # type: ignore
        self.assertGreater(len(charts.chart_climb.series()), 0)  # type: ignore
        self.assertGreater(len(charts.chart_mission.series()), 0)  # type: ignore
        self.assertGreater(len(charts.chart_electrical.series()), 0)  # type: ignore

        # Check status label
        self.assertIn("Performance complete", win._status_label.text())

        # Check project extension storage
        stored = get_stored_performance_result(api.current_project)
        self.assertIsNotNone(stored)
        self.assertTrue(stored.feasible)  # type: ignore

    def test_results_dock_csv_export(self) -> None:
        from unittest.mock import patch

        api = StudioAPI()
        from setuav_studio.plugins.flight_performance.results_dock import PerformanceResultsDock

        dock = PerformanceResultsDock(api)
        res = FlightEnvelopeResult(
            mass_kg=2.0,
            area_m2=0.5,
            air_density=1.225,
            cl_max=1.2,
            metrics=PerformanceMetrics(stall_speed=9.0, max_speed=28.0),
            optimal_speeds=OptimalSpeeds(best_range=15.0, best_endurance=12.0),
            curves=FlightCurves(
                velocities=[10.0, 15.0],
                power_required=[50.0, 60.0],
                power_available=[100.0, 90.0],
                thrust_required=[5.0, 4.0],
                thrust_available=[10.0, 6.0],
                rate_of_climb=[2.5, 1.5],
                climb_angle_deg=[10.0, 5.0],
                range_km=[30.0, 40.0],
                endurance_hours=[1.0, 1.2],
                electrical_power=[70.0, 65.0],
                current_draw=[4.5, 4.0],
                throttle_pct=[50.0, 60.0],
                feasible=[True, True],
            ),
        )
        dock.set_results(res)

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            temp_path = tf.name

        try:
            with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(temp_path, "CSV Files (*.csv)")):
                dock._export_csv()
            self.assertTrue(os.path.exists(temp_path))
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Setuav Studio Flight Performance Envelope Export", content)
                self.assertIn("Velocity_mps", content)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_project_tree_nodes(self) -> None:
        api = StudioAPI()
        api.set_panel_handler(lambda _panel: None)
        api.set_workspace_handler(lambda _workspace: None)
        plugin = FlightPerformancePlugin()
        plugin.activate(api)

        doc = open_project(TEST_PROJECT_PATH)
        res = FlightEnvelopeResult(
            mass_kg=2.0,
            area_m2=0.5,
            air_density=1.225,
            cl_max=1.2,
            metrics=PerformanceMetrics(stall_speed=9.0, max_speed=28.0, max_range_km=35.0, max_rate_of_climb=3.5),
            optimal_speeds=OptimalSpeeds(best_range=15.0, best_endurance=12.0),
        )
        store_performance_result(doc, res, "Test Performance Run")

        nodes = plugin._project_tree_nodes(doc)
        self.assertGreaterEqual(len(nodes), 1)
        self.assertEqual(nodes[0].title, "Performance Analyses")
        self.assertGreaterEqual(len(nodes[0].children), 1)

        run_node = nodes[0].children[0]
        self.assertEqual(run_node.title, "Test Performance Run")
        self.assertIn("V_stall: 9.0 m/s", run_node.tooltip or "")
        self.assertEqual(len(run_node.children), 0)


if __name__ == "__main__":
    unittest.main()
