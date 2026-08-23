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
    EngineCapabilities,
    FlightCondition,
    MultiDimensionalSweepResult,
    PolarPoint,
    PropulsionPoint,
    ReferenceValues,
    SweepVariable,
)
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
            methods=frozenset({AnalysisMethod.VLM, AnalysisMethod.AERO_BUILDUP}),
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
        method: AnalysisMethod = AnalysisMethod.AERO_BUILDUP,
        settings: dict[str, Any] | None = None,
        progress_callback: Any | None = None,
    ) -> AeroResult:
        if not HAS_AEROSANDBOX:
            raise RuntimeError(
                "AeroSandbox library is not installed. Please install it using 'pip install aerosandbox'."
            )

        airplane = self._build_airplane(components, condition=condition)
        if not airplane.wings:
            raise ValueError("No valid lifting surfaces found in project for aerodynamic analysis.")

        comp_by_id = {
            str(comp.get("id")): comp
            for comp in components
            if isinstance(comp, dict) and comp.get("id")
        }
        propulsion_points = self._extract_propulsion_points(components, comp_by_id)

        atmosphere = asb.Atmosphere(altitude=condition.altitude)

        if condition.alpha_steps <= 1:
            alphas = [float(condition.alpha)]
        else:
            alphas = [
                float(a)
                for a in np.linspace(
                    condition.alpha_min, condition.alpha_max, condition.alpha_steps
                )
            ]

        span, area = self._compute_reference_geometry(airplane)
        mean_chord = area / span if span > 0 else 0.0
        ref = ReferenceValues(
            s_ref=area,
            b_ref=span,
            c_ref=mean_chord,
            x_cg=float(airplane.xyz_ref[0]) if hasattr(airplane, "xyz_ref") and airplane.xyz_ref is not None else 0.0,
            y_cg=float(airplane.xyz_ref[1]) if hasattr(airplane, "xyz_ref") and airplane.xyz_ref is not None else 0.0,
            z_cg=float(airplane.xyz_ref[2]) if hasattr(airplane, "xyz_ref") and airplane.xyz_ref is not None else 0.0,
        )

        polar_points: list[PolarPoint] = []
        oswald_list: list[float] = []

        ref_area = area if area > 0 else 1.0
        total_steps = len(alphas)

        rho = float(atmosphere.density())
        mu = float(atmosphere.dynamic_viscosity())
        speed_of_sound = float(atmosphere.speed_of_sound())
        mach = condition.velocity / speed_of_sound if speed_of_sound > 0 else 0.0
        q_inf = 0.5 * rho * (condition.velocity ** 2)
        qs = q_inf * ref_area
        reynolds = (rho * condition.velocity * mean_chord / mu) if mu > 0 else 0.0

        for idx, alpha in enumerate(alphas, start=1):
            if progress_callback:
                progress_callback(idx, total_steps, f"α={alpha:.1f}°")

            op = asb.OperatingPoint(
                atmosphere=atmosphere,
                velocity=condition.velocity,
                alpha=float(alpha),
                beta=float(condition.beta),
                p=float(condition.p),
                q=float(condition.q),
                r=float(condition.r),
            )

            if method == AnalysisMethod.VLM:
                solver = asb.VortexLatticeMethod(
                    airplane=airplane,
                    op_point=op,
                    spanwise_resolution=settings.get("spanwise_resolution", 12) if settings else 12,
                    chordwise_resolution=settings.get("chordwise_resolution", 6) if settings else 6,
                )
                res = solver.run()
            else:
                model_size = settings.get("model_size", "small") if settings else "small"
                solver = asb.AeroBuildup(
                    airplane=airplane,
                    op_point=op,
                    include_wave_drag=settings.get("include_wave_drag", True) if settings else True,
                    model_size=model_size,
                )
                res = solver.run()

            cl = float(np.ravel(res["CL"])[0]) if "CL" in res else 0.0
            cd = float(np.ravel(res["CD"])[0]) if "CD" in res else 0.0
            cy_wind = float(np.ravel(res.get("CY", 0.0))[0]) if "CY" in res else 0.0
            cl_roll = float(np.ravel(res.get("Cl", 0.0))[0]) if "Cl" in res else 0.0
            cm = float(np.ravel(res.get("Cm", 0.0))[0]) if "Cm" in res else 0.0
            cn = float(np.ravel(res.get("Cn", 0.0))[0]) if "Cn" in res else 0.0

            # Dimensional wind forces
            lift = float(np.ravel(res["L"])[0]) if "L" in res else (qs * cl)
            drag = float(np.ravel(res["D"])[0]) if "D" in res else (qs * cd)
            sideforce = float(np.ravel(res["Y"])[0]) if "Y" in res else (qs * cy_wind)

            # Dimensional body forces & moments
            if "F_b" in res and res["F_b"] is not None:
                fb = res["F_b"]
                fx_b = float(np.ravel(fb[0])[0])
                fy_b = float(np.ravel(fb[1])[0])
                fz_b = float(np.ravel(fb[2])[0])
            else:
                a_rad = math.radians(float(alpha))
                b_rad = math.radians(float(condition.beta))
                ca, sa = math.cos(a_rad), math.sin(a_rad)
                cb, sb = math.cos(b_rad), math.sin(b_rad)
                fx_b = -drag * ca * cb + lift * sa - sideforce * ca * sb
                fy_b = sideforce * cb - drag * sb
                fz_b = -lift * ca - drag * sa * cb - sideforce * sa * sb

            if "M_b" in res and res["M_b"] is not None:
                mb = res["M_b"]
                mx_b = float(np.ravel(mb[0])[0])
                my_b = float(np.ravel(mb[1])[0])
                mz_b = float(np.ravel(mb[2])[0])
            else:
                mx_b = qs * span * cl_roll
                my_b = qs * mean_chord * cm
                mz_b = qs * span * cn

            if "M_w" in res and res["M_w"] is not None:
                mw = res["M_w"]
                mx_w = float(np.ravel(mw[0])[0])
                my_w = float(np.ravel(mw[1])[0])
                mz_w = float(np.ravel(mw[2])[0])
            else:
                mx_w, my_w, mz_w = mx_b, my_b, mz_b

            # Body force coefficients
            cx = (fx_b / qs) if qs > 0 else 0.0
            cy = (fy_b / qs) if qs > 0 else cy_wind
            cz = (fz_b / qs) if qs > 0 else 0.0

            cd_ind = 0.0
            cd_pro = 0.0
            cd_wave = 0.0
            if qs > 0:
                if "D_induced" in res:
                    cd_ind = float(np.ravel(res["D_induced"])[0]) / qs
                if "D_profile" in res:
                    cd_pro = float(np.ravel(res["D_profile"])[0]) / qs
                if "D_wave" in res:
                    cd_wave = float(np.ravel(res["D_wave"])[0]) / qs

            ld = cl / cd if abs(cd) > 1e-7 else 0.0

            forces_moments = AeroForcesMoments(
                fx_b=fx_b,
                fy_b=fy_b,
                fz_b=fz_b,
                lift=lift,
                drag=drag,
                sideforce=sideforce,
                mx_b=mx_b,
                my_b=my_b,
                mz_b=mz_b,
                mx_w=mx_w,
                my_w=my_w,
                mz_w=mz_w,
            )

            state = AeroState(
                alpha=float(alpha),
                beta=float(condition.beta),
                p=float(condition.p),
                q=float(condition.q),
                r=float(condition.r),
                velocity=float(condition.velocity),
                altitude=float(condition.altitude),
                mach=mach,
                reynolds=reynolds,
                dynamic_pressure=q_inf,
                control_deflections=dict(condition.control_deflections),
            )

            polar_points.append(
                PolarPoint(
                    alpha=float(alpha),
                    cl=cl,
                    cd=cd,
                    cm=cm,
                    cd_induced=cd_ind,
                    cd_profile=cd_pro,
                    cl_over_cd=ld,
                    cx=cx,
                    cy=cy,
                    cz=cz,
                    cl_roll=cl_roll,
                    cn=cn,
                    cd_wave=cd_wave,
                    beta=float(condition.beta),
                    p=float(condition.p),
                    q=float(condition.q),
                    r=float(condition.r),
                    forces_moments=forces_moments,
                    state=state,
                    velocity=float(condition.velocity),
                    altitude=float(condition.altitude),
                    mach=mach,
                    reynolds=reynolds,
                    dynamic_pressure=q_inf,
                    control_deflections=dict(condition.control_deflections),
                    converged=True,
                )
            )

            wing_comps = res.get("wing_aero_components", [])
            if wing_comps:
                oswald_list.append(float(wing_comps[0].oswalds_efficiency))

        cl_values = [p.cl for p in polar_points]
        cd_values = [p.cd for p in polar_points]
        ld_values = [p.cl_over_cd for p in polar_points]

        cl_max = max(cl_values) if cl_values else 0.0
        cl_max_alpha = polar_points[cl_values.index(cl_max)].alpha if cl_values else 0.0
        cd_min = min(cd_values) if cd_values else 0.0
        ld_max = max(ld_values) if ld_values else 0.0
        ld_max_alpha = polar_points[ld_values.index(ld_max)].alpha if ld_values else 0.0

        oswald = float(sum(oswald_list) / len(oswald_list)) if oswald_list else None

        sweep_result: MultiDimensionalSweepResult | None = None
        if len(alphas) > 1:
            sweep_result = MultiDimensionalSweepResult(
                variables=[SweepVariable(name="alpha", values=alphas, unit="deg")],
                points=list(polar_points),
                grid_shape=(len(alphas),),
            )

        return AeroResult(
            method=method,
            engine_name=self.name,
            polar_points=polar_points,
            cl_max=cl_max,
            cl_max_alpha=cl_max_alpha,
            cd_min=cd_min,
            ld_max=ld_max,
            ld_max_alpha=ld_max_alpha,
            reference=ref,
            reynolds=reynolds,
            mach=mach,
            dynamic_pressure=q_inf,
            oswald_efficiency=oswald,
            sweep_result=sweep_result,
            condition=condition,
            raw={
                "airplane": airplane,
                "velocity": condition.velocity,
                "propulsion_points": [p.to_dict() for p in propulsion_points],
            },
            propulsion_points=propulsion_points,
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

        # Compute span coordinates eta in [0, 1]
        y_vals = [s["local_y"] for s in station_raw]
        y_min, y_max = min(y_vals), max(y_vals)
        span_length = max(y_max - y_min, 1e-4)

        for s in station_raw:
            s["eta"] = (s["local_y"] - y_min) / span_length

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

        # Parse control surface definitions
        parsed_cs: list[dict[str, Any]] = []
        for cs in cs_list:
            cs_type = str(cs.get("type") or "flap").lower()
            tag = str(cs.get("tag") or cs.get("name") or cs.get("id") or cs_type)
            cs_id = str(cs.get("id") or tag)

            # Deflection angle resolution (checking condition override first)
            deflection = float(cs.get("deflection", 0.0))
            if condition and condition.control_deflections:
                for k, v in condition.control_deflections.items():
                    k_clean = k.strip().lower()
                    if k_clean in (tag.lower(), cs_type, cs_id.lower()):
                        deflection = float(v)
                        break

            # Span range [eta_start, eta_end]
            if "eta_start" in cs and "eta_end" in cs:
                eta_s = float(np.clip(float(cs["eta_start"]), 0.0, 1.0))
                eta_e = float(np.clip(float(cs["eta_end"]), 0.0, 1.0))
            elif "span_start" in cs and "span_end" in cs:
                eta_s = float(np.clip((float(cs["span_start"]) - y_min) / span_length, 0.0, 1.0))
                eta_e = float(np.clip((float(cs["span_end"]) - y_min) / span_length, 0.0, 1.0))
            else:
                eta_s, eta_e = 0.0, 1.0

            if eta_s > eta_e:
                eta_s, eta_e = eta_e, eta_s

            # Chord fraction
            chord_frac = float(cs.get("chord_fraction", 0.25))
            if cs.get("chord_mode") == "dimension" and "chord" in cs:
                chord_frac = float(cs["chord"]) / (span_length * 0.25)
            chord_frac = float(np.clip(chord_frac, 0.05, 0.95))

            sym_mode = str(cs.get("symmetry_mode") or "auto").lower()
            if sym_mode == "auto":
                sym_mode = "antisymmetric" if cs_type in ("aileron", "elevon") else "symmetric"

            parsed_cs.append({
                "tag": tag,
                "type": cs_type,
                "eta_start": eta_s,
                "eta_end": eta_e,
                "chord_fraction": chord_frac,
                "deflection": deflection,
                "symmetry_mode": sym_mode,
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
                    delta_r = cs["deflection"]
                    delta_l = -cs["deflection"] if cs["symmetry_mode"] == "antisymmetric" else cs["deflection"]
                    cf = cs["chord_fraction"]
                    hinge_pt = 1.0 - cf

                    if abs(delta_r) > 1e-4:
                        af_r = base_af.add_control_surface(deflection=delta_r, hinge_point_x=hinge_pt)
                    if abs(delta_l) > 1e-4:
                        af_l = base_af.add_control_surface(deflection=delta_l, hinge_point_x=hinge_pt)

                    if cs["symmetry_mode"] == "antisymmetric" and abs(cs["deflection"]) > 1e-4:
                        has_antisymmetric = True

                    cs_objs_r.append(asb.ControlSurface(name=cs["tag"], deflection=delta_r, hinge_point=hinge_pt, symmetric=(cs["symmetry_mode"] == "symmetric")))
                    cs_objs_l.append(asb.ControlSurface(name=cs["tag"], deflection=delta_l, hinge_point=hinge_pt, symmetric=(cs["symmetry_mode"] == "symmetric")))

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
