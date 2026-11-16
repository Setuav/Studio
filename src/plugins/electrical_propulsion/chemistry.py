"""Battery chemistry profiles: discharge curves and cell scaling rules per chemistry.

A battery cell is described by its chemistry and its capacity. Each profile in
``data/chemistries`` holds the open-circuit voltage and the resistance shape against
depth of discharge, measured on a reference cell charged to ``max_charge_voltage_v``,
and the rules that derive the other cell properties from the capacity:

- resistance at half the usable depth of discharge is ``resistance_mohm_ah`` divided
  by the capacity: the cell resistance falls with the electrode area while the
  capacity grows with it (constant area-specific impedance);
- the continuous current is ``c_rate`` times the capacity;
- the pack mass per cell, cell hardware share included, is
  ``mass_coefficient_g * capacity_ah ** mass_exponent``.

A lower charge voltage starts the discharge further down the same curve: the usable
curve begins where the open-circuit voltage, less the reference cell's rest drop
below its charge voltage, equals the charge voltage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

CHEMISTRY_DATA_DIR = Path(__file__).resolve().parent / "data" / "chemistries"

CHEMISTRY_FILES = {
    "LiPo": "lipo.json",
    "Li-Ion": "li_ion.json",
}
CHEMISTRIES = tuple(CHEMISTRY_FILES)


@dataclass(frozen=True)
class UsableCurves:
    """Cell curves over the usable depth of discharge from a given charge voltage."""

    dod: tuple[float, ...]
    ocv_v: tuple[float, ...]
    resistance_ratio: tuple[float, ...]
    """Resistance relative to its value at half the usable depth of discharge."""

    @property
    def mean_ocv_v(self) -> float:
        """Open-circuit voltage averaged over the charge, i.e. energy per charge."""
        return float(np.trapezoid(self.ocv_v, self.dod))


@dataclass(frozen=True)
class ChemistryProfile:
    """Discharge curves and scaling rules of one cell chemistry."""

    chemistry: str
    source: str
    nominal_voltage_v: float
    charge_voltage_v: float
    max_charge_voltage_v: float
    cutoff_voltage_v: float
    resistance_mohm_ah: float
    c_rate: float
    mass_coefficient_g: float
    mass_exponent: float
    dod: tuple[float, ...]
    ocv_v: tuple[float, ...]
    resistance_ratio: tuple[float, ...]

    @property
    def min_charge_voltage_v(self) -> float:
        return self.nominal_voltage_v

    def cell_resistance_ohm(self, capacity_ah: float) -> float:
        """Resistance at half the usable depth of discharge of a cell of ``capacity_ah``."""
        return self.resistance_mohm_ah / 1000.0 / capacity_ah

    def pack_mass_per_cell_g(self, capacity_ah: float) -> float:
        """Pack mass per cell of ``capacity_ah``, cell hardware share included."""
        return self.mass_coefficient_g * capacity_ah**self.mass_exponent

    def usable_curves(self, charge_voltage_v: float) -> UsableCurves:
        """Return the curves of a cell charged to ``charge_voltage_v``."""
        if not self.min_charge_voltage_v <= charge_voltage_v <= self.max_charge_voltage_v:
            raise ValueError(
                f"{self.chemistry} charge voltage {charge_voltage_v:g} V is outside "
                f"{self.min_charge_voltage_v:g} V to {self.max_charge_voltage_v:g} V."
            )
        dod = np.asarray(self.dod)
        ocv = np.asarray(self.ocv_v)
        ratio = np.asarray(self.resistance_ratio)
        rest_ocv_v = charge_voltage_v - (self.max_charge_voltage_v - ocv[0])
        start = float(np.interp(rest_ocv_v, ocv[::-1], dod[::-1]))

        keep = dod > start
        full_dod = np.concatenate([[start], dod[keep]])
        usable_dod = (full_dod - start) / (1.0 - start)
        usable_ratio = np.interp(full_dod, dod, ratio)
        usable_ratio /= np.interp(0.5, usable_dod, usable_ratio)
        return UsableCurves(
            dod=tuple(float(v) for v in usable_dod),
            ocv_v=tuple(float(v) for v in np.interp(full_dod, dod, ocv)),
            resistance_ratio=tuple(float(v) for v in usable_ratio),
        )


@cache
def chemistry_profile(chemistry: str) -> ChemistryProfile:
    """Return the profile of ``chemistry``."""
    try:
        filename = CHEMISTRY_FILES[chemistry]
    except KeyError:
        raise ValueError(f"Battery chemistry '{chemistry}' is not supported.") from None
    data = json.loads((CHEMISTRY_DATA_DIR / filename).read_text(encoding="utf-8"))
    if data["chemistry"] != chemistry:
        raise ValueError(f"Chemistry profile {filename} declares '{data['chemistry']}'.")
    curves = data["curves"]
    return ChemistryProfile(
        chemistry=chemistry,
        source=data["source"],
        nominal_voltage_v=float(data["nominal_voltage_v"]),
        charge_voltage_v=float(data["charge_voltage_v"]),
        max_charge_voltage_v=float(data["max_charge_voltage_v"]),
        cutoff_voltage_v=float(data["cutoff_voltage_v"]),
        resistance_mohm_ah=float(data["resistance_mohm_ah"]),
        c_rate=float(data["c_rate"]),
        mass_coefficient_g=float(data["mass_coefficient_g"]),
        mass_exponent=float(data["mass_exponent"]),
        dod=tuple(float(v) for v in curves["dod"]),
        ocv_v=tuple(float(v) for v in curves["ocv_v"]),
        resistance_ratio=tuple(float(v) for v in curves["resistance_ratio"]),
    )


__all__ = [
    "CHEMISTRIES",
    "CHEMISTRY_DATA_DIR",
    "ChemistryProfile",
    "UsableCurves",
    "chemistry_profile",
]
