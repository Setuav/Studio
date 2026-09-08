"""AeroSandbox solver-result normalization and public result assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import (
    AeroAnalysisError,
    AeroForcesMoments,
    AeroResult,
    AnalysisMethod,
    ControlChannelAnalysis,
    FlightCondition,
    MultiDimensionalSweepResult,
    PolarPoint,
    SweepType,
    SweepVariable,
)

if TYPE_CHECKING:
    asb: Any = None
    np: Any = None
else:
    try:
        import aerosandbox as asb
        import aerosandbox.numpy as np
    except ImportError:
        asb = None
        np = None


class AeroSandboxResultMixin:
    """Convert native solver payloads into stable Setuav result models."""

    if TYPE_CHECKING:

        @property
        def name(self) -> str: ...

    def _polar_point_from_result(
        self,
        result: dict[str, Any],
        condition: FlightCondition,
        eval_state: dict[str, Any],
        context: dict[str, Any],
    ) -> PolarPoint:
        coefficients = {
            "cl": float(np.ravel(result["CL"])[0]),
            "cd": float(np.ravel(result["CD"])[0]),
            "cm": self._scalar_result(result, "Cm"),
            "cy": self._scalar_result(result, "CY"),
            "cl_roll": self._scalar_result(result, "Cl"),
            "cn": self._scalar_result(result, "Cn"),
        }
        vectors = {
            name: np.ravel(result.get(name, [0.0, 0.0, 0.0]))
            for name in ("F_b", "F_w", "F_g", "M_b", "M_w", "M_g")
        }
        raw = self._serializable_solver_result(result)
        raw["_sweep_group"] = str(eval_state.get("_sweep_group", ""))
        forces = self._forces_moments(result, vectors, coefficients, context["qs"], raw)
        cd_induced, cd_profile, cd_wave = self._drag_breakdown(result, context["qs"])
        cl = coefficients["cl"]
        cd = coefficients["cd"]
        return PolarPoint(
            alpha=context["alpha"],
            cl=cl,
            cd=cd,
            cm=coefficients["cm"],
            cd_induced=cd_induced,
            cd_profile=cd_profile,
            cl_over_cd=cl / cd if abs(cd) > 1e-7 else 0.0,
            cx=self._coefficient_from_vector(vectors["F_b"], 0, context["qs"]),
            cy=coefficients["cy"],
            cz=self._coefficient_from_vector(vectors["F_b"], 2, context["qs"]),
            cl_roll=coefficients["cl_roll"],
            cn=coefficients["cn"],
            cd_wave=cd_wave,
            beta=context["beta"],
            p=float(condition.p),
            q=float(condition.q),
            r=float(condition.r),
            forces_moments=forces,
            state=context["state"],
            velocity=context["velocity"],
            altitude=context["altitude"],
            mach=context["mach"],
            reynolds=context["reynolds"],
            dynamic_pressure=context["dynamic_pressure"],
            control_deflections=context["controls"],
            converged=True,
            notes="",
            raw=raw,
        )

    @staticmethod
    def _scalar_result(result: dict[str, Any], name: str, default: float = 0.0) -> float:
        return float(np.ravel(result.get(name, default))[0])

    @staticmethod
    def _serializable_solver_result(result: dict[str, Any]) -> dict[str, Any]:
        raw: dict[str, Any] = {}
        for key, value in result.items():
            if isinstance(value, (int, float, np.number)):
                raw[key] = float(value)
            elif isinstance(value, np.ndarray):
                raw[key] = value.tolist()
            elif isinstance(value, (str, bool, list, dict)):
                raw[key] = value
        return raw

    def _forces_moments(
        self,
        result: dict[str, Any],
        vectors: dict[str, Any],
        coefficients: dict[str, float],
        qs: float,
        raw: dict[str, Any],
    ) -> AeroForcesMoments:
        value = self._vector_value
        return AeroForcesMoments(
            fx_b=value(vectors["F_b"], 0),
            fy_b=value(vectors["F_b"], 1),
            fz_b=value(vectors["F_b"], 2),
            fx_w=value(vectors["F_w"], 0),
            fy_w=value(vectors["F_w"], 1),
            fz_w=value(vectors["F_w"], 2),
            lift=self._scalar_result(result, "L", qs * coefficients["cl"]),
            drag=self._scalar_result(result, "D", qs * coefficients["cd"]),
            sideforce=self._scalar_result(result, "Y", qs * coefficients["cy"]),
            fx_g=value(vectors["F_g"], 0),
            fy_g=value(vectors["F_g"], 1),
            fz_g=value(vectors["F_g"], 2),
            mx_b=value(vectors["M_b"], 0),
            my_b=value(vectors["M_b"], 1),
            mz_b=value(vectors["M_b"], 2),
            mx_w=value(vectors["M_w"], 0),
            my_w=value(vectors["M_w"], 1),
            mz_w=value(vectors["M_w"], 2),
            mx_g=value(vectors["M_g"], 0),
            my_g=value(vectors["M_g"], 1),
            mz_g=value(vectors["M_g"], 2),
            raw=raw,
        )

    @staticmethod
    def _vector_value(vector: Any, index: int) -> float:
        return float(vector[index]) if len(vector) > index else 0.0

    @classmethod
    def _coefficient_from_vector(cls, vector: Any, index: int, qs: float) -> float:
        return cls._vector_value(vector, index) / qs if qs > 0 else 0.0

    @classmethod
    def _drag_breakdown(
        cls, result: dict[str, Any], qs: float
    ) -> tuple[float | None, float | None, float | None]:
        induced_force = cls._optional_scalar_result(result, "D_induced")
        profile_force = cls._optional_scalar_result(result, "D_profile")
        wave_force = cls._optional_scalar_result(result, "D_wave")
        induced = cls._optional_drag_coefficient(result, "CDi", induced_force, qs)
        profile = cls._optional_drag_coefficient(result, "CDp", profile_force, qs)
        wave = wave_force / qs if wave_force is not None and qs > 0 else None
        return induced, profile, wave

    @staticmethod
    def _optional_scalar_result(result: dict[str, Any], name: str) -> float | None:
        return float(np.ravel(result[name])[0]) if name in result else None

    @staticmethod
    def _optional_drag_coefficient(
        result: dict[str, Any], name: str, force: float | None, qs: float
    ) -> float | None:
        if name in result:
            return float(np.ravel(result[name])[0])
        return force / qs if force is not None and qs > 0 else None

    @staticmethod
    def _failed_polar_point(context: dict[str, Any], error: Exception) -> PolarPoint:
        return PolarPoint(
            alpha=context["alpha"],
            cl=0.0,
            cd=0.0,
            cm=0.0,
            beta=context["beta"],
            state=context["state"],
            velocity=context["velocity"],
            altitude=context["altitude"],
            mach=context["mach"],
            reynolds=context["reynolds"],
            dynamic_pressure=context["dynamic_pressure"],
            control_deflections=context["controls"],
            converged=False,
            notes=str(error),
        )

    @staticmethod
    def _require_converged_points(
        points: list[PolarPoint], method: AnalysisMethod
    ) -> list[PolarPoint]:
        converged = [point for point in points if point.converged]
        if converged:
            return converged
        failures = list(
            dict.fromkeys(point.notes.strip() for point in points if point.notes.strip())
        )
        details = "; ".join(failures[:3])
        message = f"{method.value} failed at all {len(points)} operating point(s)"
        if details:
            message += f": {details}"
        raise AeroAnalysisError(message)

    @staticmethod
    def _polar_summary(
        points: list[PolarPoint], oswald_values: list[float]
    ) -> dict[str, float | None]:
        best_lift = max(points, key=lambda point: point.cl)
        best_drag = min(points, key=lambda point: point.cd)
        best_efficiency = max(points, key=lambda point: point.cl_over_cd)
        return {
            "cl_max": best_lift.cl,
            "cl_max_alpha": best_lift.alpha,
            "cd_min": best_drag.cd,
            "ld_max": best_efficiency.cl_over_cd,
            "ld_max_alpha": best_efficiency.alpha,
            "oswald": (float(sum(oswald_values) / len(oswald_values)) if oswald_values else None),
        }

    @staticmethod
    def _build_sweep_result(
        condition: FlightCondition,
        eval_states: list[dict[str, Any]],
        primary_values: list[float],
        secondary_values: list[float | None],
        points: list[PolarPoint],
    ) -> MultiDimensionalSweepResult | None:
        if len(eval_states) <= 1 or condition.sweep_type == SweepType.DUAL_ALPHA_BETA:
            return None
        if condition.secondary_variable and len(secondary_values) > 1:
            variables = [
                SweepVariable(
                    name=str(condition.secondary_variable),
                    values=[float(value) for value in secondary_values if value is not None],
                    unit="deg",
                ),
                SweepVariable(
                    name=str(condition.sweep_variable), values=primary_values, unit="deg"
                ),
            ]
            shape = (len(secondary_values), len(primary_values))
        else:
            variables = [
                SweepVariable(name=str(condition.sweep_variable), values=primary_values, unit="deg")
            ]
            shape = (len(primary_values),)
        return MultiDimensionalSweepResult(
            variables=variables, points=list(points), grid_shape=shape
        )

    def _control_analysis(
        self, condition: FlightCondition, points: list[PolarPoint]
    ) -> ControlChannelAnalysis | None:
        if condition.sweep_type != SweepType.CONTROL_DEFLECTION:
            return None
        return self._fit_control_channel_analysis(
            points, str(condition.sweep_variable).strip().lower()
        )

    def _build_aero_result(
        self,
        condition: FlightCondition,
        method: AnalysisMethod,
        setup: dict[str, Any],
        points: list[PolarPoint],
        converged: list[PolarPoint],
        summary: dict[str, float | None],
        sweep_result: MultiDimensionalSweepResult | None,
        control_analysis: ControlChannelAnalysis | None,
        stability: Any | None,
        stability_error: str | None,
    ) -> AeroResult:
        atmosphere = asb.Atmosphere(altitude=max(float(condition.altitude), 0.0))
        density = float(atmosphere.density())
        speed_of_sound = float(atmosphere.speed_of_sound())
        mach = float(condition.velocity) / speed_of_sound if speed_of_sound > 0 else 0.0
        return AeroResult(
            method=method,
            engine_name=self.name,
            polar_points=points,
            cl_max=float(summary["cl_max"] or 0.0),
            cl_max_alpha=float(summary["cl_max_alpha"] or 0.0),
            cd_min=float(summary["cd_min"] or 0.0),
            ld_max=float(summary["ld_max"] or 0.0),
            ld_max_alpha=float(summary["ld_max_alpha"] or 0.0),
            reference=setup["reference"],
            reynolds=points[0].reynolds if points else 0.0,
            mach=mach,
            dynamic_pressure=0.5 * density * float(condition.velocity) ** 2,
            oswald_efficiency=summary["oswald"],
            stability_derivatives=stability,
            sweep_result=sweep_result,
            control_analysis=control_analysis,
            condition=condition,
            propulsion_points=setup["propulsion_points"],
            raw={
                "airplane": setup["airplane"],
                "method": method.value,
                "reference_cg_source": setup["mass_cg_source"],
                "reference_xyz_m": list(setup["reference_xyz"]),
                "velocity": float(condition.velocity),
                "solver_status": {
                    "total_points": len(points),
                    "converged_points": len(converged),
                    "failed_points": len(points) - len(converged),
                    "complete": len(converged) == len(points),
                },
                "stability_status": "available" if stability is not None else "failed",
                "stability_error": stability_error,
            },
        )

    @staticmethod
    def _fit_control_channel_analysis(
        points: list[PolarPoint],
        channel: str,
    ) -> ControlChannelAnalysis | None:
        """Fit coefficient-per-degree effectiveness from converged channel-sweep points."""
        samples = [
            point for point in points if point.converged and channel in point.control_deflections
        ]
        if len(samples) < 2:
            return None

        x_values = [float(point.control_deflections[channel]) for point in samples]
        x_mean = sum(x_values) / len(x_values)
        denominator = sum((value - x_mean) ** 2 for value in x_values)
        if denominator <= 1e-12:
            return None

        coefficient_values = {
            "CL": [float(point.cl) for point in samples],
            "CD": [float(point.cd) for point in samples],
            "Cm": [float(point.cm) for point in samples],
            "CY": [float(point.cy) for point in samples],
            "Cl": [float(point.cl_roll) for point in samples],
            "Cn": [float(point.cn) for point in samples],
        }
        derivatives: dict[str, float] = {}
        linearity: dict[str, float] = {}
        for coefficient, y_values in coefficient_values.items():
            y_mean = sum(y_values) / len(y_values)
            slope = (
                sum(
                    (x_value - x_mean) * (y_value - y_mean)
                    for x_value, y_value in zip(x_values, y_values, strict=True)
                )
                / denominator
            )
            intercept = y_mean - slope * x_mean
            residual = sum(
                (y_value - (intercept + slope * x_value)) ** 2
                for x_value, y_value in zip(x_values, y_values, strict=True)
            )
            total = sum((y_value - y_mean) ** 2 for y_value in y_values)
            derivatives[coefficient] = float(slope)
            linearity[coefficient] = float(
                1.0 if total <= 1e-12 and residual <= 1e-12 else 1.0 - residual / max(total, 1e-12)
            )

        return ControlChannelAnalysis(
            channel=channel,
            sample_count=len(samples),
            deflection_min_deg=min(x_values),
            deflection_max_deg=max(x_values),
            derivatives_per_deg=derivatives,
            linearity_r2=linearity,
        )
