"""Thrust, power, and loading conversion utilities for aircraft sizing.

References:
- Mattingly, J.D., "Aircraft Engine Design", 3rd Ed., Ch. 2.
- Gudmundsson, S., "General Aviation Aircraft Design", Ch. 3.
"""

from __future__ import annotations

from typing import Any, overload

import numpy as np

from setuav_studio.model.atmosphere import G0

WATTS_PER_HORSEPOWER: float = 745.699872


@overload
def tw_to_pw(
    tw: float,
    speed_mps: float,
    propeller_efficiency: float = 0.75,
) -> float: ...


@overload
def tw_to_pw(
    tw: np.ndarray,
    speed_mps: float,
    propeller_efficiency: float = 0.75,
) -> np.ndarray: ...


def tw_to_pw(
    tw: Any,
    speed_mps: float,
    propeller_efficiency: float = 0.75,
) -> Any:
    """Convert Thrust-to-Weight (T/W) to Power-to-Weight (P/W) in Watts/Newton.

    P/W = (T/W * V) / eta_prop  [W/N]
    """
    eta = max(float(propeller_efficiency), 0.1)
    v = max(float(speed_mps), 0.5)
    return (tw * v) / eta


@overload
def tw_to_power_loading_w_kg(
    tw: float,
    speed_mps: float,
    propeller_efficiency: float = 0.75,
) -> float: ...


@overload
def tw_to_power_loading_w_kg(
    tw: np.ndarray,
    speed_mps: float,
    propeller_efficiency: float = 0.75,
) -> np.ndarray: ...


def tw_to_power_loading_w_kg(
    tw: Any,
    speed_mps: float,
    propeller_efficiency: float = 0.75,
) -> Any:
    """Convert Thrust-to-Weight (T/W) to specific power in Watts per kilogram (W/kg).

    P / m = (P/W) * g_0  [W/kg]
    """
    pw_wn = tw_to_pw(tw, speed_mps, propeller_efficiency)
    return pw_wn * G0


def required_shaft_power_watts(
    pw_wn: float,
    mtow_kg: float,
) -> float:
    """Compute required motor shaft power in Watts from P/W (W/N) and MTOW (kg).

    P = (P/W) * (m * g)  [Watts]
    """
    weight_n = max(float(mtow_kg), 0.01) * G0
    return max(float(pw_wn), 0.0) * weight_n


def watts_to_hp(watts: float) -> float:
    """Convert Watts to mechanical Horsepower (hp)."""
    return float(watts) / WATTS_PER_HORSEPOWER


def hp_to_watts(hp: float) -> float:
    """Convert mechanical Horsepower (hp) to Watts."""
    return float(hp) * WATTS_PER_HORSEPOWER


__all__ = [
    "WATTS_PER_HORSEPOWER",
    "hp_to_watts",
    "required_shaft_power_watts",
    "tw_to_power_loading_w_kg",
    "tw_to_pw",
    "watts_to_hp",
]
