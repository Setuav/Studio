"""Unit tests for the Flight Performance Envelope plugin and solver."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QThreadPool
from pythrust.propulsion.models import BatterySpec, MotorSpec, PropellerSpec, SystemSpec

from plugins.electrical_propulsion.database import get_propeller_database
from plugins.electrical_propulsion.plugin import ElectricalPropulsionPlugin
from plugins.electrical_propulsion.powertrain import Powertrain
from plugins.flight_performance.analysis_store import (
    get_stored_performance_result,
    store_performance_result,
)
from plugins.flight_performance.engine.models import (
    CruisePerformance,
    FlightCurves,
    FlightEnvelopeResult,
    OptimalSpeeds,
    PerformanceMetrics,
)
from plugins.flight_performance.engine.solver import FlightPerformanceSolver
from plugins.flight_performance.plugin import FlightPerformancePlugin
from setuav_studio.api import StudioAPI, StudioEvents
from setuav_studio.plugin import PluginManager
from setuav_studio.project import open_project
from tests._common import TEST_PROJECT_PATH, get_qapp


def _powertrain(voltage_v: float, capacity_mah: float, unit_count: int = 1) -> Powertrain:
    propeller_data = get_propeller_database().get("APC_13x6.5E")
    assert propeller_data is not None
    return Powertrain(
        motor=MotorSpec(
            kv_rpm_per_v=900.0, resistance_ohm=0.035, no_load_current_a=1.2, current_max_a=45.0
        ),
        propeller=PropellerSpec(diameter_m=0.3302, pitch_m=0.1651, blade_count=2),
        propeller_data=propeller_data,
        battery=BatterySpec(voltage_v=voltage_v, discharge_efficiency=0.98),
        unit_system=SystemSpec(resistance_ohm=0.005),
        capacity_mah=capacity_mah,
        unit_count=unit_count,
    )


class TestFlightPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def tearDown(self) -> None:
        self._drain_events()

    def _drain_events(self, iterations: int = 15) -> None:
        QThreadPool.globalInstance().waitForDone()
        for _ in range(iterations):
            self.app.processEvents()

    def _temporary_project_copy(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_path = Path(temp_dir.name) / "fixed-wing"
        shutil.copytree(TEST_PROJECT_PATH, project_path)
        return project_path

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

        # Post-stall points must not bias the pre-stall fit.
        cd0_pre, k_pre = FlightPerformanceSolver.fit_parabolic_cd(
            [0.0, 0.4, 0.8, 1.2, 1.3],
            [0.02, 0.0264, 0.0456, 0.0776, 0.40],
            alpha_values=[0.0, 4.0, 8.0, 12.0, 18.0],
            alpha_max=12.0,
        )
        self.assertAlmostEqual(cd0_pre or 0.0, 0.02, places=3)
        self.assertAlmostEqual(k_pre or 0.0, 0.04, places=3)

        # Non-physical samples are rejected rather than corrected silently.
        self.assertEqual(
            FlightPerformanceSolver.fit_parabolic_cd([0.0, 0.4, 0.8], [0.02, -0.01, 0.03]),
            (None, None),
        )

    def test_aerobuildup_clmax_requires_post_peak_drop(self) -> None:
        points = [
            SimpleNamespace(alpha=-2.0, cl=0.30, converged=True),
            SimpleNamespace(alpha=8.0, cl=1.20, converged=True),
            SimpleNamespace(alpha=16.0, cl=1.50, converged=True),
            SimpleNamespace(alpha=22.0, cl=1.42, converged=True),
        ]
        cl_max, alpha_max, confirmed = FlightPerformanceSolver._resolve_aerobuildup_clmax(points)
        self.assertAlmostEqual(cl_max, 1.50)
        self.assertAlmostEqual(alpha_max, 16.0)
        self.assertTrue(confirmed)

        unconfirmed = points[:3]
        _, _, confirmed = FlightPerformanceSolver._resolve_aerobuildup_clmax(unconfirmed)
        self.assertFalse(confirmed)

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
            "powertrain": _powertrain(22.2, 5000.0),
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
        powertrain = _powertrain(22.2, 5000.0)
        throttle, _power, current, feasible = FlightPerformanceSolver.solve_propulsion_for_thrust(
            powertrain=powertrain, rho=1.225, v_mps=10.0, thrust_req=2.0
        )

        self.assertTrue(feasible)
        self.assertLess(throttle, 100.0)
        self.assertLessEqual(current, powertrain.current_limit_a)

    def test_twin_motor_needs_less_throttle_for_the_same_thrust(self) -> None:
        single = _powertrain(22.2, 5000.0)
        twin = _powertrain(22.2, 5000.0, unit_count=2)
        thr_single, _, cur_single, _ = FlightPerformanceSolver.solve_propulsion_for_thrust(
            powertrain=single, rho=1.225, v_mps=12.0, thrust_req=6.0
        )
        thr_twin, _, cur_twin, feasible = FlightPerformanceSolver.solve_propulsion_for_thrust(
            powertrain=twin, rho=1.225, v_mps=12.0, thrust_req=6.0
        )

        self.assertTrue(feasible)
        self.assertLess(thr_twin, thr_single)
        self.assertLess(cur_twin, 2.0 * cur_single)

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

    def test_solver_requires_mass_instead_of_using_default(self) -> None:
        with self.assertRaisesRegex(ValueError, "Mass properties are unavailable"):
            FlightPerformanceSolver.run_analysis(
                {
                    "area_m2": 0.5,
                    "air_density": 1.225,
                    "cl_max": 1.2,
                    "cd_min": 0.035,
                    "v_min": 8.0,
                    "v_max": 20.0,
                    "v_step": 1.0,
                }
            )

    def test_controls_dock_runs_analysis_as_background_task(self) -> None:
        from plugins.flight_performance.controls_dock import PerformanceControlsDock

        context = {
            "mass_kg": 2.0,
            "area_m2": 0.5,
            "air_density": 1.225,
            "cl_max": 1.2,
            "cd_min": 0.035,
            "v_min": 8.0,
            "v_max": 25.0,
            "v_step": 1.0,
            "powertrain": _powertrain(14.8, 4000.0),
        }

        api = StudioAPI()
        progress: list[tuple[int, int, str]] = []
        statuses: list[tuple[str, str]] = []
        published: list[FlightEnvelopeResult] = []
        api._host.bind_progress_handler(
            lambda current, total, label: progress.append((current, total, label))
        )
        api._host.bind_status_handler(
            lambda message, level, _timeout: statuses.append((message, level))
        )
        api.subscribe(StudioEvents.FLIGHT_PERFORMANCE_ANALYSIS_COMPLETED, published.append)

        dock = PerformanceControlsDock(api)
        self.addCleanup(dock.deleteLater)
        with patch.object(dock, "_build_analysis_context", return_value=context):
            dock.btn_run.click()
            self.assertFalse(dock.btn_run.isEnabled())
            self.assertTrue(dock.btn_cancel.isEnabled())
            self._drain_events()

        self.assertEqual(len(published), 1)
        self.assertTrue(published[0].feasible)
        self.assertTrue(dock.btn_run.isEnabled())
        self.assertFalse(dock.btn_cancel.isEnabled())
        # Initial report from the dock, task progress from the solver, then clear on finish.
        self.assertEqual(progress[0], (0, 100, "Performance"))
        self.assertGreater(len(progress[1:-1]), 0)
        self.assertEqual(progress[-1], (1, 1, ""))
        self.assertEqual(statuses[-1][1], "success")
        self.assertIn("Coupled Performance complete", statuses[-1][0])

    def test_controls_dock_refreshes_empty_mass_on_content_change(self) -> None:
        from plugins.flight_performance.controls_dock import PerformanceControlsDock

        api = StudioAPI()
        doc = open_project(TEST_PROJECT_PATH)
        api._host.set_project(doc)
        dock = PerformanceControlsDock(api)
        self.addCleanup(dock.deleteLater)

        initial_g = doc.mass_properties.mass_kg * 1000.0
        self.assertGreater(initial_g, 0.0)
        self.assertEqual(dock._property_value(dock.mass_table, "empty_mass"), f"{initial_g:.1f} g")

        esc = next(c for c in doc.data["components"] if c["id"] == "esc-cruise")
        api.edit_component(
            esc, "Change ESC mass", lambda: esc.update({"mass": esc["mass"] + 100.0})
        )

        updated_g = doc.mass_properties.mass_kg * 1000.0
        self.assertAlmostEqual(updated_g, initial_g + 100.0, places=3)
        self.assertEqual(dock._property_value(dock.mass_table, "empty_mass"), f"{updated_g:.1f} g")
        self.assertEqual(
            dock._property_value(dock.mass_table, "tow"),
            f"{updated_g + dock.spin_payload.value():.1f} g",
        )

    def test_flight_performance_plugin_and_ui(self) -> None:
        from setuav_studio.ui.shell import MainWindow

        api = StudioAPI()
        win = MainWindow(api)
        self.addCleanup(win.deleteLater)
        pm = PluginManager(api)
        pm.activate(ElectricalPropulsionPlugin())
        pm.activate(FlightPerformancePlugin())
        win.layout_manager.restore_window_layout()

        doc = open_project(self._temporary_project_copy())
        win.project_controller.open_project(doc.location)
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
        self.assertIn("Performance complete", win.status_manager.status_label.text())

        # Check project extension storage
        assert api.project is not None
        stored = get_stored_performance_result(api.project)
        self.assertIsNotNone(stored)
        self.assertTrue(stored.feasible)  # type: ignore

    def test_results_dock_csv_export(self) -> None:
        from unittest.mock import patch

        api = StudioAPI()
        from plugins.flight_performance.results_dock import PerformanceResultsDock

        dock = PerformanceResultsDock(api)
        self.addCleanup(dock.deleteLater)
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
            with patch(
                "PySide6.QtWidgets.QFileDialog.getSaveFileName",
                return_value=(temp_path, "CSV Files (*.csv)"),
            ):
                dock._export_csv()
            self.assertTrue(os.path.exists(temp_path))
            with open(temp_path, encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Setuav Studio Flight Performance Envelope Export", content)
                self.assertIn("Velocity_mps", content)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_project_tree_nodes(self) -> None:
        api = StudioAPI()
        api._host.bind_panel_handlers(lambda _panel: None)
        plugin = FlightPerformancePlugin()
        plugin.activate(api)

        doc = open_project(TEST_PROJECT_PATH)
        res = FlightEnvelopeResult(
            mass_kg=2.0,
            area_m2=0.5,
            air_density=1.225,
            cl_max=1.2,
            metrics=PerformanceMetrics(
                stall_speed=9.0, max_speed=28.0, max_range_km=35.0, max_rate_of_climb=3.5
            ),
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

    def test_plugin_deactivate_removes_selection_listener(self) -> None:
        api = StudioAPI()
        actions: list[object] = []
        removed_actions: list[tuple[str, str]] = []
        panels: list[object] = []
        removed_panels: list[str] = []
        api._host.bind_action_handlers(
            actions.append,
            lambda menu, title: removed_actions.append((menu, title)),
        )
        api._host.bind_panel_handlers(panels.append, removed_panels.append)

        plugin = FlightPerformancePlugin()
        plugin.activate(api)

        self.assertEqual(len(actions), 0)
        self.assertIn(plugin._on_selection_changed, api._selection_listeners)

        plugin.deactivate(api)

        self.assertNotIn(plugin._on_selection_changed, api._selection_listeners)
        self.assertEqual(removed_actions, [])
        self.assertEqual(
            removed_panels,
            [
                "flight_performance.controls_dock",
                "flight_performance.charts_dock",
                "flight_performance.results_dock",
            ],
        )

        plugin.activate(api)
        self.assertEqual(len(actions), 0)
        self.assertEqual(len(panels), 6)
        self.assertEqual(
            sum(listener == plugin._on_selection_changed for listener in api._selection_listeners),
            1,
        )

    def test_flight_performance_results_dock_unit_conversion(self) -> None:
        from plugins.flight_performance.results_dock import PerformanceResultsDock
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        um.set_display_unit("velocity", "m/s")
        um.set_display_unit("force", "N")
        um.set_display_unit("power", "W")
        um.units_changed.emit()

        api = StudioAPI()
        dock = PerformanceResultsDock(api)

        curves = FlightCurves(
            velocities=[15.0],
            power_required=[50.0],
            power_available=[120.0],
            thrust_required=[5.0],
            thrust_available=[12.0],
            rate_of_climb=[3.5],
            climb_angle_deg=[15.0],
            range_km=[30.0],
            endurance_hours=[0.8],
            electrical_power=[75.0],
            current_draw=[5.0],
            throttle_pct=[45.0],
            feasible=[True],
        )
        res = FlightEnvelopeResult(
            optimal_speeds=OptimalSpeeds(
                best_endurance=12.0, best_range=15.0, best_climb=14.0, best_ld=16.0
            ),
            metrics=PerformanceMetrics(
                stall_speed=9.5,
                max_speed=30.0,
                max_ld_ratio=13.5,
                glide_ratio=13.5,
                best_climb_angle_deg=12.0,
                min_power_required=45.0,
                max_range_km=42.0,
                max_endurance_hours=1.2,
                max_rate_of_climb=4.5,
            ),
            cruise=CruisePerformance(
                speed=15.0,
                power=60.0,
                current=4.0,
                throttle=55.0,
                endurance=1.1,
                range=38.0,
                feasible=True,
            ),
            curves=curves,
            propulsion_available=True,
            feasible=True,
        )

        dock.set_results(res)

        # Check headers in SI
        self.assertEqual(dock.detail_table.horizontalHeaderItem(0).text(), "Airspeed (m/s)")
        self.assertEqual(dock.detail_table.horizontalHeaderItem(1).text(), "P_req (W)")
        self.assertEqual(dock.detail_table.horizontalHeaderItem(3).text(), "T_req (N)")

        # Switch to Imperial
        um.set_display_unit("velocity", "ft/s")
        um.set_display_unit("force", "lbf")
        um.units_changed.emit()

        self.assertEqual(dock.detail_table.horizontalHeaderItem(0).text(), "Airspeed (ft/s)")
        self.assertEqual(dock.detail_table.horizontalHeaderItem(3).text(), "T_req (lbf)")
        expected_v = f"{um.to_display(15.0, 'velocity'):.1f}"
        expected_t = f"{um.to_display(5.0, 'force'):.2f}"
        self.assertEqual(dock.detail_table.item(0, 0).text(), expected_v)
        self.assertEqual(dock.detail_table.item(0, 3).text(), expected_t)

        # Restore units
        um.set_display_unit("velocity", "m/s")
        um.set_display_unit("force", "N")
        um.units_changed.emit()
        dock.close()


if __name__ == "__main__":
    unittest.main()
