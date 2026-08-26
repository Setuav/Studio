"""Derived flight curves, speed metrics, and public result assembly."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from .models import (
    CruisePerformance,
    FlightCurves,
    FlightEnvelopeResult,
    OptimalSpeeds,
    PerformanceMetrics,
)


@dataclass
class _DerivedCurves:
    rate_of_climb: np.ndarray
    climb_angle_deg: np.ndarray
    range_km: np.ndarray
    endurance_hours: np.ndarray


@dataclass
class _SpeedSummary:
    optimal: OptimalSpeeds
    best_range_index: int | None
    max_speed: float
    max_speed_bounded: bool
    max_ld: float
    max_rate_of_climb: float
    best_climb_angle: float
    min_power_required: float
    max_range: float
    max_endurance: float


class FlightPerformanceResultBuilder:
    """Build derived performance curves and the stable public result model."""

    def __init__(self, solver: type[Any]) -> None:
        self.solver = solver

    def build(
        self,
        inputs: Any,
        aero: Any,
        velocities: np.ndarray,
        stall_speed: float,
        power_required: np.ndarray,
        drag_required: np.ndarray,
        propulsion: Any,
    ) -> FlightEnvelopeResult:
        derived = self._derive_curves(inputs, velocities, power_required, propulsion)
        speeds = self._summarize_speeds(
            inputs,
            aero,
            velocities,
            stall_speed,
            power_required,
            drag_required,
            propulsion,
            derived,
        )
        return self._build_result(
            inputs,
            aero,
            velocities,
            stall_speed,
            power_required,
            drag_required,
            propulsion,
            derived,
            speeds,
        )

    def _derive_curves(
        self,
        inputs: Any,
        velocities: np.ndarray,
        power_required: np.ndarray,
        propulsion: Any,
    ) -> _DerivedCurves:
        if propulsion.available:
            excess_power = np.maximum(0.0, propulsion.power_available - power_required)
            rate_of_climb = excess_power / (inputs.mass_kg * 9.81)
            climb_ratio = np.clip(rate_of_climb / np.maximum(velocities, 0.1), 0.0, 1.0)
            climb_angle = np.degrees(np.arcsin(climb_ratio))
        else:
            rate_of_climb = np.array([])
            climb_angle = np.array([])
        range_km, endurance = self._range_endurance_curves(inputs, velocities, propulsion)
        return _DerivedCurves(rate_of_climb, climb_angle, range_km, endurance)

    @staticmethod
    def _range_endurance_curves(
        inputs: Any,
        velocities: np.ndarray,
        propulsion: Any,
    ) -> tuple[np.ndarray, np.ndarray]:
        count = len(velocities)
        ranges = np.zeros(count) if propulsion.available else np.array([])
        endurance = np.zeros(count) if propulsion.available else np.array([])
        if (
            propulsion.available
            and inputs.battery_capacity_ah is not None
            and inputs.battery_voltage is not None
            and inputs.battery_voltage > 0.0
        ):
            energy = (
                inputs.battery_voltage * inputs.battery_capacity_ah * inputs.usable_battery_ratio
            )
            for index in range(count):
                if propulsion.electrical_power[index] > 0 and propulsion.feasible[index]:
                    endurance[index] = energy / propulsion.electrical_power[index]
                    ranges[index] = velocities[index] * 3.6 * endurance[index]
        return ranges, endurance

    def _summarize_speeds(
        self,
        inputs: Any,
        aero: Any,
        velocities: np.ndarray,
        stall_speed: float,
        power_required: np.ndarray,
        drag_required: np.ndarray,
        propulsion: Any,
        derived: _DerivedCurves,
    ) -> _SpeedSummary:
        best_endurance, best_range, best_climb, range_index = self._optimal_speed_values(
            velocities, power_required, propulsion, derived
        )
        if propulsion.available:
            max_speed, bounded = self.solver.resolve_max_speed(
                velocities,
                propulsion.thrust_available,
                drag_required,
                propulsion.feasible,
            )
        else:
            max_speed, bounded = 0.0, False
        best_ld_speed, max_ld = self._best_ld(inputs, aero, best_range, propulsion.available)
        max_roc, best_angle = self._climb_extrema(propulsion, derived)
        return _SpeedSummary(
            optimal=OptimalSpeeds(best_endurance, best_range, best_climb, best_ld_speed),
            best_range_index=range_index,
            max_speed=max_speed,
            max_speed_bounded=bounded,
            max_ld=max_ld,
            max_rate_of_climb=max_roc,
            best_climb_angle=best_angle,
            min_power_required=float(np.min(power_required)),
            max_range=(
                float(np.max(derived.range_km))
                if propulsion.available and len(derived.range_km)
                else 0.0
            ),
            max_endurance=(
                float(np.max(derived.endurance_hours))
                if propulsion.available and len(derived.endurance_hours)
                else 0.0
            ),
        )

    @staticmethod
    def _optimal_speed_values(
        velocities: np.ndarray,
        power_required: np.ndarray,
        propulsion: Any,
        derived: _DerivedCurves,
    ) -> tuple[float, float, float, int | None]:
        feasible_mask = (
            propulsion.feasible & (propulsion.electrical_power > 0)
            if propulsion.available
            else np.zeros(len(velocities), dtype=bool)
        )
        if propulsion.available and np.any(feasible_mask):
            indices = np.where(feasible_mask)[0]
            endurance_index = int(indices[np.argmin(propulsion.electrical_power[feasible_mask])])
            range_index = int(indices[np.argmax(derived.range_km[feasible_mask])])
            climb_index = int(indices[np.argmax(derived.rate_of_climb[feasible_mask])])
        elif propulsion.available:
            endurance_index = int(np.argmin(power_required))
            range_index = int(np.argmin(power_required / np.maximum(velocities, 0.1)))
            climb_index = int(np.argmax(derived.rate_of_climb))
        else:
            return 0.0, 0.0, 0.0, None
        return (
            float(velocities[endurance_index]),
            float(velocities[range_index]),
            float(velocities[climb_index]),
            range_index,
        )

    @staticmethod
    def _best_ld(
        inputs: Any,
        aero: Any,
        best_range_speed: float,
        propulsion_available: bool,
    ) -> tuple[float, float]:
        if aero.k_induced > 0:
            cl_opt = math.sqrt(aero.cd0 / aero.k_induced)
            speed = math.sqrt(
                2.0 * inputs.mass_kg * 9.81 / (inputs.rho * aero.area_m2 * max(cl_opt, 0.01))
            )
            return float(speed), float(1.0 / (2.0 * math.sqrt(aero.cd0 * aero.k_induced)))
        return (best_range_speed if propulsion_available else 0.0), aero.ld_max

    @staticmethod
    def _climb_extrema(propulsion: Any, derived: _DerivedCurves) -> tuple[float, float]:
        if not propulsion.available or not len(derived.rate_of_climb):
            return 0.0, 0.0
        if np.any(propulsion.feasible):
            return (
                float(np.max(derived.rate_of_climb[propulsion.feasible])),
                float(np.max(derived.climb_angle_deg[propulsion.feasible])),
            )
        return float(np.max(derived.rate_of_climb)), float(np.max(derived.climb_angle_deg))

    def _build_result(
        self,
        inputs: Any,
        aero: Any,
        velocities: np.ndarray,
        stall_speed: float,
        power_required: np.ndarray,
        drag_required: np.ndarray,
        propulsion: Any,
        derived: _DerivedCurves,
        speeds: _SpeedSummary,
    ) -> FlightEnvelopeResult:
        metrics = PerformanceMetrics(
            stall_speed=stall_speed,
            max_speed=speeds.max_speed,
            max_ld_ratio=speeds.max_ld,
            glide_ratio=speeds.max_ld,
            best_climb_angle_deg=speeds.best_climb_angle,
            min_power_required=speeds.min_power_required,
            max_range_km=speeds.max_range,
            max_endurance_hours=speeds.max_endurance,
            max_rate_of_climb=speeds.max_rate_of_climb,
        )
        cruise = self._cruise_performance(velocities, propulsion, derived, speeds)
        curves = FlightCurves(
            velocities=velocities.tolist(),
            power_required=power_required.tolist(),
            power_available=propulsion.power_available.tolist(),
            thrust_required=drag_required.tolist(),
            thrust_available=propulsion.thrust_available.tolist(),
            rate_of_climb=derived.rate_of_climb.tolist(),
            climb_angle_deg=derived.climb_angle_deg.tolist(),
            range_km=derived.range_km.tolist(),
            endurance_hours=derived.endurance_hours.tolist(),
            electrical_power=propulsion.electrical_power.tolist(),
            current_draw=propulsion.current_draw.tolist(),
            throttle_pct=propulsion.throttle_pct.tolist(),
            feasible=propulsion.feasible.tolist(),
        )
        notes, propulsion_feasible = self._analysis_notes(
            inputs, aero, stall_speed, propulsion, speeds
        )
        return FlightEnvelopeResult(
            mass_kg=inputs.mass_kg,
            area_m2=aero.area_m2,
            air_density=inputs.rho,
            cl_max=aero.cl_max,
            cd0=aero.cd0,
            k_induced=aero.k_induced,
            battery_capacity_ah=inputs.battery_capacity_ah,
            battery_voltage=inputs.battery_voltage,
            optimal_speeds=speeds.optimal,
            metrics=metrics,
            cruise=cruise,
            curves=curves,
            propulsion_available=propulsion.available,
            propulsion_feasible=propulsion_feasible,
            feasible=bool(not propulsion.available or np.any(propulsion.feasible)),
            notes=notes,
            aero_summary=aero.summary,
            propulsion_summary=propulsion.summary,
        )

    @staticmethod
    def _cruise_performance(
        velocities: np.ndarray,
        propulsion: Any,
        derived: _DerivedCurves,
        speeds: _SpeedSummary,
    ) -> CruisePerformance:
        index = speeds.best_range_index
        if not propulsion.available or index is None:
            return CruisePerformance(feasible=False)
        return CruisePerformance(
            speed=float(velocities[index]),
            power=float(propulsion.electrical_power[index]),
            current=float(propulsion.current_draw[index]),
            throttle=float(propulsion.throttle_pct[index]),
            endurance=float(derived.endurance_hours[index]),
            range=float(derived.range_km[index]),
            feasible=bool(propulsion.feasible[index]),
        )

    @staticmethod
    def _analysis_notes(
        inputs: Any,
        aero: Any,
        stall_speed: float,
        propulsion: Any,
        speeds: _SpeedSummary,
    ) -> tuple[list[str], bool | None]:
        notes: list[str] = []
        if not propulsion.available:
            propulsion_feasible = None
            notes.append("Propulsion data unavailable; aerodynamic-only analysis.")
        elif not np.any(propulsion.feasible):
            propulsion_feasible = False
            notes.append("No feasible level flight operating points found within velocity sweep.")
        else:
            propulsion_feasible = True
        if propulsion.available and speeds.max_speed <= 0.0:
            notes.append("No feasible level-flight speed found within the sweep.")
        elif propulsion.available and not speeds.max_speed_bounded:
            notes.append("Maximum speed is above the sweep limit; increase V_max to bound it.")
        if propulsion.available and speeds.max_speed > 0.0 and stall_speed >= speeds.max_speed:
            notes.append(
                "Stall speed exceeds maximum level flight speed (insufficient thrust/power)."
            )
        if inputs.components and aero.stall_error:
            notes.append(
                f"AeroBuildup CLmax unavailable; stall speed not calculated: {aero.stall_error}"
            )
        elif inputs.components and aero.stall_confirmed is not True:
            notes.append(
                "AeroBuildup CLmax is unconfirmed; extend the alpha sweep before using Vstall."
            )
        return notes, propulsion_feasible
