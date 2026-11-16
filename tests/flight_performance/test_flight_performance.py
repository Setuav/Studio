"""Tests for the flight performance solver and its level-flight computation."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import PropertyMock, patch

import numpy as np
from pythrust.battery import BatteryState
from pythrust.propulsion.models import MotorSpec, PropellerSpec, SystemSpec

from plugins.aerodynamics.engine.base import AeroAnalysisError
from plugins.electrical_propulsion.cells import cell_spec
from plugins.electrical_propulsion.database import get_propeller_database
from plugins.electrical_propulsion.powertrain import Powertrain
from plugins.flight_performance.engine.performance import (
    AerodynamicModel,
    DragPolar,
    aerobuildup_cl_max,
    feasible_throttle_range,
    fit_drag_polar,
    level_flight_envelope,
    max_level_speed,
    stall_speed,
    throttle_for_thrust,
    velocity_sweep,
)
from plugins.flight_performance.plugin import FlightPerformancePlugin
from plugins.flight_performance.solver import (
    SOLVER_ID_FLIGHT_PERFORMANCE,
    FlightPerformanceSolver,
)
from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument, open_project
from setuav_studio.solver import SolverConfig
from tests._common import TEST_PROJECT_PATH

PROPULSION_TYPES = {
    "org.setuav.core:propulsion-system",
    "org.setuav.core:battery",
    "org.setuav.core:esc",
    "org.setuav.core:motor",
    "org.setuav.core:propeller",
}


def _powertrain(unit_count: int = 1) -> Powertrain:
    """6S1P pack of the default LiPo cell driving 13x6.5 propeller units."""
    propeller_data = get_propeller_database().get("APC_13x6.5E")
    assert propeller_data is not None
    return Powertrain(
        motor=MotorSpec(
            kv_rpm_per_v=900.0, resistance_ohm=0.035, no_load_current_a=1.2, current_max_a=45.0
        ),
        propeller=PropellerSpec(diameter_m=0.3302, pitch_m=0.1651, blade_count=2),
        propeller_data=propeller_data,
        battery=cell_spec("lipo_6000").rate_map(series=6, parallel=1),
        battery_state=BatteryState(soc=1.0),
        unit_system=SystemSpec(resistance_ohm=0.005),
        unit_count=unit_count,
    )


def _throttle_for_thrust(powertrain: Powertrain, airspeed_mps: float, thrust_n: float):
    return throttle_for_thrust(
        powertrain,
        rho=1.225,
        airspeed_mps=airspeed_mps,
        thrust_n=thrust_n,
        throttle_range=feasible_throttle_range(powertrain, rho=1.225, airspeed_mps=airspeed_mps),
    )


def _aero() -> AerodynamicModel:
    cl = np.linspace(-0.2, 1.25, 12)
    return AerodynamicModel(
        area_m2=0.6,
        cl_max=1.25,
        polar_cl=cl,
        polar_cd=0.03 + 0.045 * cl**2,
        drag_polar=DragPolar(cd0=0.03, k_induced=0.045),
    )


def _config(**overrides: Any) -> SolverConfig:
    parameters = FlightPerformanceSolver.default_parameters()
    parameters.update({"v_step": 1.0, "alpha_step": 1.0, **overrides})
    return SolverConfig(
        solver_id=SOLVER_ID_FLIGHT_PERFORMANCE, name="Flight Performance", parameters=parameters
    )


def _project_without_propulsion() -> ProjectDocument:
    project = open_project(TEST_PROJECT_PATH)
    project.data["components"] = [
        c for c in project.data["components"] if c.get("type") not in PROPULSION_TYPES
    ]
    return project


class LevelFlightComputationTests(unittest.TestCase):
    def test_stall_speed(self) -> None:
        self.assertAlmostEqual(stall_speed(2.0, 0.5, 1.2, 1.225), 7.305, places=3)
        with self.assertRaisesRegex(ValueError, "positive mass"):
            stall_speed(0.0, 0.5, 1.2, 1.225)

    def test_drag_polar_fit_and_rejection(self) -> None:
        cl = [0.0, 0.4, 0.8, 1.2]
        polar = fit_drag_polar(cl, [0.02 + 0.04 * c**2 for c in cl])
        assert polar is not None
        self.assertAlmostEqual(polar.cd0, 0.02, places=6)
        self.assertAlmostEqual(polar.k_induced, 0.04, places=6)
        self.assertAlmostEqual(polar.max_lift_to_drag, 1.0 / (2.0 * np.sqrt(0.02 * 0.04)))
        self.assertIsNone(fit_drag_polar([0.0, 0.4, 0.8], [0.02, -0.01, 0.03]))

    def test_cl_max_requires_a_post_peak_drop(self) -> None:
        points = [
            SimpleNamespace(alpha=-2.0, cl=0.30, converged=True),
            SimpleNamespace(alpha=8.0, cl=1.20, converged=True),
            SimpleNamespace(alpha=16.0, cl=1.50, converged=True),
            SimpleNamespace(alpha=22.0, cl=1.42, converged=True),
        ]
        self.assertEqual(aerobuildup_cl_max(points), (1.5, 16.0, True))
        self.assertFalse(aerobuildup_cl_max(points[:3])[2])

    def test_max_level_speed_interpolates_thrust_crossing(self) -> None:
        speed, bounded = max_level_speed(
            np.array([10.0, 15.0, 20.0]),
            np.array([10.0, 8.0, 4.0]),
            np.array([5.0, 7.0, 6.0]),
            np.array([True, True, False]),
        )
        self.assertTrue(bounded)
        self.assertAlmostEqual(speed, 16.667, places=3)

    def test_throttle_stays_within_motor_current(self) -> None:
        powertrain = _powertrain()
        throttle_range = feasible_throttle_range(powertrain, rho=1.225, airspeed_mps=10.0)
        assert throttle_range is not None
        low, high = throttle_range
        self.assertLess(high, 1.0)
        top = powertrain.solve(rho=1.225, airspeed_mps=10.0, throttle=high)
        self.assertTrue(top.feasible)
        self.assertLessEqual(top.battery_current_a, powertrain.motor.current_max_a + 1e-6)
        self.assertFalse(
            powertrain.solve(rho=1.225, airspeed_mps=10.0, throttle=min(1.0, high + 0.01)).feasible
        )

        throttle, point = _throttle_for_thrust(powertrain, 10.0, 2.0)
        assert point is not None
        self.assertTrue(low <= throttle <= high)
        self.assertAlmostEqual(point.thrust_n, 2.0, places=4)
        self.assertIsNone(_throttle_for_thrust(powertrain, 10.0, 500.0)[1])

    def test_thrust_below_the_modelled_range_is_not_a_flight_point(self) -> None:
        powertrain = _powertrain()
        throttle_range = feasible_throttle_range(powertrain, rho=1.225, airspeed_mps=10.0)
        assert throttle_range is not None
        lowest = powertrain.solve(rho=1.225, airspeed_mps=10.0, throttle=throttle_range[0])
        _, point = _throttle_for_thrust(powertrain, 10.0, 0.5 * lowest.thrust_n)
        self.assertIsNone(point)

    def test_twin_motor_needs_less_throttle_for_the_same_thrust(self) -> None:
        single, _ = _throttle_for_thrust(_powertrain(), 12.0, 6.0)
        twin, point = _throttle_for_thrust(_powertrain(unit_count=2), 12.0, 6.0)
        self.assertIsNotNone(point)
        self.assertLess(twin, single)

    def test_velocity_sweep_starts_at_the_stall_margin(self) -> None:
        sweep = velocity_sweep(v_min=5.0, v_max=12.0, v_step=1.0, minimum_speed=8.5)
        self.assertEqual(sweep[0], 8.5)
        self.assertEqual(sweep[-1], 11.5)
        with self.assertRaisesRegex(ValueError, "Velocity sweep is empty"):
            velocity_sweep(v_min=5.0, v_max=12.0, v_step=1.0, minimum_speed=13.0)

    def test_envelope_with_powertrain(self) -> None:
        velocities = np.arange(9.0, 30.0, 1.0)
        powertrain = _powertrain()
        envelope = level_flight_envelope(
            mass_kg=2.5,
            rho=1.225,
            aero=_aero(),
            velocities=velocities,
            powertrain=powertrain,
            reserve_soc=0.2,
        )
        propulsion = envelope.propulsion
        assert propulsion is not None
        self.assertTrue(np.all(propulsion.feasible))
        self.assertTrue(np.all(envelope.rate_of_climb > 0.0))
        best = int(np.argmin(propulsion.electrical_power))
        self.assertEqual(int(np.argmax(envelope.endurance_min)), best)
        # The open-circuit energy between full charge and the 20 % reserve, less the
        # losses of the voltage sag.
        dods = np.linspace(0.0, 0.8, 801)
        ocv = np.array([powertrain.battery.ocv(float(dod)) for dod in dods])
        reversible_wh = float(np.trapezoid(ocv, dods)) * 6.0 * 6
        ideal_min = reversible_wh / propulsion.electrical_power[best] * 60.0
        self.assertLess(envelope.endurance_min[best], ideal_min)
        self.assertGreater(envelope.endurance_min[best], 0.9 * ideal_min)
        self.assertAlmostEqual(
            envelope.best_lift_to_drag_speed,
            float(np.sqrt(2.0 * 2.5 * 9.80665 / (1.225 * 0.6 * np.sqrt(0.03 / 0.045)))),
        )

    def test_envelope_without_powertrain_is_aerodynamic_only(self) -> None:
        envelope = level_flight_envelope(
            mass_kg=2.0,
            rho=1.225,
            aero=_aero(),
            velocities=np.arange(9.0, 20.0, 1.0),
            powertrain=None,
            reserve_soc=0.2,
        )
        self.assertIsNone(envelope.propulsion)
        self.assertEqual(len(envelope.range_km), 0)
        self.assertGreater(envelope.min_power_speed, envelope.stall_speed)


class FlightPerformanceSolverTests(unittest.TestCase):
    def test_fixture_aircraft_envelope(self) -> None:
        result = FlightPerformanceSolver(_config(), open_project(TEST_PROJECT_PATH)).run()

        summary = {key: item.value for key, item in result.summary.items()}
        self.assertTrue(summary["feasible"])
        self.assertTrue(summary["max_speed_bounded"])
        self.assertAlmostEqual(float(summary["battery_voltage"]), 12.6)
        self.assertGreater(float(summary["max_speed"]), float(summary["best_range_speed"]))
        self.assertGreater(float(summary["best_range_speed"]), float(summary["stall_speed"]))
        self.assertGreater(float(summary["max_range"]), 0.0)
        self.assertGreater(float(summary["max_endurance"]), 0.0)

        table = result.tables["level_flight"]
        self.assertAlmostEqual(
            table.data["velocity"][0], 1.15 * float(summary["stall_speed"]), places=1
        )
        self.assertIn("range", table.data)
        self.assertEqual(
            set(result.plots),
            {"power_curves", "thrust_curves", "climb", "endurance", "range", "battery_load"},
        )

    def test_aircraft_without_propulsion_gets_an_aerodynamic_result(self) -> None:
        result = FlightPerformanceSolver(_config(), _project_without_propulsion()).run()

        self.assertIn("stall_speed", result.summary)
        self.assertNotIn("max_range", result.summary)
        self.assertNotIn("range", result.tables["level_flight"].data)
        self.assertEqual(set(result.plots), {"power_curves", "thrust_curves"})

    def test_polar_must_reach_stall(self) -> None:
        solver = FlightPerformanceSolver(_config(alpha_max=4.0), _project_without_propulsion())
        with self.assertRaisesRegex(AeroAnalysisError, "does not reach stall"):
            solver.run()

    def test_aircraft_mass_is_required(self) -> None:
        project = _project_without_propulsion()
        with (
            patch.object(
                ProjectDocument,
                "mass_properties",
                new_callable=PropertyMock,
                return_value=SimpleNamespace(mass_kg=0.0),
            ),
            self.assertRaisesRegex(ValueError, "needs the aircraft mass"),
        ):
            FlightPerformanceSolver(_config(), project).run()


class FlightPerformancePluginTests(unittest.TestCase):
    def test_plugin_registers_solver_and_adds_default_configuration(self) -> None:
        api = StudioAPI()
        plugin = FlightPerformancePlugin()
        plugin.activate(api)
        self.assertIs(
            api.solvers.get_solver_class(SOLVER_ID_FLIGHT_PERFORMANCE), FlightPerformanceSolver
        )

        project = open_project(TEST_PROJECT_PATH)
        api._host.set_project(project)
        plugin._add_analysis()
        configs = [
            c
            for c in project.solver_configs.values()
            if c.solver_id == SOLVER_ID_FLIGHT_PERFORMANCE
        ]
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].parameters, FlightPerformanceSolver.default_parameters())

        plugin.deactivate(api)
        self.assertIsNone(api.solvers.get_solver_class(SOLVER_ID_FLIGHT_PERFORMANCE))


if __name__ == "__main__":
    unittest.main()
