"""Tests for the battery cell catalogue."""

from __future__ import annotations

import pytest
from pythrust.battery import BatteryState

from plugins.electrical_propulsion.cells import (
    CHEMISTRIES,
    DEFAULT_CELLS,
    cell_catalog,
    cell_spec,
    chemistry_cells,
)


def test_every_chemistry_has_a_default_cell_of_that_chemistry() -> None:
    assert set(DEFAULT_CELLS) == set(CHEMISTRIES)
    for chemistry, cell_id in DEFAULT_CELLS.items():
        cell = cell_spec(cell_id)
        assert cell.chemistry == chemistry
        assert cell in chemistry_cells(chemistry)


@pytest.mark.parametrize("cell_id", sorted(cell_catalog()))
def test_cell_dataset_is_a_consistent_rate_map(cell_id: str) -> None:
    cell = cell_spec(cell_id)
    battery = cell.rate_map(series=1, parallel=1)

    assert battery.capacity_ah == cell.capacity_ah
    assert battery.charge_voltage_v == cell.charge_voltage_v
    assert battery.cutoff_voltage_v == cell.cutoff_voltage_v
    assert battery.ocv(0.0) <= cell.charge_voltage_v
    assert battery.ocv(1.0) >= cell.cutoff_voltage_v
    assert battery.ocv(1.0) < cell.nominal_voltage_v < battery.ocv(0.0)
    assert cell.source

    # A 1C discharge delivers most of the rated charge before the cut-off.
    result = battery.integrate_c_rate(
        state=BatteryState(soc=1.0), c_rate=1.0, dt_s=3600.0, max_step_s=10.0
    )
    assert result.consumed_charge_ah > 0.9 * cell.capacity_ah


def test_unknown_cell_is_rejected() -> None:
    with pytest.raises(ValueError, match="not in the cell catalogue"):
        cell_spec("unknown_cell")
