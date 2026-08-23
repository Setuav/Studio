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

from .base import FlightCondition, ReferenceValues
from .stability_models import ControlEffectiveness, ElevatorTrim, StabilityDerivatives

logger = logging.getLogger(__name__)


class StabilityAnalysisEngine:
    """Computes longitudinal and lateral-directional stability derivatives, neutral point, and trim."""

    def compute_stability(
        self,
        airplane: Any,
        condition: FlightCondition,
        ref: ReferenceValues,
        components: list[dict[str, Any]] | None = None,
        builder_fn: Any | None = None,
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
        b_ref = max(float(ref.b_ref), 1e-4)
        x_cg = float(ref.x_cg)

        # Baseline operating point
        op_base = asb.OperatingPoint(
            atmosphere=atmosphere,
            velocity=vel,
            alpha=ref_a,
            beta=ref_b,
        )
        vlm_base = asb.VortexLatticeMethod(airplane=airplane, op_point=op_base).run()
        cl_0 = float(np.ravel(vlm_base["CL"])[0])
        cd_0 = float(np.ravel(vlm_base["CD"])[0])
        cm_0 = float(np.ravel(vlm_base.get("Cm", 0.0))[0])

        # 1. Longitudinal Angle of Attack Derivatives (d/dalpha)
        da_deg = 0.5
        da_rad = math.radians(da_deg)
        op_a_p = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a + da_deg, beta=ref_b)
        op_a_m = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a - da_deg, beta=ref_b)
        res_a_p = asb.VortexLatticeMethod(airplane=airplane, op_point=op_a_p).run()
        res_a_m = asb.VortexLatticeMethod(airplane=airplane, op_point=op_a_m).run()

        cla_rad = float(np.ravel(res_a_p["CL"] - res_a_m["CL"])[0]) / (2.0 * da_rad)
        cda_rad = float(np.ravel(res_a_p["CD"] - res_a_m["CD"])[0]) / (2.0 * da_rad)
        cma_rad = float(np.ravel(res_a_p.get("Cm", 0.0) - res_a_m.get("Cm", 0.0))[0]) / (2.0 * da_rad)

        cla_deg = cla_rad * (math.pi / 180.0)
        cma_deg = cma_rad * (math.pi / 180.0)

        # 2. Pitch Damping Derivatives (d/dq_hat, where q_hat = q * c / (2 * V))
        q_hat_pert = 0.05
        q_pert_val = q_hat_pert * 2.0 * vel / c_ref
        op_q_p = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a, beta=ref_b, q=q_pert_val)
        op_q_m = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a, beta=ref_b, q=-q_pert_val)
        res_q_p = asb.VortexLatticeMethod(airplane=airplane, op_point=op_q_p).run()
        res_q_m = asb.VortexLatticeMethod(airplane=airplane, op_point=op_q_m).run()

        cl_q = float(np.ravel(res_q_p["CL"] - res_q_m["CL"])[0]) / (2.0 * q_hat_pert)
        cm_q = float(np.ravel(res_q_p.get("Cm", 0.0) - res_q_m.get("Cm", 0.0))[0]) / (2.0 * q_hat_pert)

        # 3. Lateral-Directional Sideslip Derivatives (d/dbeta)
        db_deg = 0.5
        db_rad = math.radians(db_deg)
        op_b_p = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a, beta=ref_b + db_deg)
        op_b_m = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a, beta=ref_b - db_deg)
        res_b_p = asb.VortexLatticeMethod(airplane=airplane, op_point=op_b_p).run()
        res_b_m = asb.VortexLatticeMethod(airplane=airplane, op_point=op_b_m).run()

        cyb_rad = float(np.ravel(res_b_p.get("CY", 0.0) - res_b_m.get("CY", 0.0))[0]) / (2.0 * db_rad)
        clb_rad = float(np.ravel(res_b_p.get("Cl", 0.0) - res_b_m.get("Cl", 0.0))[0]) / (2.0 * db_rad)
        cnb_rad = float(np.ravel(res_b_p.get("Cn", 0.0) - res_b_m.get("Cn", 0.0))[0]) / (2.0 * db_rad)

        cyb_deg = cyb_rad * (math.pi / 180.0)
        clb_deg = clb_rad * (math.pi / 180.0)
        cnb_deg = cnb_rad * (math.pi / 180.0)

        # 4. Roll Rate Damping Derivatives (d/dp_hat, where p_hat = p * b / (2 * V))
        p_hat_pert = 0.05
        p_pert_val = p_hat_pert * 2.0 * vel / b_ref
        op_p_p = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a, beta=ref_b, p=p_pert_val)
        op_p_m = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a, beta=ref_b, p=-p_pert_val)
        res_p_p = asb.VortexLatticeMethod(airplane=airplane, op_point=op_p_p).run()
        res_p_m = asb.VortexLatticeMethod(airplane=airplane, op_point=op_p_m).run()

        cl_p = float(np.ravel(res_p_p.get("Cl", 0.0) - res_p_m.get("Cl", 0.0))[0]) / (2.0 * p_hat_pert)
        cn_p = float(np.ravel(res_p_p.get("Cn", 0.0) - res_p_m.get("Cn", 0.0))[0]) / (2.0 * p_hat_pert)

        # 5. Yaw Rate Damping Derivatives (d/dr_hat, where r_hat = r * b / (2 * V))
        r_hat_pert = 0.05
        r_pert_val = r_hat_pert * 2.0 * vel / b_ref
        op_r_p = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a, beta=ref_b, r=r_pert_val)
        op_r_m = asb.OperatingPoint(atmosphere=atmosphere, velocity=vel, alpha=ref_a, beta=ref_b, r=-r_pert_val)
        res_r_p = asb.VortexLatticeMethod(airplane=airplane, op_point=op_r_p).run()
        res_r_m = asb.VortexLatticeMethod(airplane=airplane, op_point=op_r_m).run()

        cl_r = float(np.ravel(res_r_p.get("Cl", 0.0) - res_r_m.get("Cl", 0.0))[0]) / (2.0 * r_hat_pert)
        cn_r = float(np.ravel(res_r_p.get("Cn", 0.0) - res_r_m.get("Cn", 0.0))[0]) / (2.0 * r_hat_pert)

        # 6. Neutral Point & Static Margin
        if abs(cla_rad) > 1e-4:
            sm = -float(cma_rad / cla_rad)
            x_np = x_cg + sm * c_ref
            static_margin_pct = sm * 100.0
        else:
            sm = 0.0
            x_np = x_cg
            static_margin_pct = 0.0

        # 7. Control Effectiveness & Elevator Trim
        # 7. 3-Axis Aerodynamic Control Effectiveness (Elevator, Aileron, Rudder)
        controls_map: dict[str, ControlEffectiveness] = {}
        elevator_trim: ElevatorTrim | None = None

        if components and builder_fn:
            # Evaluate 3-axis flight control channels plus any discrete surface tags
            control_candidates = ["elevator", "aileron", "rudder", "flap"]
            for c in components:
                if not isinstance(c, dict):
                    continue
                geom = c.get("parameters", {}).get("geometry", {}) if isinstance(c.get("parameters"), dict) else {}
                for cs in geom.get("control_surfaces", []):
                    if isinstance(cs, dict) and cs.get("tag"):
                        control_candidates.append(str(cs["tag"]).lower())

            unique_candidates = list(dict.fromkeys(control_candidates))
            for ctrl_tag in unique_candidates:
                d_delta = 2.0  # deg
                cond_p = FlightCondition(velocity=vel, altitude=alt, alpha=ref_a, beta=ref_b, control_deflections={ctrl_tag: d_delta})
                cond_m = FlightCondition(velocity=vel, altitude=alt, alpha=ref_a, beta=ref_b, control_deflections={ctrl_tag: -d_delta})

                try:
                    plane_p = builder_fn(components, cond_p)
                    plane_m = builder_fn(components, cond_m)
                    res_c_p = asb.VortexLatticeMethod(airplane=plane_p, op_point=op_base).run()
                    res_c_m = asb.VortexLatticeMethod(airplane=plane_m, op_point=op_base).run()

                    cl_delta = float(np.ravel(res_c_p.get("Cl", 0.0) - res_c_m.get("Cl", 0.0))[0]) / (2.0 * d_delta)
                    cm_delta = float(np.ravel(res_c_p.get("Cm", 0.0) - res_c_m.get("Cm", 0.0))[0]) / (2.0 * d_delta)
                    cn_delta = float(np.ravel(res_c_p.get("Cn", 0.0) - res_c_m.get("Cn", 0.0))[0]) / (2.0 * d_delta)
                    cy_delta = float(np.ravel(res_c_p.get("CY", 0.0) - res_c_m.get("CY", 0.0))[0]) / (2.0 * d_delta)
                    cL_delta = float(np.ravel(res_c_p["CL"] - res_c_m["CL"])[0]) / (2.0 * d_delta)
                    cD_delta = float(np.ravel(res_c_p["CD"] - res_c_m["CD"])[0]) / (2.0 * d_delta)

                    # Only register if the control channel produces a non-zero response
                    if any(abs(v) > 1e-5 for v in (cl_delta, cm_delta, cn_delta, cy_delta, cL_delta)):
                        controls_map[ctrl_tag] = ControlEffectiveness(
                            control_tag=ctrl_tag,
                            c_l_delta=cl_delta,
                            c_m_delta=cm_delta,
                            c_n_delta=cn_delta,
                            c_y_delta=cy_delta,
                            c_L_delta=cL_delta,
                            c_D_delta=cD_delta,
                        )

                        if ctrl_tag == "elevator" and abs(cm_delta) > 1e-4:
                            # Solve for longitudinal trim equilibrium
                            cm_zero_alpha = cm_0 - (cma_deg * ref_a)
                            de_trim = -float(cm_0) / cm_delta
                            a_trim = -float(cm_zero_alpha) / cma_deg if abs(cma_deg) > 1e-4 else 0.0
                            cl_trim_val = cl_0 + cL_delta * de_trim

                            elevator_trim = ElevatorTrim(
                                alpha_ref=ref_a,
                                cm_0=cm_zero_alpha,
                                cm_alpha=cma_deg,
                                cm_delta_e=cm_delta,
                                delta_e_trim=de_trim,
                                alpha_trim_neutral=a_trim,
                                cl_trim=cl_trim_val,
                            )
                except Exception as err:
                    logger.debug("Control channel %s evaluation skipped: %s", ctrl_tag, err)

        return StabilityDerivatives(
            c_L_alpha_rad=cla_rad,
            c_L_alpha_deg=cla_deg,
            c_D_alpha_rad=cda_rad,
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
            is_pitch_stable=(cma_rad < 0),
            is_pitch_damped=(cm_q < 0),
            is_roll_stable=(clb_rad < 0),
            is_roll_damped=(cl_p < 0),
            is_yaw_stable=(cnb_rad > 0),
            is_yaw_damped=(cn_r < 0),
            controls=controls_map,
            elevator_trim=elevator_trim,
        )
