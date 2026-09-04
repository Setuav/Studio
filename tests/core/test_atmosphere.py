"""Unit tests for the independent Atmosphere model and airspeed conversions."""

from __future__ import annotations

import unittest

from setuav_studio.model import Atmosphere, Environment


class TestAtmosphereModel(unittest.TestCase):
    def test_sea_level_standard_isa(self) -> None:
        atm = Atmosphere.isa(0.0)
        self.assertAlmostEqual(atm.altitude_m, 0.0)
        self.assertAlmostEqual(atm.temperature_k, 288.15, places=2)
        self.assertAlmostEqual(atm.temperature_c, 15.0, places=2)
        self.assertAlmostEqual(atm.pressure_pa, 101325.0, places=0)
        self.assertAlmostEqual(atm.density_kg_m3, 1.225, places=3)
        self.assertAlmostEqual(atm.speed_of_sound_mps, 340.294, places=1)
        self.assertAlmostEqual(atm.density_ratio_sigma, 1.0, places=4)
        self.assertAlmostEqual(atm.pressure_ratio_delta, 1.0, places=4)
        self.assertAlmostEqual(atm.temperature_ratio_theta, 1.0, places=4)
        self.assertAlmostEqual(atm.dynamic_viscosity_pa_s, 1.789e-5, places=7)

    def test_troposphere_lapse(self) -> None:
        # At 1000m altitude
        atm_1k = Atmosphere.isa(1000.0)
        # Lapse rate is -6.5 K/km -> T = 288.15 - 6.5 = 281.65 K
        self.assertAlmostEqual(atm_1k.temperature_k, 281.65, places=2)
        self.assertLess(atm_1k.pressure_pa, 101325.0)
        self.assertLess(atm_1k.density_kg_m3, 1.225)
        self.assertLess(atm_1k.speed_of_sound_mps, 340.294)
        self.assertLess(atm_1k.density_ratio_sigma, 1.0)
        self.assertLess(atm_1k.pressure_ratio_delta, 1.0)

    def test_temperature_offset_delta_isa(self) -> None:
        # ISA +10 degC at sea level
        atm_hot = Atmosphere.isa(0.0, temperature_offset_k=10.0)
        self.assertAlmostEqual(atm_hot.temperature_k, 298.15, places=2)
        self.assertAlmostEqual(atm_hot.temperature_c, 25.0, places=2)
        # Pressure remains barometric baseline
        self.assertAlmostEqual(atm_hot.pressure_pa, 101325.0, places=0)
        # Hot air is less dense
        self.assertLess(atm_hot.density_kg_m3, 1.225)
        # Speed of sound is higher in warmer air
        self.assertGreater(atm_hot.speed_of_sound_mps, 340.294)

    def test_stratosphere_isothermal_layer(self) -> None:
        # 11,000m to 20,000m is isothermal at 216.65 K
        atm_11k = Atmosphere.isa(11000.0)
        atm_15k = Atmosphere.isa(15000.0)
        self.assertAlmostEqual(atm_11k.temperature_k, 216.65, places=2)
        self.assertAlmostEqual(atm_15k.temperature_k, 216.65, places=2)
        self.assertLess(atm_15k.pressure_pa, atm_11k.pressure_pa)
        self.assertLess(atm_15k.density_kg_m3, atm_11k.density_kg_m3)

    def test_flight_helpers(self) -> None:
        atm = Atmosphere.isa(1000.0)
        v = 25.0  # m/s (~90 km/h)
        q = atm.dynamic_pressure(v)
        expected_q = 0.5 * atm.density_kg_m3 * (v**2)
        self.assertAlmostEqual(q, expected_q, places=3)

        mach = atm.mach_number(v)
        self.assertAlmostEqual(mach, v / atm.speed_of_sound_mps, places=4)

        re = atm.reynolds_number(v, length_m=0.2)
        expected_re = (atm.density_kg_m3 * v * 0.2) / atm.dynamic_viscosity_pa_s
        self.assertAlmostEqual(re, expected_re, places=1)

    def test_airspeed_conversions_sea_level(self) -> None:
        atm = Atmosphere.isa(0.0)
        v = 30.0  # m/s
        # At sea level standard, TAS == EAS == CAS
        self.assertAlmostEqual(atm.tas_to_eas(v), v, places=3)
        self.assertAlmostEqual(atm.eas_to_tas(v), v, places=3)
        self.assertAlmostEqual(atm.tas_to_cas(v), v, places=2)
        self.assertAlmostEqual(atm.cas_to_tas(v), v, places=2)

    def test_airspeed_conversions_altitude_roundtrip(self) -> None:
        atm = Atmosphere.isa(3000.0)
        tas = 45.0  # m/s
        eas = atm.tas_to_eas(tas)
        self.assertLess(eas, tas)  # EAS is lower than TAS at altitude
        self.assertAlmostEqual(atm.eas_to_tas(eas), tas, places=4)

        cas = atm.tas_to_cas(tas)
        self.assertAlmostEqual(atm.cas_to_tas(cas), tas, places=3)

    def test_to_environment_and_serialization(self) -> None:
        atm = Atmosphere.isa(1500.0, temperature_offset_k=5.0)
        env = atm.to_environment(wind_vector_mps=(5.0, 0.0, 0.0))
        self.assertIsInstance(env, Environment)
        self.assertAlmostEqual(env.altitude_m, 1500.0)
        self.assertAlmostEqual(env.density_kg_m3, atm.density_kg_m3, places=4)
        self.assertEqual(env.wind_vector_mps, (5.0, 0.0, 0.0))

        # Dict serialization & restoration
        d = atm.to_dict()
        restored = Atmosphere.from_dict(d)
        self.assertAlmostEqual(restored.density_kg_m3, atm.density_kg_m3, places=5)
        self.assertAlmostEqual(restored.temperature_k, atm.temperature_k, places=3)


if __name__ == "__main__":
    unittest.main()
