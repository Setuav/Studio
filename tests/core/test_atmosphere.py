"""Unit tests for the independent Atmosphere model."""

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
    assert math.isclose(atm.dynamic_viscosity_pa_s, 1.789e-5, abs_tol=1e-7)


def test_troposphere_lapse() -> None:
    # At 1000m altitude (ISA standard reference values)
    atm_1k = Atmosphere.isa(1000.0)
    assert math.isclose(atm_1k.temperature_k, 281.65, abs_tol=1e-9)
    assert math.isclose(atm_1k.pressure_pa, 89874.57, abs_tol=0.5)
    assert math.isclose(atm_1k.density_kg_m3, 1.11164, abs_tol=1e-4)
    assert math.isclose(atm_1k.speed_of_sound_mps, 336.434, abs_tol=0.05)


def test_temperature_offset_delta_isa() -> None:
    # ISA +10 degC at sea level
    atm_hot = Atmosphere.isa(0.0, temperature_offset_k=10.0)
    assert math.isclose(atm_hot.temperature_k, 298.15, abs_tol=1e-9)
    assert math.isclose(atm_hot.temperature_c, 25.0, abs_tol=1e-9)
    assert math.isclose(atm_hot.pressure_pa, 101325.0, abs_tol=1e-6)
    assert math.isclose(atm_hot.density_kg_m3, 101325.0 / (287.05287 * 298.15), rel_tol=1e-9)
    assert math.isclose(
        atm_hot.speed_of_sound_mps, math.sqrt(1.4 * 287.05287 * 298.15), rel_tol=1e-9
    )


def test_stratosphere_layers() -> None:
    # Lower stratosphere (11–20 km): isothermal at 216.65 K
    atm_11k = Atmosphere.isa(11000.0)
    atm_15k = Atmosphere.isa(15000.0)
    assert math.isclose(atm_11k.temperature_k, 216.65, abs_tol=1e-9)
    assert math.isclose(atm_11k.pressure_pa, 22632.06, abs_tol=0.5)
    assert math.isclose(atm_11k.density_kg_m3, 0.363918, abs_tol=1e-4)
    assert math.isclose(atm_15k.temperature_k, 216.65, abs_tol=1e-9)
    assert math.isclose(atm_15k.pressure_pa, 12044.57, abs_tol=0.5)
    assert math.isclose(atm_15k.density_kg_m3, 0.193674, abs_tol=1e-4)

    # Middle stratosphere (20–32 km): +1.0 K/km lapse rate
    atm_25k = Atmosphere.isa(25000.0)
    assert math.isclose(atm_25k.temperature_k, 221.65, abs_tol=1e-9)
    assert math.isclose(atm_25k.pressure_pa, 2511.02, abs_tol=0.5)
    assert math.isclose(atm_25k.density_kg_m3, 0.039466, abs_tol=1e-4)

    # High stratosphere (>32 km): isothermal extrapolation at 228.65 K
    atm_35k = Atmosphere.isa(35000.0)
    assert math.isclose(atm_35k.temperature_k, 228.65, abs_tol=1e-9)
    assert math.isclose(atm_35k.pressure_pa, 554.45, abs_tol=0.1)


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
