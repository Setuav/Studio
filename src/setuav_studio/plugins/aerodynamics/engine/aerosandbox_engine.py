"""AeroSandbox engine implementation for Setuav Studio."""
from __future__ import annotations

import logging
import math
from copy import deepcopy
from pathlib import Path
import re
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
from .stability_engine import StabilityAnalysisEngine
from setuav_studio.plugins.geometry.engine.airfoil import (
    apply_airfoil_shaping,
    sample_airfoil_points,
)
from setuav_studio.project import ProjectDocument

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
                AnalysisMethod.AERO_BUILDUP,
                AnalysisMethod.VLM,
                AnalysisMethod.LIFTING_LINE,
            }),
            analysis_types=frozenset({
                AnalysisType.SINGLE_POINT,
                AnalysisType.ALPHA_SWEEP,
                AnalysisType.BETA_SWEEP,
                AnalysisType.MULTI_SWEEP,
                AnalysisType.STABILITY_DERIVATIVES,
            }),
            supports_fuselage=True,
            supports_control_surfaces=True,
        )

    def analyze(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod = AnalysisMethod.AERO_BUILDUP,
        settings: dict[str, Any] | None = None,
        progress_callback: Any | None = None,
    ) -> AeroResult:
        if not HAS_AEROSANDBOX:
            raise RuntimeError(
                "AeroSandbox library is not installed. Please install it using 'pip install aerosandbox'."
            )

        if not isinstance(method, AnalysisMethod):
            method = AnalysisMethod.from_value(method)

        settings = settings or {}
        span_res = int(settings.get("spanwise_resolution", 12))
        chord_res = int(settings.get("chordwise_resolution", 8))
        span_spacing_name = str(settings.get("spanwise_spacing", "cosine")).lower()
        chord_spacing_name = str(settings.get("chordwise_spacing", "cosine")).lower()
        span_spacing_fn = np.cosspace if "cos" in span_spacing_name else np.linspace
        chord_spacing_fn = np.cosspace if "cos" in chord_spacing_name else np.linspace
        include_wave = bool(settings.get("include_wave_drag", True))

        orig_method = method
        effective_method = AnalysisMethod.AERO_BUILDUP if method == AnalysisMethod.COMPREHENSIVE else method

        mass_cg, mass_cg_source = self._resolve_mass_cg(components)
        base_airplane = self._build_airplane(
            components,
            condition=condition,
            xyz_ref=mass_cg,
        )
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
        reference_xyz = mass_cg or tuple(float(value) for value in base_airplane.xyz_ref)
        ref = ReferenceValues(
            s_ref=area,
            b_ref=span,
            c_ref=mean_chord,
            x_cg=float(reference_xyz[0]),
            y_cg=float(reference_xyz[1]),
            z_cg=float(reference_xyz[2]),
        )
        ref_area = area if area > 0 else 1.0

        # Generate primary and secondary sweep evaluation points
        primary_vals = condition.get_primary_sweep_values()
        sec_vals = condition.get_secondary_sweep_values() if condition.secondary_variable else [None]
        sweep_type = condition.sweep_type

        eval_states: list[dict[str, Any]] = []

        if sweep_type == SweepType.DUAL_ALPHA_BETA:
            # 1. Alpha sweep group (primary AoA polar)
            a_steps = max(int(condition.alpha_steps), 2)
            alpha_array = [float(v) for v in np.linspace(condition.alpha_min, condition.alpha_max, a_steps)]
            for a_val in alpha_array:
                eval_states.append({
                    "alpha": float(a_val),
                    "beta": float(condition.beta),
                    "velocity": float(condition.velocity),
                    "altitude": float(condition.altitude),
                    "controls": dict(condition.control_deflections),
                    "p_val": float(a_val),
                    "s_val": float(condition.beta),
                    "_sweep_group": "alpha",
                })

            # 2. Beta sweep group (sideslip response)
            b_steps = max(int(condition.beta_steps), 2)
            beta_array = [float(v) for v in np.linspace(condition.beta_min, condition.beta_max, b_steps)]
            for b_val in beta_array:
                eval_states.append({
                    "alpha": float(condition.alpha),
                    "beta": float(b_val),
                    "velocity": float(condition.velocity),
                    "altitude": float(condition.altitude),
                    "controls": dict(condition.control_deflections),
                    "p_val": float(b_val),
                    "s_val": float(condition.alpha),
                    "_sweep_group": "beta",
                })

        else:
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
                        "_sweep_group": "primary",
                    }

                    # Primary variable mapping
                    if sweep_type == SweepType.ALPHA or condition.sweep_variable == "alpha":
                        st_dict["alpha"] = float(p_val)
                    elif sweep_type == SweepType.BETA or condition.sweep_variable == "beta":
                        st_dict["beta"] = float(p_val)
                    else:
                        st_dict["controls"][condition.sweep_variable] = float(p_val)

                    # Secondary variable mapping
                    if s_val is not None and condition.secondary_variable:
                        s_var = condition.secondary_variable
                        if s_var == "alpha":
                            st_dict["alpha"] = float(s_val)
                        elif s_var == "beta":
                            st_dict["beta"] = float(s_val)
                        else:
                            st_dict["controls"][s_var] = float(s_val)

                    eval_states.append(st_dict)

        polar_points: list[PolarPoint] = []
        oswald_list: list[float] = []
        total_steps = len(eval_states) + 1

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
                # Keep the same mass-balance reference when a sweep point
                # rebuilds the geometry for a control deflection.  Falling
                # back to the quarter-chord here silently changed the moment
                # reference between sweep points.
                cur_airplane = self._build_airplane(
                    components,
                    condition=cur_cond,
                    xyz_ref=mass_cg,
                )
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

            # Progress callback label
            if progress_callback:
                if sweep_type == SweepType.ALPHA:
                    msg = f"α={cur_alpha:.1f}°"
                elif sweep_type == SweepType.BETA:
                    msg = f"β={cur_beta:.1f}°"
                elif sweep_type == SweepType.CONTROL_DEFLECTION:
                    msg = f"{condition.sweep_variable}={st_dict['p_val']:.1f}°"
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

            # Native AeroSandbox Solver Execution
            try:
                if effective_method == AnalysisMethod.VLM:
                    solver = asb.VortexLatticeMethod(
                        airplane=cur_airplane,
                        op_point=op,
                        spanwise_resolution=span_res,
                        chordwise_resolution=chord_res,
                        spanwise_spacing_function=span_spacing_fn,
                        chordwise_spacing_function=chord_spacing_fn,
                    )
                    res = solver.run()
                elif effective_method == AnalysisMethod.LIFTING_LINE:
                    solver = asb.LiftingLine(
                        airplane=cur_airplane,
                        op_point=op,
                        spanwise_resolution=span_res,
                        spanwise_spacing_function=span_spacing_fn,
                    )
                    res = solver.run()
                else:  # AERO_BUILDUP (Default)
                    solver = asb.AeroBuildup(
                        airplane=cur_airplane,
                        op_point=op,
                        include_wave_drag=include_wave,
                    )
                    res = solver.run()

                # Native aerodynamic coefficients
                cl = float(np.ravel(res["CL"])[0])
                cd = float(np.ravel(res["CD"])[0])
                cm = float(np.ravel(res.get("Cm", 0.0))[0])
                cy = float(np.ravel(res.get("CY", 0.0))[0])
                cl_roll = float(np.ravel(res.get("Cl", 0.0))[0])
                cn = float(np.ravel(res.get("Cn", 0.0))[0])

                # Native forces and moments vectors (Body, Wind, Geometry)
                f_b = np.ravel(res.get("F_b", [0.0, 0.0, 0.0]))
                f_w = np.ravel(res.get("F_w", [0.0, 0.0, 0.0]))
                f_g = np.ravel(res.get("F_g", [0.0, 0.0, 0.0]))
                m_b = np.ravel(res.get("M_b", [0.0, 0.0, 0.0]))
                m_w = np.ravel(res.get("M_w", [0.0, 0.0, 0.0]))
                m_g = np.ravel(res.get("M_g", [0.0, 0.0, 0.0]))

                # Dimensional lift and drag (Newtons)
                lift_val = float(np.ravel(res.get("L", cur_qs * cl))[0])
                drag_val = float(np.ravel(res.get("D", cur_qs * cd))[0])
                side_val = float(np.ravel(res.get("Y", cur_qs * cy))[0])

                # Serializable raw dictionary
                raw_dict: dict[str, Any] = {}
                for k, v in res.items():
                    if isinstance(v, (int, float, np.number)):
                        raw_dict[k] = float(v)
                    elif isinstance(v, np.ndarray):
                        raw_dict[k] = v.tolist()
                    elif isinstance(v, (str, bool, list, dict)):
                        raw_dict[k] = v

                raw_dict["_sweep_group"] = str(st_dict.get("_sweep_group", ""))
                fm = AeroForcesMoments(
                    fx_b=float(f_b[0]) if len(f_b) > 0 else 0.0,
                    fy_b=float(f_b[1]) if len(f_b) > 1 else 0.0,
                    fz_b=float(f_b[2]) if len(f_b) > 2 else 0.0,
                    lift=lift_val,
                    drag=drag_val,
                    sideforce=side_val,
                    fx_g=float(f_g[0]) if len(f_g) > 0 else 0.0,
                    fy_g=float(f_g[1]) if len(f_g) > 1 else 0.0,
                    fz_g=float(f_g[2]) if len(f_g) > 2 else 0.0,
                    mx_b=float(m_b[0]) if len(m_b) > 0 else 0.0,
                    my_b=float(m_b[1]) if len(m_b) > 1 else 0.0,
                    mz_b=float(m_b[2]) if len(m_b) > 2 else 0.0,
                    mx_w=float(m_w[0]) if len(m_w) > 0 else 0.0,
                    my_w=float(m_w[1]) if len(m_w) > 1 else 0.0,
                    mz_w=float(m_w[2]) if len(m_w) > 2 else 0.0,
                    mx_g=float(m_g[0]) if len(m_g) > 0 else 0.0,
                    my_g=float(m_g[1]) if len(m_g) > 1 else 0.0,
                    mz_g=float(m_g[2]) if len(m_g) > 2 else 0.0,
                    raw=raw_dict,
                )

                d_ind = float(np.ravel(res["D_induced"])[0]) if "D_induced" in res else None
                d_prof = float(np.ravel(res["D_profile"])[0]) if "D_profile" in res else None
                d_wave = float(np.ravel(res["D_wave"])[0]) if "D_wave" in res else None

                cd_ind = d_ind / cur_qs if d_ind is not None and cur_qs > 0 else None
                cd_prof = d_prof / cur_qs if d_prof is not None and cur_qs > 0 else None
                cd_wave = d_wave / cur_qs if d_wave is not None and cur_qs > 0 else None

                pt = PolarPoint(
                    alpha=cur_alpha,
                    cl=cl,
                    cd=cd,
                    cm=cm,
                    cd_induced=cd_ind,
                    cd_profile=cd_prof,
                    cl_over_cd=(cl / cd) if abs(cd) > 1e-7 else 0.0,
                    cx=(float(f_b[0]) / cur_qs) if cur_qs > 0 and len(f_b) > 0 else 0.0,
                    cy=cy,
                    cz=(float(f_b[2]) / cur_qs) if cur_qs > 0 and len(f_b) > 2 else 0.0,
                    cl_roll=cl_roll,
                    cn=cn,
                    cd_wave=cd_wave,
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
                    converged=True,
                    notes="",
                    raw=raw_dict,
                )

                wing_comps = res.get("wing_aero_components", [])
                if wing_comps:
                    oswald_list.append(float(wing_comps[0].oswalds_efficiency))

            except Exception as err:
                logger.warning("Solver %s failed for point alpha=%.1f, beta=%.1f: %s", method.value, cur_alpha, cur_beta, err)
                pt = PolarPoint(
                    alpha=cur_alpha,
                    cl=0.0,
                    cd=0.0,
                    cm=0.0,
                    beta=cur_beta,
                    state=state,
                    velocity=cur_vel,
                    altitude=cur_alt,
                    mach=cur_mach,
                    reynolds=cur_reynolds,
                    dynamic_pressure=cur_q_inf,
                    control_deflections=cur_controls,
                    converged=False,
                    notes=str(err),
                )

            polar_points.append(pt)

        converged_points = [p for p in polar_points if p.converged]
        best_lift = max(converged_points, key=lambda p: p.cl, default=None)
        best_drag = min(converged_points, key=lambda p: p.cd, default=None)
        best_efficiency = max(converged_points, key=lambda p: p.cl_over_cd, default=None)

        cl_max = best_lift.cl if best_lift else 0.0
        cl_max_alpha = best_lift.alpha if best_lift else 0.0
        cd_min = best_drag.cd if best_drag else 0.0
        ld_max = best_efficiency.cl_over_cd if best_efficiency else 0.0
        ld_max_alpha = best_efficiency.alpha if best_efficiency else 0.0

        oswald = float(sum(oswald_list) / len(oswald_list)) if oswald_list else None

        # Build MultiDimensionalSweepResult
        sweep_result: MultiDimensionalSweepResult | None = None
        if len(eval_states) > 1 and sweep_type != SweepType.DUAL_ALPHA_BETA:
            var_unit = "deg"

            if condition.secondary_variable and len(sec_vals) > 1:
                sec_unit = "deg"

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

        # Compute 6-DoF linear stability derivatives, static margins, and trim
        if progress_callback:
            progress_callback(len(eval_states), total_steps, "Stability")

        stab_engine = StabilityAnalysisEngine()
        try:
            stability_method = (
                AnalysisMethod.VLM
                if orig_method == AnalysisMethod.COMPREHENSIVE
                else effective_method
            )
            stab_derivatives = stab_engine.compute_stability(
                airplane=base_airplane,
                condition=condition,
                ref=ref,
                components=components,
                builder_fn=lambda comps, cond: self._build_airplane(
                    comps,
                    condition=cond,
                    xyz_ref=mass_cg,
                ),
                method=stability_method,
            )
        except Exception as err:
            logger.warning("Stability derivatives computation failed: %s", err)
            stab_derivatives = None

        if progress_callback:
            progress_callback(total_steps, total_steps, "Done")

        reference_atmosphere = asb.Atmosphere(altitude=max(float(condition.altitude), 0.0))
        reference_density = float(reference_atmosphere.density())
        reference_sos = float(reference_atmosphere.speed_of_sound())
        reference_mach = float(condition.velocity) / reference_sos if reference_sos > 0 else 0.0
        reference_q = 0.5 * reference_density * float(condition.velocity) ** 2
        reference_reynolds = polar_points[0].reynolds if polar_points else 0.0

        return AeroResult(
            method=orig_method,
            engine_name=self.name,
            polar_points=polar_points,
            cl_max=cl_max,
            cl_max_alpha=cl_max_alpha,
            cd_min=cd_min,
            ld_max=ld_max,
            ld_max_alpha=ld_max_alpha,
            reference=ref,
            reynolds=reference_reynolds,
            mach=reference_mach,
            dynamic_pressure=reference_q,
            oswald_efficiency=oswald,
            stability_derivatives=stab_derivatives,
            sweep_result=sweep_result,
            condition=condition,
            propulsion_points=propulsion_points,
            raw={
                "airplane": base_airplane,
                "method": effective_method.value,
                "reference_cg_source": mass_cg_source,
                "reference_xyz_m": list(reference_xyz),
                "velocity": float(condition.velocity),
            },
        )

    @staticmethod
    def _resolve_mass_cg(
        components: list[dict[str, Any]],
    ) -> tuple[tuple[float, float, float] | None, str]:
        """Resolve the aircraft CG from the shared Weight-Balance model."""
        try:
            from setuav_studio.plugins.weight_balance.engine.solver import WeightBalanceSolver

            project = ProjectDocument(
                path=Path("<aerodynamics>"),
                kind="json",
                data={"components": components},
            )
            result = WeightBalanceSolver().evaluate(project)
            return tuple(float(value) for value in result.total.cg_body_m), "weight_balance"
        except Exception as err:
            logger.info("Weight-Balance CG unavailable; using aerodynamic reference: %s", err)
            return None, "aerodynamic_reference"

    def _build_airplane(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition | None = None,
        xyz_ref: tuple[float, float, float] | None = None,
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
                if isinstance(fuselage, list):
                    fuselages.extend(fuselage)
                elif fuselage is not None:
                    fuselages.append(fuselage)

        if not wings:
            return asb.Airplane(name="Studio Aircraft", wings=[], fuselages=fuselages)

        # Primary wing reference (largest area wing is the reference aerodynamic surface)
        main_wing = max(wings, key=lambda w: self._compute_wing_area(w))
        main_span, main_area = self._compute_wing_span_and_area(main_wing)
        main_c_ref = main_area / main_span if main_span > 0 else 0.1

        # Calculate reasonable moment center (at quarter chord of main wing root)
        root_xsec = main_wing.xsecs[0]
        reference_xyz = xyz_ref or (
            float(root_xsec.xyz_le[0]) + 0.25 * float(root_xsec.chord),
            0.0,
            float(root_xsec.xyz_le[2]),
        )

        return asb.Airplane(
            name="Studio Aircraft",
            wings=wings,
            fuselages=fuselages,
            s_ref=main_area,
            c_ref=main_c_ref,
            b_ref=main_span,
            xyz_ref=reference_xyz,
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

        local_pos, local_rot = self._local_transform(comp)

        transform = comp.get("transform")
        transform = transform if isinstance(transform, dict) else {}
        parent_id = comp.get("parent") or comp.get("attach_to") or transform.get("parent")
        if parent_id and str(parent_id) in comp_by_id:
            parent_comp = comp_by_id[str(parent_id)]
            parent_pos, parent_rot = self._resolve_world_transform(parent_comp, comp_by_id, visited)
            world_pos = parent_pos + parent_rot @ local_pos
            world_rot = parent_rot @ local_rot
            return world_pos, world_rot

        return local_pos, local_rot

    def _local_transform(self, comp: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
        """Read a component transform in metres and return its local rotation matrix."""
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
        return local_pos, self._rotation_matrix_xyz(roll_deg, pitch_deg, yaw_deg)

    def _resolve_parent_transform(
        self,
        comp: dict[str, Any],
        comp_by_id: dict[str, dict[str, Any]],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return the world frame of a component's parent (or the aircraft frame)."""
        transform = comp.get("transform")
        transform = transform if isinstance(transform, dict) else {}
        parent_id = comp.get("parent") or comp.get("attach_to") or transform.get("parent")
        if parent_id and str(parent_id) in comp_by_id:
            return self._resolve_world_transform(comp_by_id[str(parent_id)], comp_by_id)
        return np.zeros(3), np.eye(3)

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

        mirror = bool(geometry.get("mirror", False) or comp.get("mirror", False))
        if comp_by_id:
            parent_pos, parent_rot = self._resolve_parent_transform(comp, comp_by_id)
        else:
            parent_pos, parent_rot = np.zeros(3), np.eye(3)
        local_attach_pos, local_attach_rot = self._local_transform(comp)
        attach_pos = parent_pos + parent_rot @ local_attach_pos
        attach_rot = parent_rot @ local_attach_rot
        # Mirroring happens in the component's parent frame.  In particular, a
        # non-zero attachment Y is a real fuselage-to-wing gap and must not be
        # collapsed to the aircraft centerline.
        mirror_matrix = np.diag([1.0, -1.0, 1.0])
        left_attach_pos = parent_pos + parent_rot @ (mirror_matrix @ local_attach_pos)
        left_attach_rot = parent_rot @ mirror_matrix @ local_attach_rot

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
            xyz_le_left = left_attach_rot @ raw_xyz + left_attach_pos
            chord = float(profile.get("chord", 100.0)) / 1000.0

            # AeroSandbox WingXSec has an explicit twist (pitch) field.  The
            # geometry schema's rotation.x is dihedral, not twist; treating it
            # as twist was producing incorrect section incidence.
            prof_pitch = float(
                profile.get("twist")
                if "twist" in profile
                else (prof_rot.get("pitch") if "pitch" in prof_rot else prof_rot.get("y", 0.0))
            )
            pitch_angle_deg = np.degrees(np.arcsin(-np.clip(attach_rot[2, 0], -1.0, 1.0)))
            total_twist = prof_pitch + pitch_angle_deg

            airfoil_spec = profile.get("airfoil")
            airfoil = self._resolve_airfoil(airfoil_spec, shaping=geometry.get("airfoil_shaping"))

            station_raw.append({
                "local_y": float(prof_pos.get("y", 0.0)),
                "xyz_le": xyz_le,
                "xyz_le_left": xyz_le_left,
                "chord": max(chord, 1e-4),
                "twist": total_twist,
                "airfoil": airfoil,
            })

        if len(station_raw) < 2:
            return None

        # Span stations are defined by the source geometry's local Y axis.  A
        # swept/dihedral wing must not change its control-surface fractions just
        # because its 3-D leading-edge path is longer.
        y_start = station_raw[0]["local_y"]
        y_delta = station_raw[-1]["local_y"] - y_start
        if abs(y_delta) > 1e-9:
            total_span = max(abs(y_delta) / 1000.0, 1e-4)
            for s in station_raw:
                s["eta"] = float(np.clip((s["local_y"] - y_start) / y_delta, 0.0, 1.0))
        else:
            total_span = max(
                float(np.linalg.norm(station_raw[-1]["xyz_le"] - station_raw[0]["xyz_le"])),
                1e-4,
            )
            for i, s in enumerate(station_raw):
                s["eta"] = float(i / max(len(station_raw) - 1, 1))

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
                        cs_copy["_child_component"] = True
                        cs_list.append(cs_copy)

        # Check if the lifting surface itself has control tags (e.g. tags: ["elevator"], tags: ["rudder"], tags: ["ruddervator"])
        comp_tags = [str(t).lower() for t in comp.get("parameters", {}).get("tags", [])] if isinstance(comp.get("parameters"), dict) else []
        if not cs_list:
            for tag_candidate in ("elevator", "rudder", "aileron", "flap", "elevon", "ruddervator", "vtail", "v-tail"):
                if tag_candidate in comp_tags:
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
            is_child_component = bool(cs.get("_child_component", False))

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
                # Explicit child surfaces are expressed in their local
                # attachment frame; embedded lifting-surface tags already use
                # AeroSandbox's down-positive convention.
                elevator_delta = -d_elevator if is_child_component else d_elevator
                delta_r += elevator_delta
                delta_l += elevator_delta
            elif cs_type_enum == ControlSurfaceType.RUDDER:
                delta_r += d_rudder
                delta_l -= d_rudder
            elif cs_type_enum == ControlSurfaceType.AILERON:
                delta_r += d_aileron
                delta_l -= d_aileron
            elif cs_type_enum == ControlSurfaceType.ELEVON:
                elevator_delta = -d_elevator if is_child_component else d_elevator
                delta_r += (elevator_delta + d_aileron)
                delta_l += (elevator_delta - d_aileron)
            elif cs_type_enum == ControlSurfaceType.RUDDERVATOR:
                elevator_delta = -d_elevator if is_child_component else d_elevator
                delta_r += (elevator_delta + d_rudder)
                delta_l += (elevator_delta - d_rudder)
            elif cs_type_enum == ControlSurfaceType.FLAP:
                pass

            # Span range [eta_start, eta_end]
            if "eta_start" in cs and "eta_end" in cs:
                eta_s = float(np.clip(float(cs["eta_start"]), 0.0, 1.0))
                eta_e = float(np.clip(float(cs["eta_end"]), 0.0, 1.0))
            elif "span_start" in cs and "span_end" in cs:
                s_s = float(cs["span_start"])
                s_e = float(cs["span_end"])
                span_mode = str(cs.get("span_mode") or "dimension").lower()
                if span_mode == "ratio" and abs(s_s) <= 1.0 and abs(s_e) <= 1.0:
                    eta_s = float(np.clip(s_s, 0.0, 1.0))
                    eta_e = float(np.clip(s_e, 0.0, 1.0))
                else:
                    # Dimension values are stored in millimetres in the
                    # component schema; accept metre-sized legacy values too.
                    if abs(s_s) > 5.0 or abs(s_e) > 5.0:
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
                eta_mid = 0.5 * (eta_s + eta_e)
                chord_at_mid = float(station_raw[0]["chord"])
                for s0, s1 in zip(station_raw[:-1], station_raw[1:]):
                    if s0["eta"] <= eta_mid <= s1["eta"]:
                        t_mid = float(np.clip(
                            (eta_mid - s0["eta"]) / max(s1["eta"] - s0["eta"], 1e-9),
                            0.0,
                            1.0,
                        ))
                        chord_at_mid = (1.0 - t_mid) * s0["chord"] + t_mid * s1["chord"]
                        break
                chord_frac = c_val / max(chord_at_mid, 0.01)
            chord_frac = float(np.clip(chord_frac, 0.05, 0.95))

            symmetry_mode = str(cs.get("symmetry_mode") or "auto").lower()
            # Let an explicit geometry declaration override the type's
            # default left/right convention.  This keeps the aerodynamic
            # conversion aligned with the geometry viewport for custom
            # elevons/flaps while retaining the standard auto behaviour.
            if symmetry_mode == "symmetric":
                delta_l = delta_r
            elif symmetry_mode in ("antisymmetric", "anti-symmetric"):
                delta_l = -delta_r

            parsed_cs.append({
                "tag": tag,
                "type": cs_type_enum.value,
                "symmetry_mode": symmetry_mode,
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
        def interp_station(eta_val: float, side: str = "right") -> dict[str, Any]:
            xyz_key = "xyz_le_left" if side == "left" else "xyz_le"
            for idx in range(len(station_raw) - 1):
                s0 = station_raw[idx]
                s1 = station_raw[idx + 1]
                if s0["eta"] <= eta_val <= s1["eta"] or math.isclose(eta_val, s0["eta"], abs_tol=1e-4) or math.isclose(eta_val, s1["eta"], abs_tol=1e-4):
                    d_eta = max(s1["eta"] - s0["eta"], 1e-6)
                    t = float(np.clip((eta_val - s0["eta"]) / d_eta, 0.0, 1.0))
                    xyz = (1.0 - t) * s0[xyz_key] + t * s1[xyz_key]
                    chord_v = (1.0 - t) * s0["chord"] + t * s1["chord"]
                    twist_v = (1.0 - t) * s0["twist"] + t * s1["twist"]
                    af = s0["airfoil"] if t < 0.5 else s1["airfoil"]
                    return {"xyz_le": xyz, "chord": chord_v, "twist": twist_v, "airfoil": af, "eta": eta_val}
            last = station_raw[-1]
            return {"xyz_le": last[xyz_key], "chord": last["chord"], "twist": last["twist"], "airfoil": last["airfoil"], "eta": eta_val}

        evaluated_stations = [interp_station(e, "right") for e in unique_etas]
        evaluated_stations_left = [interp_station(e, "left") for e in unique_etas]

        # Build Right and Left Wing cross sections with control deflections
        xsecs_right: list[asb.WingXSec] = []
        xsecs_left: list[asb.WingXSec] = []

        has_antisymmetric = False

        for st, st_left in zip(evaluated_stations, evaluated_stations_left):
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
                        af_r = af_r.add_control_surface(deflection=delta_r, hinge_point_x=hinge_pt)
                    if abs(delta_l) > 1e-4:
                        af_l = af_l.add_control_surface(deflection=delta_l, hinge_point_x=hinge_pt)

                    if abs(delta_r - delta_l) > 1e-4:
                        has_antisymmetric = True

                    # Keep the native AeroSandbox control-surface metadata on
                    # each controlled span section. Deflection remains encoded
                    # in the airfoil camber above (as required by VLM); the
                    # zero-deflection metadata supplies the semantic name and
                    # hinge location without double-counting it in AeroBuildup.
                    starts_controlled_section = (
                        (cs["eta_start"] <= e or math.isclose(e, cs["eta_start"], abs_tol=1e-4))
                        and e < cs["eta_end"]
                        and not math.isclose(e, cs["eta_end"], abs_tol=1e-4)
                    )
                    if starts_controlled_section:
                        is_symmetric = abs(delta_r - delta_l) <= 1e-4
                        cs_objs_r.append(
                            asb.ControlSurface(
                                name=cs["tag"],
                                symmetric=is_symmetric,
                                deflection=0.0,
                                hinge_point=hinge_pt,
                            )
                        )
                        cs_objs_l.append(
                            asb.ControlSurface(
                                name=cs["tag"],
                                symmetric=is_symmetric,
                                deflection=0.0,
                                hinge_point=hinge_pt,
                            )
                        )

            xyz = st["xyz_le"]
            xsecs_right.append(
                asb.WingXSec(
                    xyz_le=[float(xyz[0]), float(xyz[1]), float(xyz[2])],
                    chord=float(st["chord"]),
                    twist=float(st["twist"]),
                    airfoil=af_r,
                    control_surfaces=cs_objs_r,
                )
            )
            # Left side uses the fully transformed mirrored station.  For a
            # symmetric wing this is used as a regression/reference geometry;
            # AeroSandbox mirrors the right half at mesh/analysis time.
            xsecs_left.append(
                asb.WingXSec(
                    xyz_le=[float(st_left["xyz_le"][0]), float(st_left["xyz_le"][1]), float(st_left["xyz_le"][2])],
                    chord=float(st_left["chord"]),
                    twist=float(st_left["twist"]),
                    airfoil=af_l,
                    control_surfaces=cs_objs_l,
                )
            )

        name = str(comp.get("name") or comp.get("id") or "Wing")

        if mirror:
            # Wing.symmetric mirrors in the *global* XZ plane.  It is only
            # equivalent to Setuav's parent-frame mirror when the transformed
            # left stations are exactly that global reflection (e.g. a normal
            # horizontal wing).  A rolled/rotated V-tail must remain two real
            # asymmetric AeroSandbox wings.
            global_reflection_matches = all(
                np.allclose(
                    left.xyz_le,
                    [right.xyz_le[0], -right.xyz_le[1], right.xyz_le[2]],
                    atol=1e-9,
                )
                for right, left in zip(xsecs_right, xsecs_left)
            )
            if not has_antisymmetric and global_reflection_matches:
                return asb.Wing(name=name, xsecs=xsecs_right, symmetric=True)

            # Left wing xsecs are ordered from tip toward the root, matching
            # AeroSandbox's conventional left-side orientation.
            left_ordered = list(reversed(xsecs_left))
            return [
                asb.Wing(name=f"{name}_Right", xsecs=xsecs_right, symmetric=False),
                asb.Wing(name=f"{name}_Left", xsecs=left_ordered, symmetric=False),
            ]

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
    ) -> list[asb.Fuselage] | asb.Fuselage | None:
        """Convert fuselage sections while preserving segment order and section orientation.

        AeroSandbox represents fuselage sections as superellipses, so arbitrary Setuav
        polygon profiles are retained as bounded/superellipse approximations with the source
        profile metadata attached for downstream consumers.
        """
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
            local_pos, local_rot = self._local_transform(comp)
            base_pos, base_rot = local_pos, local_rot

        fuselages: list[asb.Fuselage] = []
        for segment_index, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            sections = seg.get("sections", [])
            xsecs: list[asb.FuselageXSec] = []
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
                w, h, shape = self._fuselage_profile_parameters(sec_prof)

                sec_rot_data = sec.get("rotation")
                sec_rot_data = sec_rot_data if isinstance(sec_rot_data, dict) else {}
                sec_roll = float(sec_rot_data.get("roll") if "roll" in sec_rot_data else sec_rot_data.get("x", 0.0))
                sec_pitch = float(sec_rot_data.get("pitch") if "pitch" in sec_rot_data else sec_rot_data.get("y", 0.0))
                sec_yaw = float(sec_rot_data.get("yaw") if "yaw" in sec_rot_data else sec_rot_data.get("z", 0.0))
                sec_rot = self._rotation_matrix_xyz(sec_roll, sec_pitch, sec_yaw)
                xyz_normal = base_rot @ sec_rot @ np.array([1.0, 0.0, 0.0])
                normal_norm = float(np.linalg.norm(xyz_normal))
                if normal_norm > 1e-9:
                    xyz_normal = xyz_normal / normal_norm

                xsecs.append(
                    asb.FuselageXSec(
                        xyz_c=[float(xyz_c[0]), float(xyz_c[1]), float(xyz_c[2])],
                        width=max(w, 1e-4),
                        height=max(h, 1e-4),
                        shape=float(shape),
                        xyz_normal=[float(xyz_normal[0]), float(xyz_normal[1]), float(xyz_normal[2])],
                        analysis_specific_options={
                            "setuav": {
                                "profile_type": p_type,
                                "source_profile": deepcopy(sec_prof),
                                "loft": deepcopy(seg.get("loft", {})),
                            }
                        },
                    )
                )

            if xsecs:
                segment_tag = str(seg.get("tag") or seg.get("name") or "").strip()
                base_name = str(comp.get("name") or comp.get("id") or "Fuselage")
                if len(segments) > 1:
                    segment_name = f"{base_name} - {segment_tag or f'Segment {segment_index + 1}'}"
                else:
                    segment_name = base_name
                fuselages.append(asb.Fuselage(name=segment_name, xsecs=xsecs))

        if not fuselages:
            return None
        return fuselages[0] if len(fuselages) == 1 else fuselages

    @staticmethod
    def _fuselage_profile_parameters(profile: dict[str, Any]) -> tuple[float, float, float]:
        """Map a Setuav section profile to AeroSandbox width, height and shape."""
        p_type = str(profile.get("type", "circle")).lower()
        if p_type == "circle":
            diameter = float(profile.get("diameter", 100.0)) / 1000.0
            return max(diameter, 1e-4), max(diameter, 1e-4), 2.0
        if p_type == "ellipse":
            return (
                max(float(profile.get("width", 100.0)) / 1000.0, 1e-4),
                max(float(profile.get("height", 100.0)) / 1000.0, 1e-4),
                2.0,
            )

        if p_type == "rectangle":
            width = float(profile.get("width", 100.0))
            height = float(profile.get("height", 100.0))
            corner_radius = max(float(profile.get("corner_radius", 0.0)), 0.0)
            shape = AeroSandboxEngine._rounded_profile_shape(width, height, corner_radius)
            return max(width / 1000.0, 1e-4), max(height / 1000.0, 1e-4), shape

        if p_type == "trapezoid":
            top = float(profile.get("top_width", 100.0))
            bottom = float(profile.get("bottom_width", top))
            height = float(profile.get("height", 100.0))
            # FuselageXSec cannot taper its Y extent within one section.  Keep
            # the exact envelope and use a square-ish superellipse.
            return max(max(top, bottom) / 1000.0, 1e-4), max(height / 1000.0, 1e-4), 1000.0

        if p_type == "triangle":
            width = float(profile.get("base_width", 100.0))
            height = float(profile.get("height", 100.0))
            # A superellipse cannot be triangular; shape just above one keeps
            # the section's pointed character while retaining its envelope.
            return max(width / 1000.0, 1e-4), max(height / 1000.0, 1e-4), 1.05

        if p_type == "polygon":
            vertices = profile.get("vertices")
            if isinstance(vertices, list) and vertices:
                ys = [float(v.get("y", 0.0)) for v in vertices if isinstance(v, dict)]
                zs = [float(v.get("z", 0.0)) for v in vertices if isinstance(v, dict)]
                if ys and zs:
                    return max((max(ys) - min(ys)) / 1000.0, 1e-4), max((max(zs) - min(zs)) / 1000.0, 1e-4), 1.05

        width = float(profile.get("width", 100.0)) / 1000.0
        height = float(profile.get("height", 100.0)) / 1000.0
        return max(width, 1e-4), max(height, 1e-4), 2.0

    @staticmethod
    def _rounded_profile_shape(width_mm: float, height_mm: float, corner_radius_mm: float) -> float:
        """Approximate a rounded rectangle with a superellipse exponent."""
        min_dim = max(min(width_mm, height_mm), 1e-6)
        radius_fraction = float(np.clip(2.0 * corner_radius_mm / min_dim, 0.0, 1.0))
        # r=0 is a square; r=min/2 is a circle.  The native fuselage model
        # cannot encode the straight/arc transition, so retain that continuum.
        if radius_fraction <= 1e-9:
            return 1000.0
        # A moderate exponent better matches the long straight portions and
        # rounded corners than a linear interpolation from square to circle.
        return max(2.01, 2.0 + 12.0 * (1.0 - radius_fraction) ** 2)

    def _resolve_airfoil(
        self,
        spec: Any,
        shaping: dict[str, Any] | None = None,
    ) -> asb.Airfoil:
        """Resolve any airfoil specification to a fully-populated asb.Airfoil with standard Selig coordinates."""
        # Preserve AeroSandbox's native NACA representation when no geometric
        # shaping is requested. Re-sampling it through Studio's display mesh
        # used to corrupt the lower trailing-edge endpoint and measurably
        # changed pitching moment relative to a direct AeroSandbox model.
        shaping_is_active = isinstance(shaping, dict) and (
            abs(float(shaping.get("te_thickness", 0.0))) >= 1e-6
            or abs(float(shaping.get("thickness_scale", 1.0)) - 1.0) >= 1e-6
            or abs(float(shaping.get("camber_scale", 1.0)) - 1.0) >= 1e-6
        )
        naca_code: str | None = None
        if isinstance(spec, str):
            match = re.fullmatch(r"\s*(?:naca[\s_-]*)?(\d{4,5})\s*", spec, re.IGNORECASE)
            if match:
                naca_code = match.group(1)
        elif isinstance(spec, dict):
            spec_type = str(spec.get("type") or "").strip().lower()
            code_value = str(spec.get("code") or spec.get("name") or "")
            match = re.fullmatch(r"\s*(?:naca[\s_-]*)?(\d{4,5})\s*", code_value, re.IGNORECASE)
            if spec_type == "naca" and match:
                naca_code = match.group(1)

        if naca_code and not shaping_is_active:
            return asb.Airfoil(f"naca{naca_code}")

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
