"""Unit tests for the independent Atmosphere model and airspeed conversions."""

from __future__ import annotations

import math

from setuav_studio.model import Atmosphere, Environment


def test_sea_level_standard_isa() -> None:
    atm = Atmosphere.isa(0.0)
    assert math.isclose(atm.altitude_m, 0.0)
    assert math.isclose(atm.temperature_k, 288.15, abs_tol=0.01)
    assert math.isclose(atm.temperature_c, 15.0, abs_tol=0.01)
    assert math.isclose(atm.pressure_pa, 101325.0, abs_tol=1.0)
    assert math.isclose(atm.density_kg_m3, 1.225, abs_tol=0.001)
    assert math.isclose(atm.speed_of_sound_mps, 340.294, abs_tol=0.1)
    assert math.isclose(atm.density_ratio_sigma, 1.0, abs_tol=0.0001)
    assert math.isclose(atm.pressure_ratio_delta, 1.0, abs_tol=0.0001)
    assert math.isclose(atm.temperature_ratio_theta, 1.0, abs_tol=0.0001)
    assert math.isclose(atm.dynamic_viscosity_pa_s, 1.789e-5, abs_tol=1e-7)


def test_troposphere_lapse() -> None:
    # At 1000m altitude
    atm_1k = Atmosphere.isa(1000.0)
    # Lapse rate is -6.5 K/km -> T = 288.15 - 6.5 = 281.65 K
    assert math.isclose(atm_1k.temperature_k, 281.65, abs_tol=0.01)
    assert atm_1k.pressure_pa < 101325.0
    assert atm_1k.density_kg_m3 < 1.225
    assert atm_1k.speed_of_sound_mps < 340.294
    assert atm_1k.density_ratio_sigma < 1.0
    assert atm_1k.pressure_ratio_delta < 1.0


def test_temperature_offset_delta_isa() -> None:
    # ISA +10 degC at sea level
    atm_hot = Atmosphere.isa(0.0, temperature_offset_k=10.0)
    assert math.isclose(atm_hot.temperature_k, 298.15, abs_tol=0.01)
    assert math.isclose(atm_hot.temperature_c, 25.0, abs_tol=0.01)
    # Pressure remains barometric baseline
    assert math.isclose(atm_hot.pressure_pa, 101325.0, abs_tol=1.0)
    # Hot air is less dense
    assert atm_hot.density_kg_m3 < 1.225
    # Speed of sound is higher in warmer air
    assert atm_hot.speed_of_sound_mps > 340.294


def test_stratosphere_isothermal_layer() -> None:
    # 11,000m to 20,000m is isothermal at 216.65 K
    atm_11k = Atmosphere.isa(11000.0)
    atm_15k = Atmosphere.isa(15000.0)
    assert math.isclose(atm_11k.temperature_k, 216.65, abs_tol=0.01)
    assert math.isclose(atm_15k.temperature_k, 216.65, abs_tol=0.01)
    assert atm_15k.pressure_pa < atm_11k.pressure_pa
    assert atm_15k.density_kg_m3 < atm_11k.density_kg_m3


def test_flight_helpers() -> None:
    atm = Atmosphere.isa(1000.0)
    v = 25.0  # m/s (~90 km/h)
    q = atm.dynamic_pressure(v)
    expected_q = 0.5 * atm.density_kg_m3 * (v**2)
    assert math.isclose(q, expected_q, rel_tol=1e-4)

    mach = atm.mach_number(v)
    assert math.isclose(mach, v / atm.speed_of_sound_mps, rel_tol=1e-4)

    re = atm.reynolds_number(v, length_m=0.2)
    expected_re = (atm.density_kg_m3 * v * 0.2) / atm.dynamic_viscosity_pa_s
    assert math.isclose(re, expected_re, rel_tol=1e-3)


def test_airspeed_conversions_sea_level() -> None:
    atm = Atmosphere.isa(0.0)
    v = 30.0  # m/s
    # At sea level standard, TAS == EAS == CAS
    assert math.isclose(atm.tas_to_eas(v), v, abs_tol=0.001)
    assert math.isclose(atm.eas_to_tas(v), v, abs_tol=0.001)
    assert math.isclose(atm.tas_to_cas(v), v, abs_tol=0.01)
    assert math.isclose(atm.cas_to_tas(v), v, abs_tol=0.01)


def test_airspeed_conversions_altitude_roundtrip() -> None:
    atm = Atmosphere.isa(3000.0)
    tas = 45.0  # m/s
    eas = atm.tas_to_eas(tas)
    assert eas < tas  # EAS is lower than TAS at altitude
    assert math.isclose(atm.eas_to_tas(eas), tas, rel_tol=1e-4)

    cas = atm.tas_to_cas(tas)
    assert math.isclose(atm.cas_to_tas(cas), tas, rel_tol=1e-3)


def test_to_environment_and_serialization() -> None:
    atm = Atmosphere.isa(1500.0, temperature_offset_k=5.0)
    env = atm.to_environment(wind_vector_mps=(5.0, 0.0, 0.0))
    assert isinstance(env, Environment)
    assert math.isclose(env.altitude_m, 1500.0)
    assert math.isclose(env.density_kg_m3, atm.density_kg_m3, rel_tol=1e-4)
    assert env.wind_vector_mps == (5.0, 0.0, 0.0)

    # Dict serialization & restoration
    d = atm.to_dict()
    restored = Atmosphere.from_dict(d)
    assert math.isclose(restored.density_kg_m3, atm.density_kg_m3, rel_tol=1e-5)
    assert math.isclose(restored.temperature_k, atm.temperature_k, rel_tol=1e-4)


def test_ambient_temperature_keeps_isa_pressure() -> None:
    hot = Atmosphere.at_temperature(1000.0, 30.0)
    standard = Atmosphere.isa(1000.0)
    assert math.isclose(hot.temperature_c, 30.0, abs_tol=1e-9)
    assert math.isclose(hot.pressure_pa, standard.pressure_pa, rel_tol=1e-12)
    assert math.isclose(
        hot.density_kg_m3, standard.pressure_pa / (287.05287 * 303.15), rel_tol=1e-9
    )
