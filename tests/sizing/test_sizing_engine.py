"""Unit tests for the preliminary sizing computational engine."""

from __future__ import annotations

import unittest

import numpy as np

from plugins.sizing.engine import (
    AeroParameters,
    BatteryParameters,
    MissionProfile,
    calculate_induced_drag_factor,
    calculate_oswald_raymer,
    climb_thrust_to_weight,
    converge_sizing,
    cruise_thrust_to_weight,
    hp_to_watts,
    max_wing_loading_landing,
    max_wing_loading_stall,
    recommend_motors,
    recommend_propellers,
    required_shaft_power_watts,
    service_ceiling_thrust_to_weight,
    size_battery_pack,
    solve_sizing_for_mission,
    takeoff_thrust_to_weight,
    turn_thrust_to_weight,
    tw_to_power_loading_w_kg,
    tw_to_pw,
    watts_to_hp,
)
from setuav_studio.model.atmosphere import Atmosphere


class TestSizingEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.atm = Atmosphere.isa(0.0)
        self.aero = AeroParameters.create(
            cd0=0.025,
            aspect_ratio=10.0,
            cl_max_clean=1.4,
            cl_max_takeoff=1.6,
            cl_max_landing=1.8,
        )
        self.mission = MissionProfile(
            payload_mass_kg=0.6,
            range_km=30.0,
            endurance_min=45.0,
            v_cruise_mps=18.0,
            v_stall_mps=11.0,
            v_climb_mps=14.0,
            roc_mps=3.0,
            cruise_altitude_m=500.0,
            ground_roll_takeoff_m=20.0,
            ground_roll_landing_m=25.0,
        )

    def test_aerodynamics(self) -> None:
        e = calculate_oswald_raymer(10.0)
        self.assertGreater(e, 0.70)
        self.assertLess(e, 0.95)

        k = calculate_induced_drag_factor(10.0, e)
        self.assertAlmostEqual(k, 1.0 / (np.pi * 10.0 * e), places=5)

        cd = self.aero.cd(0.5)
        self.assertAlmostEqual(cd, 0.025 + self.aero.k * (0.5**2), places=5)

        ld_max = self.aero.max_lift_to_drag_ratio
        self.assertGreater(ld_max, 10.0)
        self.assertLess(ld_max, 25.0)

    def test_stall_and_landing_limits(self) -> None:
        ws_stall = max_wing_loading_stall(v_stall_mps=11.0, atmosphere=self.atm, cl_max=1.4)
        expected = 0.5 * 1.225 * (11.0**2) * 1.4
        self.assertAlmostEqual(ws_stall, expected, places=2)

        ws_land = max_wing_loading_landing(
            landing_ground_roll_m=25.0,
            atmosphere=self.atm,
            cl_max_landing=1.8,
        )
        self.assertGreater(ws_land, 0.0)

    def test_thrust_to_weight_curves(self) -> None:
        ws_grid = np.linspace(20.0, 150.0, 10)

        # Takeoff
        tw_to = takeoff_thrust_to_weight(
            ws_pa=ws_grid,
            ground_roll_m=20.0,
            atmosphere=self.atm,
            aero=self.aero,
        )
        self.assertEqual(len(tw_to), 10)
        self.assertTrue(np.all(tw_to > 0.0))
        self.assertTrue(np.all(np.diff(tw_to) > 0.0))  # Monotonically increasing with W/S

        # Climb
        tw_clm = climb_thrust_to_weight(
            ws_pa=ws_grid,
            climb_rate_mps=3.0,
            v_climb_mps=14.0,
            atmosphere=self.atm,
            aero=self.aero,
        )
        self.assertTrue(np.all(tw_clm > 0.0))

        # Cruise
        tw_crs = cruise_thrust_to_weight(
            ws_pa=ws_grid,
            v_cruise_mps=18.0,
            atmosphere=self.atm,
            aero=self.aero,
        )
        self.assertTrue(np.all(tw_crs > 0.0))

        # Turn
        tw_trn, ws_trn_lim = turn_thrust_to_weight(
            ws_pa=ws_grid,
            load_factor_n=1.414,
            v_turn_mps=18.0,
            atmosphere=self.atm,
            aero=self.aero,
        )
        self.assertTrue(np.all(tw_trn > tw_crs))  # Turn requires more thrust than level cruise
        self.assertGreater(ws_trn_lim, 0.0)

        # Service ceiling
        tw_ceil = service_ceiling_thrust_to_weight(
            ws_pa=ws_grid,
            ceiling_altitude_m=2500.0,
            v_ceiling_mps=16.0,
            aero=self.aero,
        )
        self.assertTrue(np.all(tw_ceil > 0.0))

    def test_converters(self) -> None:
        tw = 0.35
        v = 20.0
        eta = 0.70
        pw = tw_to_pw(tw, speed_mps=v, propeller_efficiency=eta)
        self.assertAlmostEqual(pw, (0.35 * 20.0) / 0.70, places=4)

        pw_wkg = tw_to_power_loading_w_kg(tw, v, eta)
        self.assertAlmostEqual(pw_wkg, pw * 9.80665, places=3)

        p_watts = required_shaft_power_watts(pw, mtow_kg=3.5)
        self.assertAlmostEqual(p_watts, pw * (3.5 * 9.80665), places=2)

        hp = watts_to_hp(745.699872)
        self.assertAlmostEqual(hp, 1.0, places=4)
        self.assertAlmostEqual(hp_to_watts(1.0), 745.699872, places=3)

    def test_battery_sizing(self) -> None:
        bat = size_battery_pack(
            required_mission_energy_wh=100.0,
            max_power_watts=450.0,
            params=BatteryParameters(specific_energy_wh_kg=180.0, max_dod=0.80),
        )
        # Total nominal energy = 100 / 0.8 = 125 Wh
        self.assertAlmostEqual(bat.energy_wh, 125.0, places=2)
        self.assertAlmostEqual(bat.usable_energy_wh, 100.0, places=2)
        self.assertAlmostEqual(bat.mass_kg, 125.0 / 180.0, places=3)
        self.assertGreater(bat.nominal_voltage_v, 10.0)
        self.assertTrue(bat.is_c_rate_feasible)

    def test_weight_convergence(self) -> None:
        res = converge_sizing(
            mission=self.mission,
            aero=self.aero,
            design_wing_loading_pa=90.0,
            design_power_loading_wn=10.0,
        )
        self.assertTrue(res.converged)
        self.assertLess(res.iterations, 25)
        self.assertGreater(res.weights.mtow_kg, self.mission.payload_mass_kg)
        self.assertGreater(res.wing_area_m2, 0.1)
        self.assertGreater(res.wingspan_m, 1.0)
        self.assertGreater(res.max_shaft_power_w, 50.0)

        # Mass fractions sum to 1.0
        total_frac = (
            res.weights.payload_fraction
            + res.weights.battery_fraction
            + res.weights.structural_fraction
            + res.weights.propulsion_fraction
            + (res.weights.avionics_mass_kg / res.weights.mtow_kg)
        )
        self.assertAlmostEqual(total_frac, 1.0, places=3)

    def test_matching_chart_pipeline(self) -> None:
        chart, sizing = solve_sizing_for_mission(
            mission=self.mission,
            aero=self.aero,
        )
        self.assertEqual(len(chart.curves), 7)
        self.assertGreater(chart.ws_max_stall_pa, 0.0)
        self.assertGreater(chart.ws_max_landing_pa, 0.0)
        self.assertGreater(chart.optimum_design_point[0], 0.0)
        self.assertGreater(chart.optimum_design_point[1], 0.0)
        self.assertTrue(sizing.converged)

    def test_recommender(self) -> None:
        motors = recommend_motors(target_power_w=400.0, limit=5)
        self.assertGreater(len(motors), 0)
        self.assertGreater(motors[0].max_power_w, 200.0)

        props = recommend_propellers(target_power_w=400.0, v_cruise_mps=18.0, limit=5)
        self.assertGreater(len(props), 0)
        self.assertGreater(props[0].diameter_in, 5.0)


if __name__ == "__main__":
    unittest.main()
