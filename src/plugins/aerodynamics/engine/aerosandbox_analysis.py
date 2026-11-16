"""AeroSandbox analysis orchestration and result conversion."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from setuav_studio.utilities.mass_balance import resolve_aircraft_mass_properties

from .aerosandbox_results import AeroSandboxResultMixin
from .base import (
    AeroResult,
    AeroState,
    AnalysisMethod,
    FlightCondition,
    PolarPoint,
    ReferenceValues,
    SweepType,
    control_channels_for_components,
)
from .stability_engine import StabilityAnalysisEngine

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    asb: Any = None
    np: Any = None
    HAS_AEROSANDBOX = True
else:
    try:
        import aerosandbox as asb
        import aerosandbox.numpy as np

        HAS_AEROSANDBOX = True
    except ImportError:
        HAS_AEROSANDBOX = False
        asb = None
        np = None


class AeroSandboxAnalysisMixin(AeroSandboxResultMixin):
    """Analysis workflow shared by the AeroSandbox engine."""

    if TYPE_CHECKING:

        @property
        def name(self) -> str: ...

        def _build_airplane(
            self,
            components: list[dict[str, Any]],
            condition: FlightCondition | None = None,
            xyz_ref: tuple[float, float, float] | None = None,
            control_encoding: str = "native",
        ) -> Any: ...

        def _compute_reference_geometry(self, airplane: Any) -> tuple[float, float]: ...

    def analyze(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod = AnalysisMethod.AERO_BUILDUP,
        settings: dict[str, Any] | None = None,
        progress_callback: Any | None = None,
        *,
        include_stability: bool = True,
    ) -> AeroResult:
        if not HAS_AEROSANDBOX:
            raise RuntimeError(
                "AeroSandbox library is not installed. Please install it using 'pip install aerosandbox'."
            )

        method = method if isinstance(method, AnalysisMethod) else AnalysisMethod.from_value(method)
        solver_settings = self._solver_settings(method, settings or {})
        setup = self._prepare_analysis(components, condition, solver_settings["control_encoding"])
        self._validate_control_sweep(components, condition)
        sweep_vals, eval_states = self._build_evaluation_states(condition)
        polar_points, oswald_values = self._evaluate_states(
            components,
            condition,
            method,
            solver_settings,
            setup,
            eval_states,
            progress_callback,
        )
        converged_points = self._require_converged_points(polar_points, method)
        summary = self._polar_summary(converged_points, oswald_values)
        sweep_result = self._build_sweep_result(condition, eval_states, sweep_vals, polar_points)
        control_analysis = self._control_analysis(condition, polar_points)
        stability, stability_error = (
            self._compute_stability(
                components,
                condition,
                method,
                setup,
                len(eval_states),
                progress_callback,
            )
            if include_stability
            else (None, None)
        )
        return self._build_aero_result(
            condition,
            method,
            setup,
            polar_points,
            converged_points,
            summary,
            sweep_result,
            control_analysis,
            stability,
            stability_error,
        )

    @staticmethod
    def _solver_settings(method: AnalysisMethod, settings: dict[str, Any]) -> dict[str, Any]:
        span_spacing = str(settings.get("spanwise_spacing", "cosine")).lower()
        chord_spacing = str(settings.get("chordwise_spacing", "cosine")).lower()
        return {
            "span_res": int(settings.get("spanwise_resolution", 12)),
            "chord_res": int(settings.get("chordwise_resolution", 8)),
            "span_spacing": np.cosspace if "cos" in span_spacing else np.linspace,
            "chord_spacing": np.cosspace if "cos" in chord_spacing else np.linspace,
            "include_wave": bool(settings.get("include_wave_drag", True)),
            "control_encoding": "airfoil" if method == AnalysisMethod.VLM else "native",
        }

    def _prepare_analysis(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        control_encoding: str,
    ) -> dict[str, Any]:
        mass_cg, mass_cg_source = self._resolve_mass_cg(components)
        airplane = self._build_airplane(
            components,
            condition=condition,
            xyz_ref=mass_cg,
            control_encoding=control_encoding,
        )
        if not airplane.wings:
            raise ValueError("No valid lifting surfaces found in project for aerodynamic analysis.")
        span, area = self._compute_reference_geometry(airplane)
        mean_chord = area / span if span > 0 else 0.0
        reference_xyz = mass_cg or tuple(float(value) for value in airplane.xyz_ref)
        return {
            "mass_cg": mass_cg,
            "mass_cg_source": mass_cg_source,
            "airplane": airplane,
            "mean_chord": mean_chord,
            "ref_area": area if area > 0 else 1.0,
            "reference_xyz": reference_xyz,
            "reference": ReferenceValues(
                s_ref=area,
                b_ref=span,
                c_ref=mean_chord,
                x_cg=float(reference_xyz[0]),
                y_cg=float(reference_xyz[1]),
                z_cg=float(reference_xyz[2]),
            ),
        }

    @staticmethod
    def _validate_control_sweep(
        components: list[dict[str, Any]], condition: FlightCondition
    ) -> None:
        if condition.sweep_type != SweepType.CONTROL_DEFLECTION:
            return
        channel = str(condition.sweep_variable).strip().lower()
        if channel not in control_channels_for_components(components):
            raise ValueError(
                f"Control channel '{channel}' is not provided by the aircraft geometry"
            )

    def _build_evaluation_states(
        self, condition: FlightCondition
    ) -> tuple[list[float], list[dict[str, Any]]]:
        sweep_vals = condition.sweep_values()
        states = [self._evaluation_state(condition, sweep_val) for sweep_val in sweep_vals]
        return sweep_vals, states

    @staticmethod
    def _base_evaluation_state(condition: FlightCondition) -> dict[str, Any]:
        return {
            "alpha": float(condition.alpha),
            "beta": float(condition.beta),
            "velocity": float(condition.velocity),
            "altitude": float(condition.altitude),
            "controls": dict(condition.control_deflections),
        }

    def _evaluation_state(
        self,
        condition: FlightCondition,
        sweep_val: float,
    ) -> dict[str, Any]:
        state = self._base_evaluation_state(condition)
        state["sweep_val"] = float(sweep_val)
        self._apply_sweep_value(state, condition.sweep_variable, float(sweep_val))
        return state

    @staticmethod
    def _apply_sweep_value(state: dict[str, Any], variable: str, value: float) -> None:
        if variable == "alpha":
            state["alpha"] = value
        elif variable == "beta":
            state["beta"] = value
        else:
            state["controls"][variable] = value

    def _evaluate_states(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod,
        solver_settings: dict[str, Any],
        setup: dict[str, Any],
        eval_states: list[dict[str, Any]],
        progress_callback: Any | None,
    ) -> tuple[list[PolarPoint], list[float]]:
        points: list[PolarPoint] = []
        oswald_values: list[float] = []
        total_steps = len(eval_states) + 1
        for index, eval_state in enumerate(eval_states, start=1):
            point, oswald = self._evaluate_state(
                components,
                condition,
                method,
                solver_settings,
                setup,
                eval_state,
                index,
                total_steps,
                progress_callback,
            )
            points.append(point)
            if oswald is not None:
                oswald_values.append(oswald)
        return points, oswald_values

    def _evaluate_state(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod,
        solver_settings: dict[str, Any],
        setup: dict[str, Any],
        eval_state: dict[str, Any],
        index: int,
        total_steps: int,
        progress_callback: Any | None,
    ) -> tuple[PolarPoint, float | None]:
        point_context = self._point_context(
            components, condition, solver_settings, setup, eval_state
        )
        if progress_callback:
            progress_callback(
                index,
                total_steps,
                self._progress_message(condition, eval_state, point_context, index, total_steps),
            )
        try:
            result = self._run_solver(
                method, point_context["airplane"], point_context["op"], solver_settings
            )
            point = self._polar_point_from_result(result, condition, eval_state, point_context)
            wing_components = result.get("wing_aero_components", [])
            oswald = float(wing_components[0].oswalds_efficiency) if wing_components else None
            return point, oswald
        except Exception as err:
            logger.warning(
                "Solver %s failed for point alpha=%.1f, beta=%.1f: %s",
                method.value,
                point_context["alpha"],
                point_context["beta"],
                err,
            )
            return self._failed_polar_point(point_context, err), None

    def _point_context(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        solver_settings: dict[str, Any],
        setup: dict[str, Any],
        eval_state: dict[str, Any],
    ) -> dict[str, Any]:
        alpha = float(eval_state["alpha"])
        beta = float(eval_state["beta"])
        velocity = max(float(eval_state["velocity"]), 0.1)
        altitude = max(float(eval_state["altitude"]), 0.0)
        controls = dict(eval_state["controls"])
        point_condition = FlightCondition(
            velocity=velocity,
            altitude=altitude,
            alpha=alpha,
            beta=beta,
            p=float(condition.p),
            q=float(condition.q),
            r=float(condition.r),
            control_deflections=controls,
        )
        airplane = setup["airplane"]
        if controls != condition.control_deflections:
            airplane = self._build_airplane(
                components,
                condition=point_condition,
                xyz_ref=setup["mass_cg"],
                control_encoding=solver_settings["control_encoding"],
            )
        atmosphere = asb.Atmosphere(altitude=altitude)
        density = float(atmosphere.density())
        viscosity = float(atmosphere.dynamic_viscosity())
        speed_of_sound = float(atmosphere.speed_of_sound())
        mach = velocity / speed_of_sound if speed_of_sound > 0 else 0.0
        dynamic_pressure = 0.5 * density * velocity**2
        reynolds = density * velocity * setup["mean_chord"] / viscosity if viscosity > 0 else 0.0
        op = asb.OperatingPoint(
            atmosphere=atmosphere,
            velocity=velocity,
            alpha=alpha,
            beta=beta,
            p=float(condition.p),
            q=float(condition.q),
            r=float(condition.r),
        )
        state = AeroState(
            alpha=alpha,
            beta=beta,
            p=float(condition.p),
            q=float(condition.q),
            r=float(condition.r),
            velocity=velocity,
            altitude=altitude,
            mach=mach,
            reynolds=reynolds,
            dynamic_pressure=dynamic_pressure,
            control_deflections=controls,
        )
        return {
            "alpha": alpha,
            "beta": beta,
            "velocity": velocity,
            "altitude": altitude,
            "controls": controls,
            "airplane": airplane,
            "op": op,
            "state": state,
            "mach": mach,
            "reynolds": reynolds,
            "dynamic_pressure": dynamic_pressure,
            "qs": dynamic_pressure * setup["ref_area"],
        }

    @staticmethod
    def _progress_message(
        condition: FlightCondition,
        eval_state: dict[str, Any],
        context: dict[str, Any],
        index: int,
        total_steps: int,
    ) -> str:
        if condition.sweep_type == SweepType.ALPHA:
            return f"α={context['alpha']:.1f}°"
        if condition.sweep_type == SweepType.BETA:
            return f"β={context['beta']:.1f}°"
        if condition.sweep_type == SweepType.CONTROL_DEFLECTION:
            return f"{condition.sweep_variable}={eval_state['sweep_val']:.1f}°"
        return f"Step {index}/{total_steps}"

    @staticmethod
    def _run_solver(
        method: AnalysisMethod,
        airplane: Any,
        operating_point: Any,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        if method == AnalysisMethod.VLM:
            solver = asb.VortexLatticeMethod(
                airplane=airplane,
                op_point=operating_point,
                spanwise_resolution=settings["span_res"],
                chordwise_resolution=settings["chord_res"],
                spanwise_spacing_function=settings["span_spacing"],
                chordwise_spacing_function=settings["chord_spacing"],
            )
        elif method == AnalysisMethod.LIFTING_LINE:
            solver = asb.LiftingLine(
                airplane=airplane,
                op_point=operating_point,
                spanwise_resolution=settings["span_res"],
                spanwise_spacing_function=settings["span_spacing"],
            )
        else:
            solver = asb.AeroBuildup(
                airplane=airplane,
                op_point=operating_point,
                include_wave_drag=settings["include_wave"],
            )
        return solver.run()

    def _compute_stability(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod,
        setup: dict[str, Any],
        point_count: int,
        progress_callback: Any | None,
    ) -> tuple[Any | None, str | None]:
        total_steps = point_count + 1
        if progress_callback:
            progress_callback(point_count, total_steps, "Stability")
        try:
            stability = StabilityAnalysisEngine().compute_stability(
                airplane=setup["airplane"],
                condition=condition,
                ref=setup["reference"],
                components=components,
                builder_fn=lambda comps, cond: self._build_airplane(
                    comps,
                    condition=cond,
                    xyz_ref=setup["mass_cg"],
                    control_encoding="airfoil" if method == AnalysisMethod.VLM else "native",
                ),
                method=method,
                cg_source=setup["mass_cg_source"],
            )
            error = None
        except Exception as err:
            logger.warning("Stability derivatives computation failed: %s", err)
            stability = None
            error = str(err)
        if progress_callback:
            progress_callback(total_steps, total_steps, "Done")
        return stability, error

    @staticmethod
    def _resolve_mass_cg(
        components: list[dict[str, Any]],
    ) -> tuple[tuple[float, float, float] | None, str]:
        """Resolve the aircraft CG from the core mass-balance model.

        A massless aircraft has no CG, so the aerodynamic reference point is used instead.
        """
        mass_props = resolve_aircraft_mass_properties(components)
        if mass_props.mass_kg <= 0.0:
            return None, "aerodynamic_reference"
        cg_x, cg_y, cg_z = mass_props.cg_body_m
        return (float(cg_x), float(cg_y), float(cg_z)), "mass_balance"
