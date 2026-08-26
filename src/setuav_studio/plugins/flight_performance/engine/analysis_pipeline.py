"""Staged flight-performance analysis pipeline."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from pythrust.propellers.database import PropellerEntry
from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec

from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import (
    AeroSandboxEngine,
    AnalysisMethod,
    FlightCondition,
)
from setuav_studio.plugins.electrical_propulsion.engine.solver import PropulsionSolverEngine
from setuav_studio.plugins.weight_balance.engine.solver import WeightBalanceSolver

from .analysis_results import FlightPerformanceResultBuilder
from .models import FlightEnvelopeResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class _AnalysisInputs:
    context: dict[str, Any]
    mass_kg: float
    area_m2: float
    rho: float
    cl_max: float
    cd_min: float
    ld_max: float
    v_min: float
    v_max: float
    v_step: float
    stall_margin: float
    battery_capacity_ah: float | None
    battery_voltage: float | None
    usable_battery_ratio: float
    motor_spec: MotorSpec | None
    prop_spec: PropellerSpec | None
    prop_entry: PropellerEntry | None
    components: Any
    polar_cl: Any
    polar_cd: Any
    polar_alpha: Any


@dataclass
class _AerodynamicModel:
    area_m2: float
    cl_max: float
    cd_min: float
    ld_max: float
    polar_cl: np.ndarray | None
    polar_cd: np.ndarray | None
    cd0: float
    k_induced: float
    stall_confirmed: bool | None
    stall_error: str | None
    summary: dict[str, Any]


@dataclass
class _PropulsionGrid:
    available: bool
    power_available: np.ndarray
    thrust_available: np.ndarray
    electrical_power: np.ndarray
    current_draw: np.ndarray
    throttle_pct: np.ndarray
    feasible: np.ndarray
    summary: dict[str, Any]


class FlightPerformanceAnalysisPipeline:
    """Execute flight-performance stages while preserving the solver API."""

    def __init__(
        self,
        solver: type[Any],
        context: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        self.solver = solver
        self.context = context
        self.progress_callback = progress_callback

    def run(self) -> FlightEnvelopeResult:
        inputs = self._resolve_inputs()
        aero = self._resolve_aerodynamic_model(inputs)
        self._progress(30, "Grid")
        velocities, stall_speed = self._build_velocity_grid(inputs, aero)
        power_required, drag_required, _ = self.solver.compute_power_and_drag_required(
            velocities=velocities,
            mass_kg=inputs.mass_kg,
            area_m2=aero.area_m2,
            rho=inputs.rho,
            polar_cl=aero.polar_cl,
            polar_cd=aero.polar_cd,
            cd0=aero.cd0,
            k_induced=aero.k_induced,
            default_cd=aero.cd_min,
        )
        propulsion = self._solve_propulsion_grid(inputs, velocities, drag_required)
        self._progress(90, "Speeds")
        result = FlightPerformanceResultBuilder(self.solver).build(
            inputs,
            aero,
            velocities,
            stall_speed,
            power_required,
            drag_required,
            propulsion,
        )
        self._progress(100, "Done")
        return result

    def _resolve_inputs(self) -> _AnalysisInputs:
        context = self.context
        capacity_mah = context.get("battery_capacity_mah")
        voltage = context.get("battery_voltage")
        return _AnalysisInputs(
            context=context,
            mass_kg=self._resolve_mass(context),
            area_m2=float(context.get("area_m2", 0.0)),
            rho=float(context.get("air_density", 1.225)),
            cl_max=float(context.get("cl_max", 0.0)),
            cd_min=float(context.get("cd_min", 0.0)),
            ld_max=float(context.get("ld_max", 0.0)),
            v_min=float(context.get("v_min", 8.0)),
            v_max=float(context.get("v_max", 35.0)),
            v_step=float(context.get("v_step", 0.25)),
            stall_margin=float(context.get("stall_margin", 1.15)),
            battery_capacity_ah=(
                float(capacity_mah) / 1000.0 if capacity_mah is not None else None
            ),
            battery_voltage=float(voltage) if voltage is not None else None,
            usable_battery_ratio=float(context.get("usable_battery_ratio", 0.85)),
            motor_spec=context.get("motor_spec"),
            prop_spec=context.get("prop_spec"),
            prop_entry=context.get("prop_entry"),
            components=context.get("components"),
            polar_cl=context.get("polar_cl"),
            polar_cd=context.get("polar_cd"),
            polar_alpha=context.get("polar_alpha"),
        )

    @staticmethod
    def _resolve_mass(context: dict[str, Any]) -> float:
        mass_kg = float(context.get("mass_kg", 0.0))
        project = context.get("project")
        if mass_kg <= 0.0 and project is not None:
            try:
                mass_kg = float(WeightBalanceSolver().evaluate(project).total.mass_kg)
            except Exception as exc:
                logger.debug("WeightBalance evaluate failed; trying component mass sum: %s", exc)
            if mass_kg <= 0.0:
                components = project.data.get("components", [])
                mass_kg = (
                    sum(
                        float(component.get("parameters", {}).get("mass", 0.0))
                        for component in components
                        if isinstance(component, dict)
                    )
                    / 1000.0
                )
        if mass_kg <= 0.0:
            raise ValueError(
                "Mass properties are unavailable. Define component masses or run Weight Balance before analysis."
            )
        return mass_kg

    def _resolve_aerodynamic_model(self, inputs: _AnalysisInputs) -> _AerodynamicModel:
        area = inputs.area_m2
        cl_max = inputs.cl_max
        cd_min = inputs.cd_min
        ld_max = inputs.ld_max
        polar_cl = inputs.polar_cl
        polar_cd = inputs.polar_cd
        polar_alpha = inputs.polar_alpha
        summary: dict[str, Any] = {}
        stall_confirmed: bool | None = None
        stall_error: str | None = None
        if inputs.components and AeroSandboxEngine().is_available():
            (
                area,
                cl_max,
                cd_min,
                ld_max,
                polar_cl,
                polar_cd,
                polar_alpha,
                summary,
                stall_confirmed,
                stall_error,
            ) = self._run_aerobuildup(inputs, area, cl_max, cd_min, ld_max)
        elif inputs.components:
            stall_error = "AeroSandbox/AeroBuildup is unavailable."
        area, cl_max, cd_min, ld_max = self._aero_defaults(
            inputs.components, area, cl_max, cd_min, ld_max
        )
        polar_cl_array = np.array(polar_cl, dtype=float) if polar_cl else None
        polar_cd_array = np.array(polar_cd, dtype=float) if polar_cd else None
        cd0, k_induced = self._fit_drag_model(
            inputs,
            summary,
            polar_cl_array,
            polar_cd_array,
            polar_alpha,
            cd_min,
        )
        return _AerodynamicModel(
            area_m2=area,
            cl_max=cl_max,
            cd_min=cd_min,
            ld_max=ld_max,
            polar_cl=polar_cl_array,
            polar_cd=polar_cd_array,
            cd0=cd0,
            k_induced=k_induced,
            stall_confirmed=stall_confirmed,
            stall_error=stall_error,
            summary=summary,
        )

    def _run_aerobuildup(
        self,
        inputs: _AnalysisInputs,
        area: float,
        cl_max: float,
        cd_min: float,
        ld_max: float,
    ) -> tuple[Any, ...]:
        self._progress(10, "Aero Polar")
        polar_cl = inputs.polar_cl
        polar_cd = inputs.polar_cd
        polar_alpha = inputs.polar_alpha
        summary: dict[str, Any] = {}
        stall_confirmed: bool | None = None
        try:
            condition = FlightCondition(
                velocity=15.0,
                altitude=float(inputs.context.get("altitude", 0.0)),
                alpha_min=-8.0,
                alpha_max=25.0,
                alpha_steps=67,
                sweep_min=-8.0,
                sweep_max=25.0,
                sweep_steps=67,
            )
            result = AeroSandboxEngine().analyze(
                components=inputs.components,
                condition=condition,
                method=AnalysisMethod.AERO_BUILDUP,
            )
            if result.polar_points:
                valid_polar = [point for point in result.polar_points if point.converged]
                polar_cl = [point.cl for point in valid_polar]
                polar_cd = [point.cd for point in valid_polar]
                polar_alpha = [point.alpha for point in valid_polar]
                cl_max, cl_max_alpha, stall_confirmed = self.solver._resolve_aerobuildup_clmax(
                    result.polar_points
                )
                area = float(result.reference.s_ref) if result.reference.s_ref > 0 else area
                cd_min = float(result.cd_min) if result.cd_min > 0 else cd_min
                ld_max = float(result.ld_max) if result.ld_max > 0 else ld_max
                summary = {
                    "method": "AeroBuildup",
                    "cl_max": cl_max,
                    "cl_max_alpha": cl_max_alpha,
                    "cl_max_confirmed": stall_confirmed,
                    "cd_min": cd_min,
                    "ld_max": ld_max,
                    "s_ref": area,
                    "points_count": len(polar_cl),
                }
            stall_error = None
        except Exception as exc:
            stall_error = str(exc)
            logger.warning("Auto AeroSandbox analysis failed: %s", exc)
        return (
            area,
            cl_max,
            cd_min,
            ld_max,
            polar_cl,
            polar_cd,
            polar_alpha,
            summary,
            stall_confirmed,
            stall_error,
        )

    @staticmethod
    def _aero_defaults(
        components: Any,
        area: float,
        cl_max: float,
        cd_min: float,
        ld_max: float,
    ) -> tuple[float, float, float, float]:
        area = area if area > 0.0 else 0.50
        if cl_max <= 0.0 and not components:
            cl_max = 1.20
        cd_min = cd_min if cd_min > 0.0 else 0.035
        ld_max = ld_max if ld_max > 0.0 else 12.0
        return area, cl_max, cd_min, ld_max

    def _fit_drag_model(
        self,
        inputs: _AnalysisInputs,
        summary: dict[str, Any],
        polar_cl: np.ndarray | None,
        polar_cd: np.ndarray | None,
        polar_alpha: Any,
        cd_min: float,
    ) -> tuple[float, float]:
        cd0 = k_induced = None
        if polar_cl is not None and polar_cd is not None and len(polar_cl) >= 3:
            alpha_max = (
                float(summary["cl_max_alpha"]) if summary.get("method") == "AeroBuildup" else None
            )
            cd0, k_induced = self.solver.fit_parabolic_cd(
                polar_cl.tolist(),
                polar_cd.tolist(),
                alpha_values=polar_alpha,
                alpha_max=alpha_max,
            )
        if cd0 is None or k_induced is None:
            cd0 = cd_min
            aspect_ratio = float(inputs.context.get("aspect_ratio", 8.0))
            oswald = float(inputs.context.get("oswald_efficiency", 0.8))
            k_induced = 1.0 / (math.pi * aspect_ratio * oswald)
        return cd0, k_induced

    def _build_velocity_grid(
        self, inputs: _AnalysisInputs, aero: _AerodynamicModel
    ) -> tuple[np.ndarray, float]:
        stall_cl_max = aero.cl_max
        if inputs.components and (aero.stall_confirmed is not True or aero.cl_max <= 0.0):
            stall_cl_max = 0.0
        stall_speed = self.solver.compute_stall_speed(
            inputs.mass_kg, aero.area_m2, stall_cl_max, inputs.rho
        )
        start = max(stall_speed * inputs.stall_margin, inputs.v_min)
        end = max(start + 2.0, inputs.v_max)
        values: list[float] = []
        velocity = start
        while velocity <= end + 1e-4:
            values.append(velocity)
            velocity += inputs.v_step
        if len(values) < 5:
            values = np.linspace(start, end, 25).tolist()
        return np.array(values, dtype=float), stall_speed

    def _solve_propulsion_grid(
        self,
        inputs: _AnalysisInputs,
        velocities: np.ndarray,
        drag_required: np.ndarray,
    ) -> _PropulsionGrid:
        available = self._has_propulsion(inputs)
        count = len(velocities)
        power = np.zeros(count) if available else np.array([])
        thrust = np.zeros(count) if available else np.array([])
        electrical = np.zeros(count) if available else np.array([])
        current = np.zeros(count) if available else np.array([])
        throttle = np.zeros(count) if available else np.array([])
        feasible = np.ones(count, dtype=bool)
        for index, velocity in enumerate(velocities):
            if count > 0:
                self._progress(int(40 + 45 * (index / count)), f"{velocity:.1f} m/s")
            if available:
                self._solve_propulsion_point(
                    inputs,
                    float(velocity),
                    float(drag_required[index]),
                    index,
                    power,
                    thrust,
                    electrical,
                    current,
                    throttle,
                    feasible,
                )
        return _PropulsionGrid(
            available=available,
            power_available=power,
            thrust_available=thrust,
            electrical_power=electrical,
            current_draw=current,
            throttle_pct=throttle,
            feasible=feasible,
            summary=self._propulsion_summary(inputs, available),
        )

    @staticmethod
    def _has_propulsion(inputs: _AnalysisInputs) -> bool:
        motor = inputs.motor_spec
        propeller = inputs.prop_spec
        pitch = propeller.pitch_m if propeller else None
        return bool(
            motor is not None
            and propeller is not None
            and inputs.prop_entry is not None
            and inputs.battery_voltage is not None
            and inputs.battery_voltage > 0.0
            and motor.kv_rpm_per_v > 0.0
            and motor.current_max_a > 0.0
            and propeller.diameter_m > 0.0
            and pitch is not None
            and pitch > 0.0
        )

    def _solve_propulsion_point(
        self,
        inputs: _AnalysisInputs,
        velocity: float,
        drag_required: float,
        index: int,
        power: np.ndarray,
        thrust: np.ndarray,
        electrical: np.ndarray,
        current: np.ndarray,
        throttle: np.ndarray,
        feasible: np.ndarray,
    ) -> None:
        motor = inputs.motor_spec
        propeller = inputs.prop_spec
        entry = inputs.prop_entry
        voltage = inputs.battery_voltage
        if motor is None or propeller is None or entry is None or voltage is None:
            return
        safe_throttle = self.solver._safe_max_throttle(
            motor_spec=motor,
            prop_spec=propeller,
            prop_entry=entry,
            total_voltage=voltage,
            rho=inputs.rho,
            v_mps=velocity,
        )
        if safe_throttle > 0.0:
            maximum = PropulsionSolverEngine.solve_point(
                motor_spec=motor,
                prop_spec=propeller,
                prop_entry=entry,
                total_voltage=voltage,
                rho=inputs.rho,
                v_mps=velocity,
                throttle_val=safe_throttle,
                x_val=velocity,
            )
            thrust[index] = maximum.thrust
            power[index] = maximum.thrust * velocity
        required_throttle, electric_power, amperage, point_feasible = (
            self.solver.solve_propulsion_for_thrust(
                motor_spec=motor,
                prop_spec=propeller,
                prop_entry=entry,
                total_voltage=voltage,
                rho=inputs.rho,
                v_mps=velocity,
                thrust_req=drag_required,
            )
        )
        throttle[index] = required_throttle
        electrical[index] = electric_power
        current[index] = amperage
        feasible[index] = safe_throttle > 0.0 and point_feasible and thrust[index] >= drag_required

    @staticmethod
    def _propulsion_summary(inputs: _AnalysisInputs, available: bool) -> dict[str, Any]:
        motor = inputs.motor_spec
        propeller = inputs.prop_spec
        pitch = propeller.pitch_m if propeller else None
        return {
            "has_propulsion": available,
            "motor_kv": motor.kv_rpm_per_v if motor else None,
            "motor_max_current": motor.current_max_a if motor else None,
            "prop_diameter_in": propeller.diameter_m / 0.0254 if propeller else None,
            "prop_pitch_in": pitch / 0.0254 if pitch is not None else None,
            "battery_voltage": inputs.battery_voltage,
            "battery_capacity_ah": inputs.battery_capacity_ah,
        }

    def _progress(self, value: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(value, 100, message)
