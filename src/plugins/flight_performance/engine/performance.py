"""Steady level-flight performance of a fixed-wing aircraft."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.optimize import root_scalar

from plugins.electrical_propulsion.powertrain import Powertrain, PowertrainPoint
from setuav_studio.model.atmosphere import G0


@dataclass(frozen=True)
class DragPolar:
    """Parabolic drag polar ``CD = CD0 + k * CL²``."""

    cd0: float
    k_induced: float

    @property
    def max_lift_to_drag(self) -> float:
        return 1.0 / (2.0 * math.sqrt(self.cd0 * self.k_induced))

    @property
    def cl_at_max_lift_to_drag(self) -> float:
        return math.sqrt(self.cd0 / self.k_induced)


@dataclass(frozen=True)
class AerodynamicModel:
    """Untrimmed aircraft aerodynamics used for level-flight performance.

    ``polar_cl`` / ``polar_cd`` hold the converged pre-stall polar sorted by CL. The
    drag coefficient follows the fitted parabolic polar when one fits the data, and
    the tabulated polar otherwise.
    """

    area_m2: float
    cl_max: float
    polar_cl: np.ndarray
    polar_cd: np.ndarray
    drag_polar: DragPolar | None

    def drag_coefficient(self, cl: np.ndarray) -> np.ndarray:
        if self.drag_polar is not None:
            return self.drag_polar.cd0 + self.drag_polar.k_induced * cl**2
        return np.interp(cl, self.polar_cl, self.polar_cd)

    @property
    def max_lift_to_drag(self) -> float:
        if self.drag_polar is not None:
            return self.drag_polar.max_lift_to_drag
        return float(np.max(self.polar_cl / self.polar_cd))

    @property
    def cl_at_max_lift_to_drag(self) -> float:
        if self.drag_polar is not None:
            return self.drag_polar.cl_at_max_lift_to_drag
        return float(self.polar_cl[int(np.argmax(self.polar_cl / self.polar_cd))])


@dataclass(frozen=True)
class PropulsionSweep:
    """Powertrain response across the velocity sweep."""

    thrust_available: np.ndarray
    power_available: np.ndarray
    throttle_pct: np.ndarray
    electrical_power: np.ndarray
    current: np.ndarray
    feasible: np.ndarray


@dataclass(frozen=True)
class PerformanceEnvelope:
    """Level-flight performance across a velocity sweep."""

    velocities: np.ndarray
    lift_coefficient: np.ndarray
    drag: np.ndarray
    power_required: np.ndarray
    stall_speed: float
    min_power_speed: float
    best_lift_to_drag_speed: float
    propulsion: PropulsionSweep | None
    rate_of_climb: np.ndarray
    climb_angle_deg: np.ndarray
    endurance_min: np.ndarray
    range_km: np.ndarray


def aerobuildup_cl_max(polar_points: Sequence[Any]) -> tuple[float, float, bool]:
    """Return (CLmax, alpha at CLmax, stall confirmed) of a converged polar.

    A peak is confirmed only when the polar after it contains a meaningful CL
    decrease; otherwise the sweep has not reached stall.
    """
    points = [
        point
        for point in polar_points
        if point.converged and math.isfinite(point.cl) and math.isfinite(point.alpha)
    ]
    if not points:
        return 0.0, 0.0, False
    peak_index = max(range(len(points)), key=lambda index: points[index].cl)
    peak = points[peak_index]
    post_peak = [point.cl for point in points[peak_index + 1 :]]
    drop_threshold = max(abs(peak.cl) * 0.02, 0.01)
    confirmed = bool(post_peak and min(post_peak) <= peak.cl - drop_threshold)
    return float(peak.cl), float(peak.alpha), confirmed


def stall_speed(mass_kg: float, area_m2: float, cl_max: float, rho: float) -> float:
    """Return V_stall = sqrt(2 W / (rho S CLmax)) in m/s."""
    if mass_kg <= 0.0 or area_m2 <= 0.0 or cl_max <= 0.0 or rho <= 0.0:
        raise ValueError(
            "Stall speed needs positive mass, wing area, CLmax and air density "
            f"(got m={mass_kg}, S={area_m2}, CLmax={cl_max}, rho={rho})."
        )
    return math.sqrt(2.0 * mass_kg * G0 / (rho * area_m2 * cl_max))


def fit_drag_polar(cl_values: npt.ArrayLike, cd_values: npt.ArrayLike) -> DragPolar | None:
    """Fit ``CD = CD0 + k CL²`` to a pre-stall polar.

    Returns ``None`` when the samples do not determine a physical parabolic polar
    (fewer than three valid points, non-positive coefficients or a poor fit).
    """
    cl_arr = np.asarray(cl_values, dtype=float)
    cd_arr = np.asarray(cd_values, dtype=float)
    if cl_arr.shape != cd_arr.shape:
        raise ValueError("Drag polar fit needs as many CD values as CL values.")
    valid = np.isfinite(cl_arr) & np.isfinite(cd_arr) & (cd_arr > 0.0)
    x = cl_arr[valid] ** 2
    y = cd_arr[valid]
    if len(x) < 3 or float(np.ptp(x)) <= 1e-12:
        return None
    a_mat = np.vstack([np.ones_like(x), x]).T
    coeffs, _, _, _ = np.linalg.lstsq(a_mat, y, rcond=None)
    cd0, k_induced = float(coeffs[0]), float(coeffs[1])
    if not (cd0 > 0.0 and k_induced > 0.0):
        return None
    residual = float(np.sum((y - a_mat @ coeffs) ** 2))
    total = float(np.sum((y - float(np.mean(y))) ** 2))
    if total > 1e-12 and 1.0 - residual / total < 0.80:
        return None
    return DragPolar(cd0=cd0, k_induced=k_induced)


def max_level_speed(
    velocities: np.ndarray,
    thrust_available: np.ndarray,
    thrust_required: np.ndarray,
    feasible: np.ndarray,
) -> tuple[float, bool]:
    """Return the thrust-balance speed and whether the sweep bounds it.

    The speed is interpolated at the first available-to-required thrust crossing
    after the last feasible point. It is ``(0.0, False)`` when no point is feasible
    and the last feasible velocity, unbounded, when the sweep ends first.
    """
    margin = thrust_available - thrust_required
    valid_indices = np.flatnonzero(np.asarray(feasible, dtype=bool) & (margin >= 0.0))
    if not len(valid_indices):
        return 0.0, False
    last = int(valid_indices[-1])
    if last >= len(velocities) - 1 or margin[last + 1] >= 0.0:
        return float(velocities[last]), False
    m0, m1 = float(margin[last]), float(margin[last + 1])
    fraction = m0 / (m0 - m1)
    return float(velocities[last] + fraction * (velocities[last + 1] - velocities[last])), True


_THROTTLE_SAMPLES = tuple(float(value) for value in np.linspace(0.05, 1.0, 20))


def feasible_throttle_range(
    powertrain: Powertrain, *, rho: float, airspeed_mps: float
) -> tuple[float, float] | None:
    """Return the throttle interval with valid operating points, or ``None``.

    Below the interval the propeller runs outside its data at this airspeed; above
    it a motor or the battery exceeds its current limit.
    """

    def feasible(throttle: float) -> bool:
        return powertrain.solve(rho=rho, airspeed_mps=airspeed_mps, throttle=throttle).feasible

    flags = [feasible(throttle) for throttle in _THROTTLE_SAMPLES]
    indices = [index for index, flag in enumerate(flags) if flag]
    if not indices:
        return None
    first, last = indices[0], indices[-1]
    low = _THROTTLE_SAMPLES[first]
    if first > 0:
        low = _feasibility_edge(feasible, _THROTTLE_SAMPLES[first - 1], low)
    high = _THROTTLE_SAMPLES[last]
    if last < len(_THROTTLE_SAMPLES) - 1:
        high = _feasibility_edge(feasible, high, _THROTTLE_SAMPLES[last + 1])
    return low, high


def _feasibility_edge(feasible: Callable[[float], bool], a: float, b: float) -> float:
    """Return the feasible side of the feasibility boundary between ``a`` and ``b``."""
    feasible_end, infeasible_end = (a, b) if feasible(a) else (b, a)
    for _ in range(24):
        mid = 0.5 * (feasible_end + infeasible_end)
        if feasible(mid):
            feasible_end = mid
        else:
            infeasible_end = mid
    return feasible_end


def throttle_for_thrust(
    powertrain: Powertrain,
    *,
    rho: float,
    airspeed_mps: float,
    thrust_n: float,
    throttle_range: tuple[float, float] | None,
) -> tuple[float, PowertrainPoint | None]:
    """Return (throttle, operating point) delivering ``thrust_n`` inside ``throttle_range``.

    The operating point is ``None`` when no valid operating point delivers the thrust:
    the powertrain is too weak, or the thrust lies below what it can model at this
    airspeed.
    """
    if throttle_range is None:
        return 0.0, None
    low, high = throttle_range

    def point(throttle: float) -> PowertrainPoint:
        return powertrain.solve(rho=rho, airspeed_mps=airspeed_mps, throttle=throttle)

    if point(high).thrust_n < thrust_n:
        return high, None
    if point(low).thrust_n > thrust_n:
        return low, None
    root = root_scalar(
        lambda throttle: point(throttle).thrust_n - thrust_n,
        bracket=[low, high],
        method="brentq",
    )
    throttle = float(root.root)
    solved = point(throttle)
    return throttle, solved if solved.feasible else None


def velocity_sweep(
    *, v_min: float, v_max: float, v_step: float, minimum_speed: float
) -> np.ndarray:
    """Return the swept velocities from ``max(v_min, minimum_speed)`` to ``v_max``."""
    start = max(v_min, minimum_speed)
    if start >= v_max:
        raise ValueError(
            f"Velocity sweep is empty: it starts at {start:.2f} m/s "
            f"(stall-limited) but V_max is {v_max:.2f} m/s."
        )
    velocities = np.arange(start, v_max + 1e-9, v_step)
    if len(velocities) < 2:
        raise ValueError("Velocity sweep needs at least two points; reduce the speed step.")
    return velocities


def level_flight_envelope(
    *,
    mass_kg: float,
    rho: float,
    aero: AerodynamicModel,
    velocities: np.ndarray,
    powertrain: Powertrain | None,
    reserve_soc: float,
    progress: Callable[[float], None] = lambda _fraction: None,
) -> PerformanceEnvelope:
    """Solve steady level flight across ``velocities``.

    Endurance and range are the time and distance flown at constant battery power
    from the powertrain's state of charge down to ``reserve_soc``.
    """
    weight_n = mass_kg * G0
    dynamic_force = 0.5 * rho * velocities**2 * aero.area_m2
    cl = weight_n / dynamic_force
    drag = dynamic_force * aero.drag_coefficient(cl)
    power_required = drag * velocities
    v_stall = stall_speed(mass_kg, aero.area_m2, aero.cl_max, rho)
    best_ld_speed = math.sqrt(2.0 * weight_n / (rho * aero.area_m2 * aero.cl_at_max_lift_to_drag))

    propulsion = None
    rate_of_climb = climb_angle = endurance = range_km = np.array([])
    if powertrain is not None:
        propulsion = _propulsion_sweep(powertrain, rho, velocities, drag, progress)
        excess = np.maximum(0.0, propulsion.power_available - power_required)
        rate_of_climb = np.where(propulsion.feasible, excess / weight_n, 0.0)
        climb_angle = np.degrees(np.arcsin(np.clip(rate_of_climb / velocities, 0.0, 1.0)))
        hours = np.zeros_like(velocities)
        for index in np.flatnonzero(propulsion.feasible & (propulsion.electrical_power > 0.0)):
            hours[index] = (
                powertrain.discharge_time_s(
                    power_w=float(propulsion.electrical_power[index]), final_soc=reserve_soc
                )
                / 3600.0
            )
        endurance = hours * 60.0
        range_km = velocities * 3.6 * hours

    return PerformanceEnvelope(
        velocities=velocities,
        lift_coefficient=cl,
        drag=drag,
        power_required=power_required,
        stall_speed=v_stall,
        min_power_speed=float(velocities[int(np.argmin(power_required))]),
        best_lift_to_drag_speed=best_ld_speed,
        propulsion=propulsion,
        rate_of_climb=rate_of_climb,
        climb_angle_deg=climb_angle,
        endurance_min=endurance,
        range_km=range_km,
    )


def _propulsion_sweep(
    powertrain: Powertrain,
    rho: float,
    velocities: np.ndarray,
    drag: np.ndarray,
    progress: Callable[[float], None],
) -> PropulsionSweep:
    count = len(velocities)
    thrust_available = np.zeros(count)
    throttle_pct = np.zeros(count)
    electrical_power = np.zeros(count)
    current = np.zeros(count)
    feasible = np.zeros(count, dtype=bool)
    for index, velocity in enumerate(velocities):
        progress(index / count)
        v = float(velocity)
        throttle_range = feasible_throttle_range(powertrain, rho=rho, airspeed_mps=v)
        if throttle_range is not None:
            thrust_available[index] = powertrain.solve(
                rho=rho, airspeed_mps=v, throttle=throttle_range[1]
            ).thrust_n
        throttle, point = throttle_for_thrust(
            powertrain,
            rho=rho,
            airspeed_mps=v,
            thrust_n=float(drag[index]),
            throttle_range=throttle_range,
        )
        throttle_pct[index] = throttle * 100.0
        if point is not None:
            electrical_power[index] = point.battery_power_w
            current[index] = point.battery_current_a
            feasible[index] = True
    return PropulsionSweep(
        thrust_available=thrust_available,
        power_available=thrust_available * velocities,
        throttle_pct=throttle_pct,
        electrical_power=electrical_power,
        current=current,
        feasible=feasible,
    )


__all__ = [
    "AerodynamicModel",
    "DragPolar",
    "PerformanceEnvelope",
    "PropulsionSweep",
    "aerobuildup_cl_max",
    "feasible_throttle_range",
    "fit_drag_polar",
    "level_flight_envelope",
    "max_level_speed",
    "stall_speed",
    "throttle_for_thrust",
    "velocity_sweep",
]
