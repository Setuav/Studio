"""Linear stability and trim analysis engine for 6-DoF flight dynamics."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

try:
    import aerosandbox as asb

    HAS_AEROSANDBOX = True
except ImportError:
    HAS_AEROSANDBOX = False

from .base import (
    AnalysisMethod,
    FlightCondition,
    ReferenceValues,
    control_channels_for_components,
)
from .stability_models import (
    ControlEffectiveness,
    ElevatorTrim,
    StabilityDerivatives,
)

logger = logging.getLogger(__name__)


class StabilityAnalysisEngine:
    """Computes longitudinal and lateral-directional stability derivatives, neutral point, and trim."""

    _MIN_PITCH_DERIVATIVE_PER_DEG = 1e-4
    _MIN_ELEVATOR_AUTHORITY_PER_DEG = 1e-4
    _MAX_TRIM_DEFLECTION_DEG = 45.0

    def compute_stability(
        self,
        airplane: Any,
        condition: FlightCondition,
        ref: ReferenceValues,
        components: list[dict[str, Any]] | None = None,
        builder_fn: Any | None = None,
        method: AnalysisMethod = AnalysisMethod.VLM,
        cg_source: str = "unknown",
    ) -> StabilityDerivatives:
        """Compute full 6-DoF linear stability derivatives and trim equilibrium.

        Args:
            airplane: Base asb.Airplane instance.
            condition: FlightCondition defining flight velocity, altitude, and reference angles.
            ref: ReferenceValues for aerodynamic normalization (s_ref, b_ref, c_ref, x_cg).
            components: Optional raw component tree for control surface perturbation.
            builder_fn: Optional callable `fn(components, condition)` to rebuild modified airplane.

        Returns:
            StabilityDerivatives object with all aerodynamic derivatives and trim solution.
        """
        if not HAS_AEROSANDBOX:
            raise RuntimeError("AeroSandbox is required for stability analysis.")

        vel = max(float(condition.velocity), 0.1)
        alt = max(float(condition.altitude), 0.0)
        ref_a = float(condition.alpha)
        ref_b = float(condition.beta)

        atmosphere = asb.Atmosphere(altitude=alt)
        c_ref = max(float(ref.c_ref), 1e-4)
        x_cg = float(ref.x_cg)
        # Baseline operating point
        op_base = asb.OperatingPoint(
            atmosphere=atmosphere,
            velocity=vel,
            alpha=ref_a,
            beta=ref_b,
        )

        # Native AeroSandbox stability derivatives run
        solver_cls = {
            AnalysisMethod.VLM: asb.VortexLatticeMethod,
            AnalysisMethod.LIFTING_LINE: asb.LiftingLine,
            AnalysisMethod.AERO_BUILDUP: asb.AeroBuildup,
        }.get(method, asb.AeroBuildup)
        analysis = solver_cls(airplane=airplane, op_point=op_base)
        try:
            res = analysis.run_with_stability_derivatives()
        except Exception as err:
            raise RuntimeError(
                f"{method.value} native stability derivatives failed: {err}"
            ) from err

        def scalar(key: str) -> float:
            if key not in res or res[key] is None:
                raise RuntimeError(f"{method.value} did not return native stability field '{key}'")
            value = float(np.ravel(res[key])[0])
            if not math.isfinite(value):
                raise RuntimeError(f"{method.value} returned non-finite stability field '{key}'")
            return value

        cl_0 = scalar("CL")
        cm_0 = scalar("Cm")

        cla_rad = scalar("CLa")
        cda_rad = scalar("CDa")
        cma_rad = scalar("Cma")
        cla_deg = cla_rad * (math.pi / 180.0)
        cma_deg = cma_rad * (math.pi / 180.0)

        cl_q = scalar("CLq")
        cm_q = scalar("Cmq")

        cyb_rad = scalar("CYb")
        clb_rad = scalar("Clb")
        cnb_rad = scalar("Cnb")
        cyb_deg = cyb_rad * (math.pi / 180.0)
        clb_deg = clb_rad * (math.pi / 180.0)
        cnb_deg = cnb_rad * (math.pi / 180.0)

        cl_p = scalar("Clp")
        cn_p = scalar("Cnp")
        cl_r = scalar("Clr")
        cn_r = scalar("Cnr")

        # Neutral Point & Static Margin
        if "x_np" in res and res["x_np"] is not None and not np.isnan(np.ravel(res["x_np"])[0]):
            x_np = float(np.ravel(res["x_np"])[0])
            static_margin_pct = ((x_np - x_cg) / c_ref) * 100.0
        elif abs(cla_rad) > 1e-4:
            sm = -float(cma_rad / cla_rad)
            x_np = x_cg + sm * c_ref
            static_margin_pct = sm * 100.0
        else:
            x_np = x_cg
            static_margin_pct = 0.0

        # 7. Control Effectiveness & Elevator Trim
        # 7. 3-Axis Aerodynamic Control Effectiveness (Elevator, Aileron, Rudder)
        controls_map: dict[str, ControlEffectiveness] = {}
        elevator_trim: ElevatorTrim | None = None
        trim_invalid_reasons: tuple[str, ...] = ()

        if components and builder_fn:
            # Analyze canonical pilot channels. Individual surface tags are
            # geometry details and must not become separate control analyses.
            for ctrl_tag in control_channels_for_components(components):
                d_delta = 2.0  # deg
                controls_p = dict(condition.control_deflections)
                controls_m = dict(condition.control_deflections)
                base_delta = float(condition.control_deflections.get(ctrl_tag, 0.0))
                controls_p[ctrl_tag] = base_delta + d_delta
                controls_m[ctrl_tag] = base_delta - d_delta
                cond_p = FlightCondition(
                    velocity=vel,
                    altitude=alt,
                    alpha=ref_a,
                    beta=ref_b,
                    control_deflections=controls_p,
                )
                cond_m = FlightCondition(
                    velocity=vel,
                    altitude=alt,
                    alpha=ref_a,
                    beta=ref_b,
                    control_deflections=controls_m,
                )

                try:
                    plane_p = builder_fn(components, cond_p)
                    plane_m = builder_fn(components, cond_m)
                    res_c_p = solver_cls(airplane=plane_p, op_point=op_base).run()
                    res_c_m = solver_cls(airplane=plane_m, op_point=op_base).run()

                    def delta(key: str) -> float:
                        if key not in res_c_p or key not in res_c_m:
                            raise RuntimeError(
                                f"control perturbation did not return native field '{key}'"
                            )
                        value = float(np.ravel(res_c_p[key] - res_c_m[key])[0]) / (2.0 * d_delta)
                        if not math.isfinite(value):
                            raise RuntimeError(
                                f"control perturbation returned non-finite field '{key}'"
                            )
                        return value

                    cl_delta = delta("Cl")
                    cm_delta = delta("Cm")
                    cn_delta = delta("Cn")
                    cy_delta = delta("CY")
                    cL_delta = delta("CL")
                    cD_delta = delta("CD")

                    # Only register if the control channel produces a non-zero response
                    if any(
                        abs(v) > 1e-5 for v in (cl_delta, cm_delta, cn_delta, cy_delta, cL_delta)
                    ):
                        controls_map[ctrl_tag] = ControlEffectiveness(
                            control_tag=ctrl_tag,
                            c_l_delta=cl_delta,
                            c_m_delta=cm_delta,
                            c_n_delta=cn_delta,
                            c_y_delta=cy_delta,
                            c_L_delta=cL_delta,
                            c_D_delta=cD_delta,
                            derivative_method="finite_difference",
                            perturbation_deg=d_delta,
                        )

                except Exception as err:
                    logger.debug("Control channel %s evaluation skipped: %s", ctrl_tag, err)

        elevator_trim, trim_invalid_reasons = self._validated_elevator_trim(
            cg_source=cg_source,
            cg_xyz=(float(ref.x_cg), float(ref.y_cg), float(ref.z_cg)),
            alpha_ref=ref_a,
            cl_ref=cl_0,
            cm_ref=cm_0,
            cm_alpha_per_deg=cma_deg,
            elevator=controls_map.get("elevator"),
        )

        return StabilityDerivatives(
            c_L_alpha_rad=cla_rad,
            c_L_alpha_deg=cla_deg,
            c_D_alpha_rad=cda_rad,
            c_D_alpha_deg=cda_rad * (math.pi / 180.0),
            c_m_alpha_rad=cma_rad,
            c_m_alpha_deg=cma_deg,
            c_L_q=cl_q,
            c_m_q=cm_q,
            c_Y_beta_rad=cyb_rad,
            c_Y_beta_deg=cyb_deg,
            c_l_beta_rad=clb_rad,
            c_l_beta_deg=clb_deg,
            c_n_beta_rad=cnb_rad,
            c_n_beta_deg=cnb_deg,
            c_l_p=cl_p,
            c_n_p=cn_p,
            c_l_r=cl_r,
            c_n_r=cn_r,
            x_cg=x_cg,
            x_np=x_np,
            static_margin=static_margin_pct,
            is_pitch_stable=(cma_rad < 0 and static_margin_pct > 0.0),
            is_pitch_damped=(cm_q < 0),
            is_roll_stable=(clb_rad < 0),
            is_roll_damped=(cl_p < 0),
            is_yaw_stable=(cnb_rad > 0),
            is_yaw_damped=(cn_r < 0),
            controls=controls_map,
            elevator_trim=elevator_trim,
            trim_valid=elevator_trim is not None,
            trim_invalid_reasons=trim_invalid_reasons,
            solver_method=method.value,
            rate_derivative_convention="normalized_body_rates",
        )

    @classmethod
    def _validated_elevator_trim(
        cls,
        *,
        cg_source: str,
        cg_xyz: tuple[float, float, float],
        alpha_ref: float,
        cl_ref: float,
        cm_ref: float,
        cm_alpha_per_deg: float,
        elevator: ControlEffectiveness | None,
    ) -> tuple[ElevatorTrim | None, tuple[str, ...]]:
        """Return a linear elevator trim only when its inputs and authority are usable."""
        reasons: list[str] = []
        if cg_source == "weight_balance_incomplete":
            reasons.append("Weight-Balance CG excludes components with missing mass")
        elif cg_source != "weight_balance":
            reasons.append("CG is unavailable from Weight-Balance")
        if not all(math.isfinite(value) for value in cg_xyz):
            reasons.append("CG contains non-finite coordinates")
        if (
            not math.isfinite(cm_alpha_per_deg)
            or abs(cm_alpha_per_deg) < cls._MIN_PITCH_DERIVATIVE_PER_DEG
        ):
            reasons.append("pitch derivative Cm_alpha is unavailable or too small")
        if elevator is None or not math.isfinite(elevator.c_m_delta):
            reasons.append("elevator control authority is unavailable")
        elif abs(elevator.c_m_delta) < cls._MIN_ELEVATOR_AUTHORITY_PER_DEG:
            reasons.append("elevator pitch authority Cm_delta_e is too small")

        if reasons:
            return None, tuple(reasons)

        assert elevator is not None
        cm_zero_alpha = cm_ref - cm_alpha_per_deg * alpha_ref
        delta_e_trim = -cm_ref / elevator.c_m_delta
        alpha_trim_neutral = -cm_zero_alpha / cm_alpha_per_deg
        cl_trim = cl_ref + elevator.c_L_delta * delta_e_trim
        values = (cm_zero_alpha, delta_e_trim, alpha_trim_neutral, cl_trim)
        if not all(math.isfinite(value) for value in values):
            return None, ("trim solution contains non-finite values",)
        if abs(delta_e_trim) > cls._MAX_TRIM_DEFLECTION_DEG:
            return None, (
                f"required elevator deflection exceeds ±{cls._MAX_TRIM_DEFLECTION_DEG:g}°",
            )

        return ElevatorTrim(
            alpha_ref=alpha_ref,
            cm_0=cm_zero_alpha,
            cm_alpha=cm_alpha_per_deg,
            cm_delta_e=elevator.c_m_delta,
            delta_e_trim=delta_e_trim,
            alpha_trim_neutral=alpha_trim_neutral,
            cl_trim=cl_trim,
        ), ()
