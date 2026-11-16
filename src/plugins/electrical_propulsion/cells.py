"""Battery cell catalogue: rate-map cell datasets with a default cell per chemistry.

Each dataset in ``data/cells`` describes one cell in PyThrust's rate-map JSON format
(``cell`` limits and ``curves`` of open-circuit voltage and resistance against depth
of discharge) plus the catalogue fields ``id``, ``chemistry``, ``nominal_voltage_v``
and ``mass_g``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pythrust.battery import RateMapBattery

CELL_DATA_DIR = Path(__file__).resolve().parent / "data" / "cells"

CHEMISTRIES = ("LiPo", "Li-Ion", "LiFePO4", "Solid-State", "NiMH")

DEFAULT_CELLS = {
    "LiPo": "lipo_6000",
    "Li-Ion": "molicel_p42a",
    "LiFePO4": "lifepo4_26650_2500",
    "Solid-State": "semi_solid_6500",
    "NiMH": "nimh_subc_3000",
}


@dataclass(frozen=True)
class CellSpec:
    """One catalogue cell."""

    id: str
    name: str
    chemistry: str
    source: str
    capacity_ah: float
    nominal_voltage_v: float
    charge_voltage_v: float
    cutoff_voltage_v: float
    max_current_a: float
    mass_g: float
    path: Path

    def rate_map(self, *, series: int, parallel: int) -> RateMapBattery:
        """Return a pack of this cell with the given series and parallel counts."""
        return RateMapBattery.from_json(self.path, series=series, parallel=parallel)

    @property
    def mid_discharge_resistance_ohm(self) -> float:
        """Cell resistance at half depth of discharge."""
        return self.rate_map(series=1, parallel=1).resistance(0.5)


@cache
def cell_catalog() -> dict[str, CellSpec]:
    """Return every catalogue cell by id."""
    catalog: dict[str, CellSpec] = {}
    for path in sorted(CELL_DATA_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        cell = data["cell"]
        spec = CellSpec(
            id=data["id"],
            name=data["name"],
            chemistry=data["chemistry"],
            source=data["source"],
            capacity_ah=float(cell["capacity_ah"]),
            nominal_voltage_v=float(cell["nominal_voltage_v"]),
            charge_voltage_v=float(cell["charge_voltage_v"]),
            cutoff_voltage_v=float(cell["cutoff_voltage_v"]),
            max_current_a=float(cell["max_current_a"]),
            mass_g=float(cell["mass_g"]),
            path=path,
        )
        if spec.id != path.stem:
            raise ValueError(f"Cell dataset {path.name} declares id '{spec.id}'.")
        if spec.chemistry not in CHEMISTRIES:
            raise ValueError(f"Cell '{spec.id}' has unknown chemistry '{spec.chemistry}'.")
        catalog[spec.id] = spec
    return catalog


def cell_spec(cell_id: str) -> CellSpec:
    """Return the catalogue cell ``cell_id``."""
    try:
        return cell_catalog()[cell_id]
    except KeyError:
        raise ValueError(f"Battery cell '{cell_id}' is not in the cell catalogue.") from None


def chemistry_cells(chemistry: str) -> list[CellSpec]:
    """Return the catalogue cells of ``chemistry``."""
    return [spec for spec in cell_catalog().values() if spec.chemistry == chemistry]


__all__ = [
    "CELL_DATA_DIR",
    "CHEMISTRIES",
    "DEFAULT_CELLS",
    "CellSpec",
    "cell_catalog",
    "cell_spec",
    "chemistry_cells",
]
