"""Tests for the battery chemistry profiles and the packs built from them."""

from __future__ import annotations

from typing import Any

import pytest
from pythrust.battery import BatteryState

from plugins.electrical_propulsion.chemistry import CHEMISTRIES, chemistry_profile
from plugins.electrical_propulsion.models.battery import battery_pack, default_battery_pack


def _params(chemistry: str = "LiPo", **values: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "chemistry": chemistry,
        "cell_count": 6,
        "parallel_count": 1,
        "cell_capacity": 5000.0,
        "charge_voltage": None,
        "cell_resistance": None,
        "c_rate": None,
        "pack_mass": None,
    }
    params.update(values)
    return params


@pytest.mark.parametrize("chemistry", CHEMISTRIES)
def test_profile_is_a_consistent_discharge_map(chemistry: str) -> None:
    profile = chemistry_profile(chemistry)

    assert profile.dod[0] == 0.0
    assert profile.dod[-1] == 1.0
    assert all(b < a for a, b in zip(profile.ocv_v, profile.ocv_v[1:], strict=False))
    assert profile.ocv_v[0] <= profile.max_charge_voltage_v
    assert profile.ocv_v[-1] >= profile.cutoff_voltage_v
    assert profile.min_charge_voltage_v <= profile.charge_voltage_v
    assert profile.charge_voltage_v <= profile.max_charge_voltage_v
    assert min(profile.resistance_ratio) > 0.0
    assert profile.source


@pytest.mark.parametrize("chemistry", CHEMISTRIES)
def test_default_pack_delivers_its_capacity_at_one_c(chemistry: str) -> None:
    battery = battery_pack(_params(chemistry)).rate_map()

    result = battery.integrate_c_rate(
        state=BatteryState(soc=1.0), c_rate=1.0, dt_s=3600.0, max_step_s=10.0
    )
    assert result.consumed_charge_ah > 0.9 * battery.capacity_ah


def test_curves_charged_to_the_reference_voltage_are_the_measured_curves() -> None:
    profile = chemistry_profile("LiPo")
    curves = profile.usable_curves(profile.max_charge_voltage_v)

    assert curves.dod == profile.dod
    assert curves.ocv_v == pytest.approx(profile.ocv_v)


def test_lower_charge_voltage_starts_further_down_the_curve() -> None:
    profile = chemistry_profile("LiPo")
    full = profile.usable_curves(4.35)
    standard = profile.usable_curves(4.2)

    rest_drop_v = profile.max_charge_voltage_v - profile.ocv_v[0]
    assert standard.ocv_v[0] == pytest.approx(4.2 - rest_drop_v)
    assert standard.ocv_v[-1] == pytest.approx(full.ocv_v[-1])
    assert (standard.dod[0], standard.dod[-1]) == (0.0, 1.0)
    assert standard.mean_ocv_v < full.mean_ocv_v
    with pytest.raises(ValueError, match="outside"):
        profile.usable_curves(4.4)


def test_cell_properties_scale_with_capacity() -> None:
    small = battery_pack(_params(cell_capacity=2500.0))
    large = battery_pack(_params(cell_capacity=10000.0))
    profile = small.profile

    assert small.cell_resistance_ohm == pytest.approx(4.0 * large.cell_resistance_ohm)
    assert large.cell_resistance_ohm == pytest.approx(profile.resistance_mohm_ah / 1000.0 / 10.0)
    assert large.max_current_a == pytest.approx(4.0 * small.max_current_a)
    # Pack mass grows slower than the capacity: small cells carry more fixed hardware.
    assert large.mass_g == pytest.approx(small.mass_g * 4.0**profile.mass_exponent)
    assert large.mass_g < 4.0 * small.mass_g


def test_rate_map_resistance_is_the_cell_resistance_at_half_usable_dod() -> None:
    pack = battery_pack(_params(cell_capacity=6500.0, parallel_count=2))
    battery = pack.rate_map()

    assert battery.resistance(0.5) == pytest.approx(pack.cell_resistance_ohm)
    assert battery.max_current_a == pytest.approx(pack.c_rate * 6.5)
    assert pack.max_current_a == pytest.approx(battery.max_current_a * 2)
    assert pack.internal_resistance_ohm == pytest.approx(pack.cell_resistance_ohm * 6 / 2)


def test_overrides_replace_the_derived_values() -> None:
    params = _params(charge_voltage=4.35, cell_resistance=0.003, c_rate=25.0, pack_mass=700.0)
    pack = battery_pack(params)
    defaults = default_battery_pack(params)

    assert pack.charge_voltage_v == 4.35
    assert pack.cell_resistance_ohm == 0.003
    assert pack.max_current_a == pytest.approx(25.0 * 5.0)
    assert pack.mass_g == 700.0
    assert defaults.charge_voltage_v == defaults.profile.charge_voltage_v
    assert defaults.mass_g != 700.0
    assert pack.energy_wh > defaults.energy_wh


def test_unknown_chemistry_is_rejected() -> None:
    with pytest.raises(ValueError, match="not supported"):
        chemistry_profile("NiCd")
