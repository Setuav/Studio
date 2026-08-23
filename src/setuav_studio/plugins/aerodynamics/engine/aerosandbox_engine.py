"""AeroSandbox engine implementation for Setuav Studio."""
from __future__ import annotations

import logging
import math
from copy import deepcopy
from typing import Any

from .base import (
    AeroEngine,
    AeroForcesMoments,
    AeroResult,
    AeroState,
    AnalysisMethod,
    AnalysisType,
    ControlSurfaceType,
    EngineCapabilities,
    FlightCondition,
    MultiDimensionalSweepResult,
    PolarPoint,
    PropulsionPoint,
    ReferenceValues,
    SweepType,
    SweepVariable,
)
from .airfoil_engine import AirfoilAnalysisEngine
from .airfoil_models import AirfoilPolar
from .stability_engine import StabilityAnalysisEngine
from .stability_models import StabilityDerivatives
from setuav_studio.plugins.geometry.engine.airfoil import (
    apply_airfoil_shaping,
    sample_airfoil_points,
)

logger = logging.getLogger(__name__)

try:
    import aerosandbox as asb
    import aerosandbox.numpy as np

    HAS_AEROSANDBOX = True
except ImportError:
    HAS_AEROSANDBOX = False
    asb = None
    np = None


class AeroSandboxEngine(AeroEngine):
    """AeroSandbox aerodynamic engine supporting VLM and AeroBuildup methods."""

    @property
    def name(self) -> str:
        return "AeroSandbox"

    def is_available(self) -> bool:
        return HAS_AEROSANDBOX

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            methods=frozenset({
                AnalysisMethod.COMPREHENSIVE,
                AnalysisMethod.VLM,
                AnalysisMethod.AERO_BUILDUP,
                AnalysisMethod.LIFTING_LINE,
            }),
            analysis_types=frozenset({
                AnalysisType.SINGLE_POINT,
                AnalysisType.ALPHA_SWEEP,
                AnalysisType.BETA_SWEEP,
                AnalysisType.MULTI_SWEEP,
            }),
            supports_fuselage=True,
            supports_control_surfaces=True,
        )

    def analyze(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod = AnalysisMethod.COMPREHENSIVE,
        settings: dict[str, Any] | None = None,
        progress_callback: Any | None = None,
    ) -> AeroResult:
        if not HAS_AEROSANDBOX:
            raise RuntimeError(
                "AeroSandbox library is not installed. Please install it using 'pip install aerosandbox'."
            )

        settings = settings or {}
        span_res = int(settings.get("spanwise_resolution", 12))
        chord_res = int(settings.get("chordwise_resolution", 8))
        span_spacing_name = str(settings.get("spanwise_spacing", "cosine")).lower()
        chord_spacing_name = str(settings.get("chordwise_spacing", "cosine")).lower()
        span_spacing_fn = np.cosspace if "cos" in span_spacing_name else np.linspace
        chord_spacing_fn = np.cosspace if "cos" in chord_spacing_name else np.linspace
        include_wave = bool(settings.get("include_wave_drag", True))
        apply_pg = bool(settings.get("compressibility_correction", True))

        base_airplane = self._build_airplane(components, condition=condition)
        if not base_airplane.wings:
            raise ValueError("No valid lifting surfaces found in project for aerodynamic analysis.")

        comp_by_id = {
            str(comp.get("id")): comp
            for comp in components
            if isinstance(comp, dict) and comp.get("id")
        }
        propulsion_points = self._extract_propulsion_points(components, comp_by_id)

        span, area = self._compute_reference_geometry(base_airplane)
        mean_chord = area / span if span > 0 else 0.0
        ref = ReferenceValues(
            s_ref=area,
            b_ref=span,
            c_ref=mean_chord,
            x_cg=float(base_airplane.xyz_ref[0]) if hasattr(base_airplane, "xyz_ref") and base_airplane.xyz_ref is not None else 0.0,
            y_cg=float(base_airplane.xyz_ref[1]) if hasattr(base_airplane, "xyz_ref") and base_airplane.xyz_ref is not None else 0.0,
            z_cg=float(base_airplane.xyz_ref[2]) if hasattr(base_airplane, "xyz_ref") and base_airplane.xyz_ref is not None else 0.0,
        )
        ref_area = area if area > 0 else 1.0

        # Pre-compute and cache 2D airfoil section aerodynamics for all lifting surfaces
        airfoil_engine = AirfoilAnalysisEngine()
        section_polars: dict[str, Any] = {}
        section_cl_max_list: list[float] = []

        ref_atmosphere = asb.Atmosphere(altitude=condition.altitude)
        ref_rho = float(ref_atmosphere.density())
        ref_mu = float(ref_atmosphere.dynamic_viscosity())
        ref_reynolds = (ref_rho * condition.velocity * mean_chord / ref_mu) if ref_mu > 0 else 1e5
        ref_sos = float(ref_atmosphere.speed_of_sound())
        ref_mach = condition.velocity / ref_sos if ref_sos > 0 else 0.0

        for wing in base_airplane.wings:
            for xsec in wing.xsecs:
                af = getattr(xsec, "airfoil", None)
                if af is not None:
                    af_name = str(getattr(af, "name", "airfoil"))
                    local_chord = max(float(xsec.chord), 1e-4)
                    local_re = (ref_reynolds * (local_chord / mean_chord)) if mean_chord > 0 else ref_reynolds
                    try:
                        p2d = airfoil_engine.analyze_airfoil(
                            airfoil=af,
                            reynolds=local_re,
                            alphas=[-4.0, 0.0, 4.0, 8.0, 12.0, 16.0],
                            mach=ref_mach,
                        )
                        section_polars[f"{wing.name}_{af_name}"] = p2d.to_dict()
                        if p2d.cl_max > 0:
                            section_cl_max_list.append(p2d.cl_max)
                    except Exception as err:
                        logger.debug("2D Section analysis skipped for %s: %s", af_name, err)

        est_stall_cl = (min(section_cl_max_list) * 0.92) if section_cl_max_list else 1.25

        # Generate primary and secondary sweep evaluation points
        primary_vals = condition.get_primary_sweep_values()
        sec_vals = condition.get_secondary_sweep_values() if condition.secondary_variable else [None]
        sweep_type = condition.sweep_type

        eval_states: list[dict[str, Any]] = []
        for s_val in sec_vals:
            for p_val in primary_vals:
                st_dict: dict[str, Any] = {
                    "alpha": float(condition.alpha),
                    "beta": float(condition.beta),
                    "velocity": float(condition.velocity),
                    "altitude": float(condition.altitude),
                    "controls": dict(condition.control_deflections),
                    "p_val": float(p_val),
                    "s_val": float(s_val) if s_val is not None else None,
                }

                # Primary variable mapping
                if sweep_type == SweepType.ALPHA or condition.sweep_variable == "alpha":
                    st_dict["alpha"] = float(p_val)
                elif sweep_type == SweepType.BETA or condition.sweep_variable == "beta":
                    st_dict["beta"] = float(p_val)
                elif sweep_type == SweepType.VELOCITY or condition.sweep_variable in ("velocity", "v", "speed"):
                    st_dict["velocity"] = float(p_val)
                elif sweep_type == SweepType.ALTITUDE or condition.sweep_variable in ("altitude", "alt", "h"):
                    st_dict["altitude"] = float(p_val)
                else:
                    st_dict["controls"][condition.sweep_variable] = float(p_val)

                # Secondary variable mapping
                if s_val is not None and condition.secondary_variable:
                    s_var = condition.secondary_variable
                    if s_var == "alpha":
                        st_dict["alpha"] = float(s_val)
                    elif s_var == "beta":
                        st_dict["beta"] = float(s_val)
                    elif s_var in ("velocity", "v", "speed"):
                        st_dict["velocity"] = float(s_val)
                    elif s_var in ("altitude", "alt", "h"):
                        st_dict["altitude"] = float(s_val)
                    else:
                        st_dict["controls"][s_var] = float(s_val)

                eval_states.append(st_dict)

        polar_points: list[PolarPoint] = []
        solver_points_map: dict[str, list[PolarPoint]] = {
            "vlm": [],
            "aero_buildup": [],
            "lifting_line": [],
        }
        oswald_list: list[float] = []
        total_steps = len(eval_states)

        for idx, st_dict in enumerate(eval_states, start=1):
            cur_alpha = float(st_dict["alpha"])
            cur_beta = float(st_dict["beta"])
            cur_vel = max(float(st_dict["velocity"]), 0.1)
            cur_alt = max(float(st_dict["altitude"]), 0.0)
            cur_controls = dict(st_dict["controls"])

            cur_cond = FlightCondition(
                velocity=cur_vel,
                altitude=cur_alt,
                alpha=cur_alpha,
                beta=cur_beta,
                p=float(condition.p),
                q=float(condition.q),
                r=float(condition.r),
                control_deflections=cur_controls,
            )

            # Rebuild airplane if control deflections are non-zero / modified
            if cur_controls != condition.control_deflections:
                cur_airplane = self._build_airplane(components, condition=cur_cond)
            else:
                cur_airplane = base_airplane

            cur_atmosphere = asb.Atmosphere(altitude=cur_alt)
            cur_rho = float(cur_atmosphere.density())
            cur_mu = float(cur_atmosphere.dynamic_viscosity())
            cur_sos = float(cur_atmosphere.speed_of_sound())
            cur_mach = cur_vel / cur_sos if cur_sos > 0 else 0.0
            cur_q_inf = 0.5 * cur_rho * (cur_vel ** 2)
            cur_qs = cur_q_inf * ref_area
            cur_reynolds = (cur_rho * cur_vel * mean_chord / cur_mu) if cur_mu > 0 else 0.0

            # Prandtl-Glauert compressibility correction factor for subsonic flow
            if apply_pg and 0.1 <= cur_mach < 0.95:
                pg_factor = 1.0 / math.sqrt(max(1.0 - (cur_mach ** 2), 0.05))
            else:
                pg_factor = 1.0

            # Progress callback label
            if progress_callback:
                if sweep_type == SweepType.ALPHA:
                    msg = f"α={cur_alpha:.1f}°"
                elif sweep_type == SweepType.BETA:
                    msg = f"β={cur_beta:.1f}°"
                elif sweep_type == SweepType.CONTROL_DEFLECTION:
                    msg = f"{condition.sweep_variable}={st_dict['p_val']:.1f}°"
                elif sweep_type == SweepType.VELOCITY:
                    msg = f"V={cur_vel:.1f}m/s"
                elif sweep_type == SweepType.ALTITUDE:
                    msg = f"h={cur_alt:.0f}m"
                else:
                    msg = f"Step {idx}/{total_steps}"
                progress_callback(idx, total_steps, msg)

            op = asb.OperatingPoint(
                atmosphere=cur_atmosphere,
                velocity=cur_vel,
                alpha=cur_alpha,
                beta=cur_beta,
                p=float(condition.p),
                q=float(condition.q),
                r=float(condition.r),
            )

            state = AeroState(
                alpha=cur_alpha,
                beta=cur_beta,
                p=float(condition.p),
                q=float(condition.q),
                r=float(condition.r),
                velocity=cur_vel,
                altitude=cur_alt,
                mach=cur_mach,
                reynolds=cur_reynolds,
                dynamic_pressure=cur_q_inf,
                control_deflections=cur_controls,
            )

            def build_pt(
                cl_val: float,
                cd_val: float,
                cm_val: float,
                cd_ind_val: float,
                cd_prof_val: float,
                cd_wave_val: float,
                cy_val: float,
                cl_r_val: float,
                cn_val: float,
                conv: bool = True,
            ) -> PolarPoint:
                ld_v = cl_val / cd_val if abs(cd_val) > 1e-7 else 0.0
                lift_v = cur_qs * cl_val
                drag_v = cur_qs * cd_val
                side_v = cur_qs * cy_val

                a_rad = math.radians(float(cur_alpha))
                b_rad = math.radians(float(cur_beta))
                ca, sa = math.cos(a_rad), math.sin(a_rad)
                cb, sb = math.cos(b_rad), math.sin(b_rad)

                fx_b_v = -drag_v * ca * cb + lift_v * sa - side_v * ca * sb
                fy_b_v = side_v * cb - drag_v * sb
                fz_b_v = -lift_v * ca - drag_v * sa * cb - side_v * sa * sb

                mx_b_v = cur_qs * span * cl_r_val
                my_b_v = cur_qs * mean_chord * cm_val
                mz_b_v = cur_qs * span * cn_val

                fm = AeroForcesMoments(
                    fx_b=fx_b_v,
                    fy_b=fy_b_v,
                    fz_b=fz_b_v,
                    lift=lift_v,
                    drag=drag_v,
                    sideforce=side_v,
                    mx_b=mx_b_v,
                    my_b=my_b_v,
                    mz_b=mz_b_v,
                    mx_w=mx_b_v,
                    my_w=my_b_v,
                    mz_w=mz_b_v,
                )

                return PolarPoint(
                    alpha=cur_alpha,
                    cl=cl_val,
                    cd=cd_val,
                    cm=cm_val,
                    cd_induced=cd_ind_val,
                    cd_profile=cd_prof_val,
                    cl_over_cd=ld_v,
                    cx=(fx_b_v / cur_qs) if cur_qs > 0 else 0.0,
                    cy=(fy_b_v / cur_qs) if cur_qs > 0 else cy_val,
                    cz=(fz_b_v / cur_qs) if cur_qs > 0 else 0.0,
                    cl_roll=cl_r_val,
                    cn=cn_val,
                    cd_wave=cd_wave_val,
                    beta=cur_beta,
                    p=float(condition.p),
                    q=float(condition.q),
                    r=float(condition.r),
                    forces_moments=fm,
                    state=state,
                    velocity=cur_vel,
                    altitude=cur_alt,
                    mach=cur_mach,
                    reynolds=cur_reynolds,
                    dynamic_pressure=cur_q_inf,
                    control_deflections=cur_controls,
                    converged=conv,
                )

            # Solver execution
            if method == AnalysisMethod.COMPREHENSIVE:
                # 1. Run VLM for 3D vortex distribution and induced drag
                try:
                    vlm_solver = asb.VortexLatticeMethod(
                        airplane=cur_airplane,
                        op_point=op,
                        spanwise_resolution=span_res,
                        chordwise_resolution=chord_res,
                        spanwise_spacing_function=span_spacing_fn,
                        chordwise_spacing_function=chord_spacing_fn,
                    )
                    res_vlm = vlm_solver.run()

                    vlm_cl = float(np.ravel(res_vlm["CL"])[0]) * pg_factor
                    vlm_cd = float(np.ravel(res_vlm["CD"])[0]) * pg_factor
                    vlm_cm = float(np.ravel(res_vlm.get("Cm", 0.0))[0]) * pg_factor
                    vlm_cy = float(np.ravel(res_vlm.get("CY", 0.0))[0])
                    vlm_clr = float(np.ravel(res_vlm.get("Cl", 0.0))[0])
                    vlm_cn = float(np.ravel(res_vlm.get("Cn", 0.0))[0])
                    pt_vlm = build_pt(vlm_cl, vlm_cd, vlm_cm, vlm_cd, 0.0, 0.0, vlm_cy, vlm_clr, vlm_cn)
                    solver_points_map["vlm"].append(pt_vlm)
                except Exception as err:
                    logger.warning("VLM evaluation error at step %d: %s", idx, err)
                    vlm_cl, vlm_cd, vlm_cm, vlm_cy, vlm_clr, vlm_cn = 0.0, 0.02, 0.0, 0.0, 0.0, 0.0

                # 2. Run AeroBuildup for viscous profile drag and stall envelope
                try:
                    ab_solver = asb.AeroBuildup(
                        airplane=cur_airplane,
                        op_point=op,
                        include_wave_drag=include_wave,
                        model_size="small",
                    )
                    res_ab = ab_solver.run()

                    ab_cl = float(np.ravel(res_ab["CL"])[0])
                    ab_cd = float(np.ravel(res_ab["CD"])[0])
                    ab_cm = float(np.ravel(res_ab.get("Cm", 0.0))[0])
                    ab_d_prof = float(np.ravel(res_ab.get("D_profile", 0.0))[0])
                    ab_d_ind = float(np.ravel(res_ab.get("D_induced", 0.0))[0])
                    ab_d_wave = float(np.ravel(res_ab.get("D_wave", 0.0))[0]) if "D_wave" in res_ab else 0.0

                    ab_cd_prof = (ab_d_prof / cur_qs) if cur_qs > 0 else 0.0
                    ab_cd_ind = (ab_d_ind / cur_qs) if cur_qs > 0 else 0.0
                    ab_cd_wave = (ab_d_wave / cur_qs) if cur_qs > 0 else 0.0
                    ab_cy = float(np.ravel(res_ab.get("CY", 0.0))[0])
                    ab_clr = float(np.ravel(res_ab.get("Cl", 0.0))[0])
                    ab_cn = float(np.ravel(res_ab.get("Cn", 0.0))[0])

                    pt_ab = build_pt(ab_cl, ab_cd, ab_cm, ab_cd_ind, ab_cd_prof, ab_cd_wave, ab_cy, ab_clr, ab_cn)
                    solver_points_map["aero_buildup"].append(pt_ab)

                    wing_comps = res_ab.get("wing_aero_components", [])
                    if wing_comps:
                        oswald_list.append(float(wing_comps[0].oswalds_efficiency))
                except Exception as err:
                    logger.warning("AeroBuildup evaluation error at step %d: %s", idx, err)
                    ab_cl, ab_cd, ab_cm, ab_cd_prof, ab_cd_ind, ab_cd_wave, ab_cy, ab_clr, ab_cn = 0.0, 0.02, 0.0, 0.015, 0.0, 0.0, 0.0, 0.0, 0.0

                # 3. Run LiftingLine (if feasible)
                try:
                    ll_solver = asb.LiftingLine(
                        airplane=cur_airplane,
                        op_point=op,
                        spanwise_resolution=max(span_res // 2, 4),
                        spanwise_spacing_function=span_spacing_fn,
                    )
                    res_ll = ll_solver.run()
                    ll_cl = float(np.ravel(res_ll["CL"])[0])
                    ll_cd = float(np.ravel(res_ll["CD"])[0])
                    ll_cm = float(np.ravel(res_ll.get("Cm", 0.0))[0])
                    pt_ll = build_pt(ll_cl, ll_cd, ll_cm, ll_cd, 0.0, 0.0, 0.0, 0.0, 0.0)
                    solver_points_map["lifting_line"].append(pt_ll)
                except Exception as err:
                    logger.debug("LiftingLine solver skipped for state %d: %s", idx, err)

                # 4. Synthesize Unified Result:
                tot_cd_ind = vlm_cd
                tot_cd_prof = ab_cd_prof
                tot_cd_wave = ab_cd_wave
                tot_cd = max(tot_cd_ind + tot_cd_prof + tot_cd_wave, 1e-4)

                # Dynamic stall transition
                if abs(vlm_cl) >= (est_stall_cl * 0.88) or abs(cur_alpha) > 12.0:
                    stall_excess = max(abs(vlm_cl) - est_stall_cl * 0.88, 0.0) / max(est_stall_cl * 0.25, 0.1)
                    alpha_excess = max(abs(cur_alpha) - 12.0, 0.0) / 4.0
                    weight = min(max(stall_excess, alpha_excess), 1.0)
                    tot_cl = (1.0 - weight) * vlm_cl + weight * ab_cl
                else:
                    tot_cl = vlm_cl

                tot_cm = vlm_cm
                tot_cy = vlm_cy
                tot_clr = vlm_clr
                tot_cn = vlm_cn

                pt_unified = build_pt(tot_cl, tot_cd, tot_cm, tot_cd_ind, tot_cd_prof, tot_cd_wave, tot_cy, tot_clr, tot_cn)
                polar_points.append(pt_unified)

            elif method == AnalysisMethod.VLM:
                solver = asb.VortexLatticeMethod(
                    airplane=cur_airplane,
                    op_point=op,
                    spanwise_resolution=span_res,
                    chordwise_resolution=chord_res,
                    spanwise_spacing_function=span_spacing_fn,
                    chordwise_spacing_function=chord_spacing_fn,
                )
                res = solver.run()

                cl = float(np.ravel(res["CL"])[0]) * pg_factor
                cd = float(np.ravel(res["CD"])[0]) * pg_factor
                cy = float(np.ravel(res.get("CY", 0.0))[0])
                clr = float(np.ravel(res.get("Cl", 0.0))[0])
                cm = float(np.ravel(res.get("Cm", 0.0))[0]) * pg_factor
                cn = float(np.ravel(res.get("Cn", 0.0))[0])

                pt = build_pt(cl, cd, cm, cd, 0.0, 0.0, cy, clr, cn)
                polar_points.append(pt)
                solver_points_map["vlm"].append(pt)

            elif method == AnalysisMethod.LIFTING_LINE:
                solver = asb.LiftingLine(
                    airplane=cur_airplane,
                    op_point=op,
                    spanwise_resolution=span_res,
                    spanwise_spacing_function=span_spacing_fn,
                )
                res = solver.run()

                cl = float(np.ravel(res["CL"])[0]) * pg_factor
                cd = float(np.ravel(res["CD"])[0]) * pg_factor
                cy = float(np.ravel(res.get("CY", 0.0))[0])
                clr = float(np.ravel(res.get("Cl", 0.0))[0])
                cm = float(np.ravel(res.get("Cm", 0.0))[0]) * pg_factor
                cn = float(np.ravel(res.get("Cn", 0.0))[0])

                pt = build_pt(cl, cd, cm, cd, 0.0, 0.0, cy, clr, cn)
                polar_points.append(pt)
                solver_points_map["lifting_line"].append(pt)

            else:  # AERO_BUILDUP
                solver = asb.AeroBuildup(
                    airplane=cur_airplane,
                    op_point=op,
                    include_wave_drag=include_wave,
                    model_size="small",
                )
                res = solver.run()

                cl = float(np.ravel(res["CL"])[0])
                cd = float(np.ravel(res["CD"])[0])
                cm = float(np.ravel(res.get("Cm", 0.0))[0])
                cy = float(np.ravel(res.get("CY", 0.0))[0])
                clr = float(np.ravel(res.get("Cl", 0.0))[0])
                cn = float(np.ravel(res.get("Cn", 0.0))[0])

                d_prof = float(np.ravel(res.get("D_profile", 0.0))[0])
                d_ind = float(np.ravel(res.get("D_induced", 0.0))[0])
                d_wave = float(np.ravel(res.get("D_wave", 0.0))[0]) if "D_wave" in res else 0.0

                cd_p = (d_prof / cur_qs) if cur_qs > 0 else 0.0
                cd_i = (d_ind / cur_qs) if cur_qs > 0 else 0.0
                cd_w = (d_wave / cur_qs) if cur_qs > 0 else 0.0

                pt = build_pt(cl, cd, cm, cd_i, cd_p, cd_w, cy, clr, cn)
                polar_points.append(pt)
                solver_points_map["aero_buildup"].append(pt)

                wing_comps = res.get("wing_aero_components", [])
                if wing_comps:
                    oswald_list.append(float(wing_comps[0].oswalds_efficiency))

        cl_values = [p.cl for p in polar_points if p.converged]
        cd_values = [p.cd for p in polar_points if p.converged]
        ld_values = [p.cl_over_cd for p in polar_points if p.converged]

        cl_max = max(cl_values) if cl_values else 0.0
        cl_max_alpha = polar_points[cl_values.index(cl_max)].alpha if cl_values else 0.0
        cd_min = min(cd_values) if cd_values else 0.0
        ld_max = max(ld_values) if ld_values else 0.0
        ld_max_alpha = polar_points[ld_values.index(ld_max)].alpha if ld_values else 0.0

        oswald = float(sum(oswald_list) / len(oswald_list)) if oswald_list else None

        # Build MultiDimensionalSweepResult
        sweep_result: MultiDimensionalSweepResult | None = None
        if len(eval_states) > 1:
            var_unit = "deg"
            if sweep_type == SweepType.VELOCITY:
                var_unit = "m/s"
            elif sweep_type == SweepType.ALTITUDE:
                var_unit = "m"

            if condition.secondary_variable and len(sec_vals) > 1:
                sec_unit = "deg"
                if condition.secondary_variable in ("velocity", "v", "speed"):
                    sec_unit = "m/s"
                elif condition.secondary_variable in ("altitude", "alt", "h"):
                    sec_unit = "m"

                sweep_vars = [
                    SweepVariable(name=str(condition.secondary_variable), values=[float(v) for v in sec_vals], unit=sec_unit),
                    SweepVariable(name=str(condition.sweep_variable), values=primary_vals, unit=var_unit),
                ]
                grid_shp = (len(sec_vals), len(primary_vals))
            else:
                sweep_vars = [
                    SweepVariable(name=str(condition.sweep_variable), values=primary_vals, unit=var_unit)
                ]
                grid_shp = (len(primary_vals),)

            sweep_result = MultiDimensionalSweepResult(
                variables=sweep_vars,
                points=list(polar_points),
                grid_shape=grid_shp,
            )

        # Filter out empty solver curve lists
        clean_solvers = {k: v for k, v in solver_points_map.items() if v}

        # Compute 6-DoF linear stability derivatives, static margins, and trim
        stab_engine = StabilityAnalysisEngine()
        try:
            stab_derivatives = stab_engine.compute_stability(
                airplane=base_airplane,
                condition=condition,
                ref=ref,
                components=components,
                builder_fn=self._build_airplane,
            )
        except Exception as err:
            logger.warning("Stability derivatives computation failed: %s", err)
            stab_derivatives = None

        return AeroResult(
            method=method,
            engine_name=self.name,
            polar_points=polar_points,
            solver_results=clean_solvers,
            cl_max=cl_max,
            cl_max_alpha=cl_max_alpha,
            cd_min=cd_min,
            ld_max=ld_max,
            ld_max_alpha=ld_max_alpha,
            reference=ref,
            reynolds=ref_reynolds,
            mach=ref_mach,
            dynamic_pressure=0.5 * ref_rho * (condition.velocity ** 2),
            oswald_efficiency=oswald,
            stability_derivatives=stab_derivatives,
            sweep_result=sweep_result,
            condition=condition,
            propulsion_points=propulsion_points,
            raw={
                "airplane": base_airplane,
                "velocity": condition.velocity,
                "propulsion_points": [p.to_dict() for p in propulsion_points],
                "solver_results": {k: [pt.to_dict() for pt in v] for k, v in clean_solvers.items()},
                "section_polars": section_polars,
            },
        )

    def _build_airplane(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition | None = None,
    ) -> asb.Airplane:
        """Convert Setuav Studio components list to AeroSandbox Airplane object with attachment hierarchy and control surfaces."""
        wings: list[asb.Wing] = []
        fuselages: list[asb.Fuselage] = []

        comp_by_id = {
            str(comp.get("id")): comp
            for comp in components
            if isinstance(comp, dict) and comp.get("id")
        }

        for comp in components:
            if not isinstance(comp, dict):
                continue
            comp_type = comp.get("type", "")
            if comp_type == "org.setuav.core:lifting-surface":
                wing_res = self._convert_lifting_surface(comp, comp_by_id=comp_by_id, condition=condition)
                if isinstance(wing_res, list):
                    wings.extend(wing_res)
                elif wing_res is not None:
                    wings.append(wing_res)
            elif comp_type == "org.setuav.core:fuselage":
                fuselage = self._convert_fuselage(comp, comp_by_id=comp_by_id)
                if fuselage is not None:
                    fuselages.append(fuselage)

        if not wings:
            return asb.Airplane(name="Studio Aircraft", wings=[], fuselages=fuselages)

        # Primary wing reference (largest area wing is the reference aerodynamic surface)
        main_wing = max(wings, key=lambda w: self._compute_wing_area(w))
        main_span, main_area = self._compute_wing_span_and_area(main_wing)
        main_c_ref = main_area / main_span if main_span > 0 else 0.1

        # Calculate reasonable moment center (at quarter chord of main wing root)
        root_xsec = main_wing.xsecs[0]
        xyz_ref = [
            float(root_xsec.xyz_le[0]) + 0.25 * float(root_xsec.chord),
            0.0,
            float(root_xsec.xyz_le[2]),
        ]

        return asb.Airplane(
            name="Studio Aircraft",
            wings=wings,
            fuselages=fuselages,
            s_ref=main_area,
            c_ref=main_c_ref,
            b_ref=main_span,
            xyz_ref=xyz_ref,
        )

    def _extract_propulsion_points(
        self,
        components: list[dict[str, Any]],
        comp_by_id: dict[str, dict[str, Any]],
    ) -> list[PropulsionPoint]:
        """Extract propulsion installation positions, thrust vectors, and geometry for aero analysis."""
        prop_types = {
            "org.setuav.core:motor",
            "org.setuav.core:propeller",
            "org.setuav.core:rotor",
            "org.setuav.core:electric-propulsion-system",
        }
        prop_points: list[PropulsionPoint] = []
        for comp in components:
            if not isinstance(comp, dict):
                continue
            ctype = str(comp.get("type") or "")
            if ctype not in prop_types:
                continue

            cid = str(comp.get("id") or "")
            cname = str(comp.get("name") or cid)
            pos_m, rot_m = self._resolve_world_transform(comp, comp_by_id)

            # Default forward thrust direction is along +X body axis
            thrust_vec = rot_m @ np.array([1.0, 0.0, 0.0])
            norm = float(np.linalg.norm(thrust_vec))
            t_dir = tuple((thrust_vec / norm).tolist()) if norm > 1e-6 else (1.0, 0.0, 0.0)

            params = comp.get("parameters") if isinstance(comp.get("parameters"), dict) else {}

            # Extract diameter in meters
            diameter_val = float(params.get("diameter") or params.get("propeller_diameter") or params.get("rotor_diameter") or 0.0)
            if diameter_val > 5.0:  # Value given in mm
                diameter_val /= 1000.0

            pitch_val = float(params.get("pitch") or params.get("propeller_pitch") or 0.0)
            rot_dir = str(params.get("rotation_direction") or params.get("direction") or "CW").upper()
            max_thrust = float(params.get("max_thrust") or params.get("thrust") or 0.0)
            kv = float(params.get("kv") or params.get("motor_kv") or 0.0)

            prop_points.append(
                PropulsionPoint(
                    id=cid,
                    name=cname,
                    component_type=ctype,
                    position=(float(pos_m[0]), float(pos_m[1]), float(pos_m[2])),
                    thrust_vector=(float(t_dir[0]), float(t_dir[1]), float(t_dir[2])),
                    diameter=diameter_val,
                    pitch=pitch_val,
                    rotation_direction=rot_dir,
                    max_thrust=max_thrust,
                    motor_kv=kv,
                    properties=dict(params),
                )
            )
        return prop_points

    def _resolve_world_transform(
        self,
        comp: dict[str, Any],
        comp_by_id: dict[str, dict[str, Any]],
        visited: set[str] | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute accumulated world translation (meters) and 3x3 rotation matrix for a component."""
        if visited is None:
            visited = set()

        cid = str(comp.get("id") or "")
        if cid in visited:
            return np.zeros(3), np.eye(3)
        visited.add(cid)

        transform = comp.get("transform")
        transform = transform if isinstance(transform, dict) else {}
        pos = transform.get("position")
        pos = pos if isinstance(pos, dict) else {}
        rot = transform.get("rotation")
        rot = rot if isinstance(rot, dict) else {}

        local_pos = np.array([
            float(pos.get("x", 0.0)) / 1000.0,
            float(pos.get("y", 0.0)) / 1000.0,
            float(pos.get("z", 0.0)) / 1000.0,
        ])

        roll_deg = float(rot.get("roll") if "roll" in rot else rot.get("x", 0.0))
        pitch_deg = float(rot.get("pitch") if "pitch" in rot else rot.get("y", 0.0))
        yaw_deg = float(rot.get("yaw") if "yaw" in rot else rot.get("z", 0.0))
        local_rot = self._rotation_matrix_xyz(roll_deg, pitch_deg, yaw_deg)

        parent_id = comp.get("parent") or comp.get("attach_to") or (transform.get("parent") if isinstance(transform, dict) else None)
        if parent_id and str(parent_id) in comp_by_id:
            parent_comp = comp_by_id[str(parent_id)]
            parent_pos, parent_rot = self._resolve_world_transform(parent_comp, comp_by_id, visited)
            world_pos = parent_pos + parent_rot @ local_pos
            world_rot = parent_rot @ local_rot
            return world_pos, world_rot

        return local_pos, local_rot

    def _convert_lifting_surface(
        self,
        comp: dict[str, Any],
        comp_by_id: dict[str, dict[str, Any]] | None = None,
        condition: FlightCondition | None = None,
    ) -> list[asb.Wing] | asb.Wing | None:
        """Convert a single lifting surface and its control surfaces into AeroSandbox Wing(s)."""
        comp_id = str(comp.get("id") or "")
        params = comp.get("parameters") if isinstance(comp.get("parameters"), dict) else {}
        geometry = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}
        profiles = geometry.get("profiles")

        if not isinstance(profiles, list) or len(profiles) < 2:
            return None

        # Resolve global 3D world transform including parent/attachment chain
        if comp_by_id:
            attach_pos, attach_rot = self._resolve_world_transform(comp, comp_by_id)
        else:
            comp_transform = comp.get("transform") if isinstance(comp.get("transform"), dict) else {}
            pos = comp_transform.get("position") if isinstance(comp_transform.get("position"), dict) else {}
            rot = comp_transform.get("rotation") if isinstance(comp_transform.get("rotation"), dict) else {}
            attach_pos = np.array([
                float(pos.get("x", 0.0)) / 1000.0,
                float(pos.get("y", 0.0)) / 1000.0,
                float(pos.get("z", 0.0)) / 1000.0,
            ])
            roll_deg = float(rot.get("roll") if "roll" in rot else rot.get("x", 0.0))
            pitch_deg = float(rot.get("pitch") if "pitch" in rot else rot.get("y", 0.0))
            yaw_deg = float(rot.get("yaw") if "yaw" in rot else rot.get("z", 0.0))
            attach_rot = self._rotation_matrix_xyz(roll_deg, pitch_deg, yaw_deg)

        mirror = bool(geometry.get("mirror", False) or comp.get("mirror", False))
        if mirror:
            attach_pos[1] = 0.0

        # Collect raw station data
        station_raw: list[dict[str, Any]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            prof_pos = profile.get("position") if isinstance(profile.get("position"), dict) else {}
            prof_rot = profile.get("rotation") if isinstance(profile.get("rotation"), dict) else {}

            raw_xyz = np.array([
                float(prof_pos.get("x", 0.0)) / 1000.0,
                float(prof_pos.get("y", 0.0)) / 1000.0,
                float(prof_pos.get("z", 0.0)) / 1000.0,
            ])
            xyz_le = attach_rot @ raw_xyz + attach_pos
            chord = float(profile.get("chord", 100.0)) / 1000.0

            prof_pitch = float(
                profile.get("twist")
                if "twist" in profile
                else (
                    prof_rot.get("pitch")
                    if "pitch" in prof_rot
                    else (prof_rot.get("y") if "y" in prof_rot else prof_rot.get("x", 0.0))
                )
            )
            pitch_angle_deg = np.degrees(np.arcsin(-np.clip(attach_rot[2, 0], -1.0, 1.0)))
            total_twist = prof_pitch + pitch_angle_deg

            airfoil_spec = profile.get("airfoil")
            airfoil = self._resolve_airfoil(airfoil_spec, shaping=geometry.get("airfoil_shaping"))

            station_raw.append({
                "local_y": float(prof_pos.get("y", 0.0)),
                "xyz_le": xyz_le,
                "chord": max(chord, 1e-4),
                "twist": total_twist,
                "airfoil": airfoil,
            })

        if len(station_raw) < 2:
            return None

        # Compute span coordinates eta in [0, 1] along the 3D loft stations
        cum_dist = [0.0]
        for i in range(1, len(station_raw)):
            d = float(np.linalg.norm(station_raw[i]["xyz_le"] - station_raw[i-1]["xyz_le"]))
            cum_dist.append(cum_dist[-1] + max(d, 1e-6))
        total_span = max(cum_dist[-1], 1e-4)

        for i, s in enumerate(station_raw):
            s["eta"] = float(cum_dist[i] / total_span)

        # Collect control surfaces attached to this lifting surface
        cs_list: list[dict[str, Any]] = []
        if isinstance(geometry.get("control_surfaces"), list):
            cs_list.extend(cs for cs in geometry["control_surfaces"] if isinstance(cs, dict))

        if comp_by_id:
            for other in comp_by_id.values():
                if not isinstance(other, dict):
                    continue
                if other.get("type") == "org.setuav.core:control-surface":
                    parent_id = other.get("parent") or other.get("attach_to") or (
                        other.get("transform", {}).get("parent") if isinstance(other.get("transform"), dict) else None
                    )
                    if str(parent_id) == comp_id:
                        other_geom = other.get("parameters", {}).get("geometry", {}) if isinstance(other.get("parameters"), dict) else {}
                        cs_copy = deepcopy(other_geom)
                        cs_copy.setdefault("tag", other.get("name") or other.get("id"))
                        cs_copy.setdefault("id", other.get("id"))
                        cs_list.append(cs_copy)

        # Check if the lifting surface itself has control tags (e.g. tags: ["elevator"], tags: ["rudder"], tags: ["ruddervator"])
        comp_tags = [str(t).lower() for t in comp.get("parameters", {}).get("tags", [])] if isinstance(comp.get("parameters"), dict) else []
        comp_name_lower = str(comp.get("name") or "").lower()
        if not cs_list:
            for tag_candidate in ("elevator", "rudder", "aileron", "flap", "elevon", "ruddervator", "vtail", "v-tail"):
                if tag_candidate in comp_tags or tag_candidate in comp_name_lower:
                    is_rv_comp = tag_candidate in ("ruddervator", "vtail", "v-tail")
                    cs_list.append({
                        "tag": "ruddervator" if is_rv_comp else tag_candidate,
                        "type": "ruddervator" if is_rv_comp else tag_candidate,
                        "eta_start": 0.0,
                        "eta_end": 1.0,
                        "chord_fraction": 0.35,
                        "symmetry_mode": "symmetric" if not (tag_candidate in ("aileron", "elevon")) else "antisymmetric",
                    })

        # Parse control surface definitions
        parsed_cs: list[dict[str, Any]] = []
        for cs in cs_list:
            cs_type_enum = ControlSurfaceType.from_str(cs.get("type")) or ControlSurfaceType.FLAP
            tag = str(cs.get("tag") or cs.get("name") or cs.get("id") or cs_type_enum.value)
            cs_id = str(cs.get("id") or tag)

            # Base deflection from UI definition
            deflection = float(cs.get("deflection", 0.0))

            # Channel inputs from flight condition
            d_elevator = 0.0
            d_rudder = 0.0
            d_aileron = 0.0
            d_direct = 0.0

            if condition and condition.control_deflections:
                for k, v in condition.control_deflections.items():
                    k_clean = k.strip().lower()
                    if k_clean == "elevator":
                        d_elevator = float(v)
                    elif k_clean == "rudder":
                        d_rudder = float(v)
                    elif k_clean == "aileron":
                        d_aileron = float(v)
                    elif k_clean in (tag.lower(), cs_type_enum.value, cs_id.lower()):
                        d_direct = float(v)

            # Apply aerodynamic channel kinematic mixing based on ControlSurfaceType
            delta_r = deflection + d_direct
            delta_l = deflection + d_direct

            if cs_type_enum == ControlSurfaceType.ELEVATOR:
                delta_r += d_elevator
                delta_l += d_elevator
            elif cs_type_enum == ControlSurfaceType.RUDDER:
                delta_r += d_rudder
                delta_l -= d_rudder
            elif cs_type_enum == ControlSurfaceType.AILERON:
                delta_r += d_aileron
                delta_l -= d_aileron
            elif cs_type_enum == ControlSurfaceType.ELEVON:
                delta_r += (d_elevator + d_aileron)
                delta_l += (d_elevator - d_aileron)
            elif cs_type_enum == ControlSurfaceType.RUDDERVATOR:
                delta_r += (d_elevator + d_rudder)
                delta_l += (d_elevator - d_rudder)
            elif cs_type_enum == ControlSurfaceType.FLAP:
                pass

            # Span range [eta_start, eta_end]
            if "eta_start" in cs and "eta_end" in cs:
                eta_s = float(np.clip(float(cs["eta_start"]), 0.0, 1.0))
                eta_e = float(np.clip(float(cs["eta_end"]), 0.0, 1.0))
            elif "span_start" in cs and "span_end" in cs:
                s_s = float(cs["span_start"])
                s_e = float(cs["span_end"])
                if s_s > 5.0 or s_e > 5.0:  # Value given in mm
                    s_s /= 1000.0
                    s_e /= 1000.0
                eta_s = float(np.clip(s_s / total_span, 0.0, 1.0))
                eta_e = float(np.clip(s_e / total_span, 0.0, 1.0))
            else:
                eta_s, eta_e = 0.0, 1.0

            if eta_s > eta_e:
                eta_s, eta_e = eta_e, eta_s

            # Chord fraction
            chord_frac = float(cs.get("chord_fraction", 0.25))
            if cs.get("chord_mode") == "dimension" and "chord" in cs:
                c_val = float(cs["chord"])
                if c_val > 5.0:
                    c_val /= 1000.0
                chord_frac = c_val / max(float(station_raw[0]["chord"]), 0.01)
            chord_frac = float(np.clip(chord_frac, 0.05, 0.95))

            parsed_cs.append({
                "tag": tag,
                "type": cs_type_enum.value,
                "eta_start": eta_s,
                "eta_end": eta_e,
                "chord_fraction": chord_frac,
                "delta_r": delta_r,
                "delta_l": delta_l,
            })

        # Discretize spanwise breakpoints
        unique_etas = sorted({round(s["eta"], 4) for s in station_raw})
        for cs in parsed_cs:
            unique_etas.append(round(cs["eta_start"], 4))
            unique_etas.append(round(cs["eta_end"], 4))
        unique_etas = sorted(list(set(unique_etas)))

        # Interpolate station properties at each eta breakpoint
        def interp_station(eta_val: float) -> dict[str, Any]:
            for idx in range(len(station_raw) - 1):
                s0 = station_raw[idx]
                s1 = station_raw[idx + 1]
                if s0["eta"] <= eta_val <= s1["eta"] or math.isclose(eta_val, s0["eta"], abs_tol=1e-4) or math.isclose(eta_val, s1["eta"], abs_tol=1e-4):
                    d_eta = max(s1["eta"] - s0["eta"], 1e-6)
                    t = float(np.clip((eta_val - s0["eta"]) / d_eta, 0.0, 1.0))
                    xyz = (1.0 - t) * s0["xyz_le"] + t * s1["xyz_le"]
                    chord_v = (1.0 - t) * s0["chord"] + t * s1["chord"]
                    twist_v = (1.0 - t) * s0["twist"] + t * s1["twist"]
                    af = s0["airfoil"] if t < 0.5 else s1["airfoil"]
                    return {"xyz_le": xyz, "chord": chord_v, "twist": twist_v, "airfoil": af, "eta": eta_val}
            last = station_raw[-1]
            return {"xyz_le": last["xyz_le"], "chord": last["chord"], "twist": last["twist"], "airfoil": last["airfoil"], "eta": eta_val}

        evaluated_stations = [interp_station(e) for e in unique_etas]

        # Build Right and Left Wing cross sections with control deflections
        xsecs_right: list[asb.WingXSec] = []
        xsecs_left: list[asb.WingXSec] = []

        has_antisymmetric = False

        for st in evaluated_stations:
            e = st["eta"]
            base_af = st["airfoil"]
            af_r = base_af
            af_l = base_af
            cs_objs_r: list[asb.ControlSurface] = []
            cs_objs_l: list[asb.ControlSurface] = []

            for cs in parsed_cs:
                if cs["eta_start"] <= e <= cs["eta_end"] or math.isclose(e, cs["eta_start"], abs_tol=1e-4) or math.isclose(e, cs["eta_end"], abs_tol=1e-4):
                    delta_r = cs["delta_r"]
                    delta_l = cs["delta_l"]
                    cf = cs["chord_fraction"]
                    hinge_pt = 1.0 - cf

                    if abs(delta_r) > 1e-4:
                        af_r = base_af.add_control_surface(deflection=delta_r, hinge_point_x=hinge_pt)
                    if abs(delta_l) > 1e-4:
                        af_l = base_af.add_control_surface(deflection=delta_l, hinge_point_x=hinge_pt)

                    if abs(delta_r - delta_l) > 1e-4:
                        has_antisymmetric = True

                    cs_objs_r.append(asb.ControlSurface(name=cs["tag"], deflection=delta_r, hinge_point=hinge_pt, symmetric=math.isclose(delta_r, delta_l, abs_tol=1e-4)))
                    cs_objs_l.append(asb.ControlSurface(name=cs["tag"], deflection=delta_l, hinge_point=hinge_pt, symmetric=math.isclose(delta_r, delta_l, abs_tol=1e-4)))

            xyz = st["xyz_le"]
            xsecs_right.append(
                asb.WingXSec(
                    xyz_le=[float(xyz[0]), float(xyz[1]), float(xyz[2])],
                    chord=float(st["chord"]),
                    twist=float(st["twist"]),
                    airfoil=af_r,
                    control_surfaces=cs_objs_r if cs_objs_r else None,
                )
            )
            # Left side mirrored in Y
            xsecs_left.append(
                asb.WingXSec(
                    xyz_le=[float(xyz[0]), -float(xyz[1]), float(xyz[2])],
                    chord=float(st["chord"]),
                    twist=float(st["twist"]),
                    airfoil=af_l,
                    control_surfaces=cs_objs_l if cs_objs_l else None,
                )
            )

        name = str(comp.get("name") or comp.get("id") or "Wing")

        # Symmetric Root Center Junction Alignment:
        if mirror and abs(xsecs_right[0].xyz_le[1]) > 1e-4:
            r_root = asb.WingXSec(
                xyz_le=[float(xsecs_right[0].xyz_le[0]), 0.0, float(xsecs_right[0].xyz_le[2])],
                chord=float(xsecs_right[0].chord),
                twist=float(xsecs_right[0].twist),
                airfoil=xsecs_right[0].airfoil,
            )
            xsecs_right.insert(0, r_root)
            l_root = asb.WingXSec(
                xyz_le=[float(xsecs_left[0].xyz_le[0]), 0.0, float(xsecs_left[0].xyz_le[2])],
                chord=float(xsecs_left[0].chord),
                twist=float(xsecs_left[0].twist),
                airfoil=xsecs_left[0].airfoil,
            )
            xsecs_left.insert(0, l_root)

        if mirror:
            if has_antisymmetric:
                # Left wing xsecs must be ordered from tip (-Y) to root (0) along increasing +Y
                left_ordered = list(reversed(xsecs_left))
                return [
                    asb.Wing(name=f"{name}_Right", xsecs=xsecs_right, symmetric=False),
                    asb.Wing(name=f"{name}_Left", xsecs=left_ordered, symmetric=False),
                ]
            return asb.Wing(name=name, xsecs=xsecs_right, symmetric=True)

        return asb.Wing(name=name, xsecs=xsecs_right, symmetric=False)

    @staticmethod
    def _rotation_matrix_xyz(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
        """Standard 3D Tait-Bryan XYZ rotation matrix."""
        rx = np.radians(rx_deg)
        ry = np.radians(ry_deg)
        rz = np.radians(rz_deg)

        cx, sx = np.cos(rx), np.sin(rx)
        cy, sy = np.cos(ry), np.sin(ry)
        cz, sz = np.cos(rz), np.sin(rz)

        rx_m = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        ry_m = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        rz_m = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])

        return rz_m @ ry_m @ rx_m

    def _compute_wing_area(self, wing: asb.Wing) -> float:
        area = 0.0
        for i in range(len(wing.xsecs) - 1):
            x1 = wing.xsecs[i]
            x2 = wing.xsecs[i + 1]
            dy = abs(x2.xyz_le[1] - x1.xyz_le[1])
            dz = abs(x2.xyz_le[2] - x1.xyz_le[2])
            span_seg = math.sqrt(dy * dy + dz * dz)
            area += 0.5 * (x1.chord + x2.chord) * span_seg
        return area * (2.0 if wing.symmetric else 1.0)

    def _compute_wing_span_and_area(self, wing: asb.Wing) -> tuple[float, float]:
        span = 0.0
        area = 0.0
        for i in range(len(wing.xsecs) - 1):
            x1 = wing.xsecs[i]
            x2 = wing.xsecs[i + 1]
            dy = abs(x2.xyz_le[1] - x1.xyz_le[1])
            dz = abs(x2.xyz_le[2] - x1.xyz_le[2])
            span_seg = math.sqrt(dy * dy + dz * dz)
            span = max(span, abs(x2.xyz_le[1]), abs(x1.xyz_le[1]))
            area += 0.5 * (x1.chord + x2.chord) * span_seg
        if wing.symmetric:
            span *= 2.0
            area *= 2.0
        return span, area

    def _convert_fuselage(
        self,
        comp: dict[str, Any],
        comp_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> asb.Fuselage | None:
        """Convert a fuselage component dictionary to AeroSandbox Fuselage with 3D world positioning."""
        params = comp.get("parameters")
        params = params if isinstance(params, dict) else {}
        geometry = params.get("geometry")
        geometry = geometry if isinstance(geometry, dict) else {}
        segments = geometry.get("segments")

        if not isinstance(segments, list) or not segments:
            return None

        if comp_by_id:
            base_pos, base_rot = self._resolve_world_transform(comp, comp_by_id)
        else:
            comp_transform = comp.get("transform")
            comp_transform = comp_transform if isinstance(comp_transform, dict) else {}
            pos = comp_transform.get("position")
            pos = pos if isinstance(pos, dict) else {}
            base_pos = np.array([
                float(pos.get("x", 0.0)) / 1000.0,
                float(pos.get("y", 0.0)) / 1000.0,
                float(pos.get("z", 0.0)) / 1000.0,
            ])
            base_rot = np.eye(3)

        xsecs: list[asb.FuselageXSec] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            sections = seg.get("sections", [])
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                sec_pos = sec.get("position")
                sec_pos = sec_pos if isinstance(sec_pos, dict) else {}
                sec_prof = sec.get("profile")
                sec_prof = sec_prof if isinstance(sec_prof, dict) else {}

                raw_xyz = np.array([
                    float(sec_pos.get("x", 0.0)) / 1000.0,
                    float(sec_pos.get("y", 0.0)) / 1000.0,
                    float(sec_pos.get("z", 0.0)) / 1000.0,
                ])
                xyz_c = base_rot @ raw_xyz + base_pos

                p_type = str(sec_prof.get("type", "circle")).lower()
                if p_type == "circle":
                    dia = float(sec_prof.get("diameter", 100.0)) / 1000.0
                    w = h = max(dia, 1e-4)
                else:
                    w = float(sec_prof.get("width", 100.0)) / 1000.0
                    h = float(sec_prof.get("height", 100.0)) / 1000.0

                xsecs.append(
                    asb.FuselageXSec(
                        xyz_c=[float(xyz_c[0]), float(xyz_c[1]), float(xyz_c[2])],
                        width=max(w, 1e-4),
                        height=max(h, 1e-4),
                    )
                )

        if not xsecs:
            return None

        xsecs.sort(key=lambda s: s.xyz_c[0])
        name = str(comp.get("name") or comp.get("id") or "Fuselage")
        return asb.Fuselage(name=name, xsecs=xsecs)

    def _resolve_airfoil(
        self,
        spec: Any,
        shaping: dict[str, Any] | None = None,
    ) -> asb.Airfoil:
        """Resolve any airfoil specification to a fully-populated asb.Airfoil with standard Selig coordinates."""
        # 1. Extract name label
        name = "airfoil"
        if isinstance(spec, str):
            name = spec
        elif isinstance(spec, dict):
            name = str(spec.get("name") or spec.get("code") or spec.get("file") or "airfoil")

        # 2. Sample 2D normalized coordinates via Studio's robust built-in parser
        raw_coords = sample_airfoil_points(spec)

        # 3. Apply airfoil shaping (TE blunting, thickness scale, camber scale) if present
        if isinstance(shaping, dict):
            te_thickness = float(shaping.get("te_thickness", 0.0))
            thickness_scale = float(shaping.get("thickness_scale", 1.0))
            camber_scale = float(shaping.get("camber_scale", 1.0))
            raw_coords = apply_airfoil_shaping(
                raw_coords,
                te_thickness=te_thickness,
                thickness_scale=thickness_scale,
                camber_scale=camber_scale,
            )

        # 4. Normalize to Selig format (Upper TE [x~1, y>=0] -> LE [x=min] -> Lower TE [x~1, y<=0])
        coords_arr = np.array([[float(p[0]), float(p[1])] for p in raw_coords], dtype=float)
        coords_arr = self._to_selig_format(coords_arr)

        # 5. Construct asb.Airfoil directly from 2D coordinates array
        try:
            return asb.Airfoil(name=name, coordinates=coords_arr)
        except Exception as exc:
            logger.warning("Could not construct custom coordinate asb.Airfoil for '%s': %s", name, exc)
            return asb.Airfoil("naca0012")

    @staticmethod
    def _to_selig_format(coords: np.ndarray) -> np.ndarray:
        """Ensure airfoil coordinates are in standard Selig format: Upper TE -> LE -> Lower TE."""
        if len(coords) < 3:
            return coords

        min_x_idx = int(np.argmin(coords[:, 0]))

        # If first point is at LE (x~0), it's LE -> Upper TE -> Lower LE
        if min_x_idx == 0:
            max_x_idx = int(np.argmax(coords[:, 0]))
            upper_part = coords[: max_x_idx + 1][::-1]  # Reverse to TE -> LE
            lower_part = coords[max_x_idx:]
            if lower_part[-1, 0] < lower_part[0, 0]:  # TE to LE -> reverse to LE to TE
                lower_part = lower_part[::-1]
            return np.vstack([upper_part, lower_part[1:]])

        # If starting at TE, check if upper surface comes first (y >= 0)
        # If lower surface comes first, reverse entire loop so upper is first
        if min_x_idx > 0 and min_x_idx < len(coords) - 1:
            mid_upper_y = coords[min_x_idx // 2, 1]
            if mid_upper_y < 0:  # lower surface was traversed first
                coords = coords[::-1]

        return coords

    def _compute_reference_geometry(self, airplane: asb.Airplane) -> tuple[float, float]:
        """Compute reference span (m) and area (m²)."""
        total_span = 0.0
        total_area = 0.0

        for wing in airplane.wings:
            wing_span = 0.0
            wing_area = 0.0
            for i in range(len(wing.xsecs) - 1):
                x1 = wing.xsecs[i]
                x2 = wing.xsecs[i + 1]
                dy = abs(x2.xyz_le[1] - x1.xyz_le[1])
                wing_span = max(wing_span, abs(x2.xyz_le[1]), abs(x1.xyz_le[1]))
                avg_chord = (x1.chord + x2.chord) / 2.0
                wing_area += avg_chord * dy

            if wing.symmetric:
                wing_span *= 2.0
                wing_area *= 2.0

            total_span = max(total_span, wing_span)
            total_area += wing_area

        return total_span, total_area
