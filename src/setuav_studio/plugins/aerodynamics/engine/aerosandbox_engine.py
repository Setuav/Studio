"""AeroSandbox engine implementation for Setuav Studio."""
from __future__ import annotations

import logging
import math
from typing import Any

from .base import (
    AeroEngine,
    AeroResult,
    AnalysisMethod,
    AnalysisType,
    EngineCapabilities,
    FlightCondition,
    PolarPoint,
    ReferenceValues,
)
from setuav_studio.plugins.geometry.airfoil import (
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
            analysis_types=frozenset({AnalysisType.SINGLE_POINT, AnalysisType.ALPHA_SWEEP}),
            supports_fuselage=True,
            supports_control_surfaces=False,
        )

    def analyze(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod = AnalysisMethod.AERO_BUILDUP,
        settings: dict[str, Any] | None = None,
    ) -> AeroResult:
        if not HAS_AEROSANDBOX:
            raise RuntimeError(
                "AeroSandbox library is not installed. Please install it using 'pip install aerosandbox'."
            )

        airplane = self._build_airplane(components)
        if not airplane.wings:
            raise ValueError("No valid lifting surfaces found in project for aerodynamic analysis.")

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

        for alpha in alphas:
            op = asb.OperatingPoint(
                atmosphere=atmosphere,
                velocity=condition.velocity,
                alpha=float(alpha),
                beta=float(condition.beta),
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
            cm = float(np.ravel(res.get("Cm", 0.0))[0]) if "Cm" in res else 0.0

            cd_ind = 0.0
            cd_pro = 0.0
            qs = 0.5 * atmosphere.density() * (condition.velocity ** 2) * ref_area
            if qs > 0:
                if "D_induced" in res:
                    cd_ind = float(np.ravel(res["D_induced"])[0]) / qs
                if "D_profile" in res:
                    cd_pro = float(np.ravel(res["D_profile"])[0]) / qs

            ld = cl / cd if abs(cd) > 1e-7 else 0.0

            polar_points.append(
                PolarPoint(
                    alpha=float(alpha),
                    cl=cl,
                    cd=cd,
                    cm=cm,
                    cd_induced=cd_ind,
                    cd_profile=cd_pro,
                    cl_over_cd=ld,
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

        rho = float(atmosphere.density())
        mu = float(atmosphere.dynamic_viscosity())
        reynolds = (rho * condition.velocity * mean_chord / mu) if mu > 0 else 0.0
        oswald = float(sum(oswald_list) / len(oswald_list)) if oswald_list else None

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
            oswald_efficiency=oswald,
            raw={"airplane": airplane, "velocity": condition.velocity},
        )

    def _build_airplane(self, components: list[dict[str, Any]]) -> asb.Airplane:
        """Convert Setuav Studio components list to AeroSandbox Airplane object."""
        wings: list[asb.Wing] = []
        fuselages: list[asb.Fuselage] = []

        for comp in components:
            if not isinstance(comp, dict):
                continue
            comp_type = comp.get("type", "")
            if comp_type == "org.setuav.core:lifting-surface":
                wing = self._convert_lifting_surface(comp)
                if wing is not None:
                    wings.append(wing)
            elif comp_type == "org.setuav.core:fuselage":
                fuselage = self._convert_fuselage(comp)
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

    def _convert_lifting_surface(self, comp: dict[str, Any]) -> asb.Wing | None:
        """Convert a single lifting surface dictionary to AeroSandbox Wing with full 3D transforms."""
        params = comp.get("parameters")
        params = params if isinstance(params, dict) else {}
        geometry = params.get("geometry")
        geometry = geometry if isinstance(geometry, dict) else {}
        profiles = geometry.get("profiles")

        if not isinstance(profiles, list) or len(profiles) < 2:
            return None

        # Component transform
        comp_transform = comp.get("transform")
        comp_transform = comp_transform if isinstance(comp_transform, dict) else {}
        pos = comp_transform.get("position")
        pos = pos if isinstance(pos, dict) else {}
        rot = comp_transform.get("rotation")
        rot = rot if isinstance(rot, dict) else {}

        mirror = bool(geometry.get("mirror", False) or comp.get("mirror", False))

        # Position in meters (lock Y to 0 for symmetric/centerline attached wings)
        attach_pos = np.array([
            float(pos.get("x", 0.0)) / 1000.0,
            0.0 if mirror else float(pos.get("y", 0.0)) / 1000.0,
            float(pos.get("z", 0.0)) / 1000.0,
        ])

        # Rotation angles in degrees (roll, pitch, yaw)
        roll_deg = float(rot.get("roll") if "roll" in rot else rot.get("x", 0.0))
        pitch_deg = float(rot.get("pitch") if "pitch" in rot else rot.get("y", 0.0))
        yaw_deg = float(rot.get("yaw") if "yaw" in rot else rot.get("z", 0.0))
        attach_rot = self._rotation_matrix_xyz(roll_deg, pitch_deg, yaw_deg)

        xsecs: list[asb.WingXSec] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            prof_pos = profile.get("position")
            prof_pos = prof_pos if isinstance(prof_pos, dict) else {}
            prof_rot = profile.get("rotation")
            prof_rot = prof_rot if isinstance(prof_rot, dict) else {}

            # Raw profile position relative to component root (in meters)
            raw_xyz = np.array([
                float(prof_pos.get("x", 0.0)) / 1000.0,
                float(prof_pos.get("y", 0.0)) / 1000.0,
                float(prof_pos.get("z", 0.0)) / 1000.0,
            ])

            # Apply component 3D rotation and translation
            xyz_le = attach_rot @ raw_xyz + attach_pos

            chord = float(profile.get("chord", 100.0)) / 1000.0

            # Twist / Pitch angle: pitch rotation of profile + component pitch
            prof_pitch = float(
                profile.get("twist")
                if "twist" in profile
                else (
                    prof_rot.get("pitch")
                    if "pitch" in prof_rot
                    else (prof_rot.get("y") if "y" in prof_rot else prof_rot.get("x", 0.0))
                )
            )
            total_twist = prof_pitch + pitch_deg

            airfoil_spec = profile.get("airfoil")
            airfoil = self._resolve_airfoil(airfoil_spec, shaping=geometry.get("airfoil_shaping"))

            xsecs.append(
                asb.WingXSec(
                    xyz_le=[float(xyz_le[0]), float(xyz_le[1]), float(xyz_le[2])],
                    chord=max(chord, 1e-4),
                    twist=total_twist,
                    airfoil=airfoil,
                )
            )

        if len(xsecs) < 2:
            return None

        name = str(comp.get("name") or comp.get("id") or "Wing")

        return asb.Wing(
            name=name,
            xsecs=xsecs,
            symmetric=mirror,
        )

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

    def _convert_fuselage(self, comp: dict[str, Any]) -> asb.Fuselage | None:
        """Convert a fuselage component dictionary to AeroSandbox Fuselage."""
        params = comp.get("parameters")
        params = params if isinstance(params, dict) else {}
        geometry = params.get("geometry")
        geometry = geometry if isinstance(geometry, dict) else {}
        segments = geometry.get("segments")

        if not isinstance(segments, list) or not segments:
            return None

        comp_transform = comp.get("transform")
        comp_transform = comp_transform if isinstance(comp_transform, dict) else {}
        pos = comp_transform.get("position")
        pos = pos if isinstance(pos, dict) else {}
        base_x = float(pos.get("x", 0.0)) / 1000.0
        base_y = float(pos.get("y", 0.0)) / 1000.0
        base_z = float(pos.get("z", 0.0)) / 1000.0

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

                x = float(sec_pos.get("x", 0.0)) / 1000.0 + base_x
                y = float(sec_pos.get("y", 0.0)) / 1000.0 + base_y
                z = float(sec_pos.get("z", 0.0)) / 1000.0 + base_z

                p_type = str(sec_prof.get("type", "circle")).lower()
                if p_type == "circle":
                    dia = float(sec_prof.get("diameter", 100.0)) / 1000.0
                    w = h = max(dia, 1e-4)
                else:
                    w = float(sec_prof.get("width", 100.0)) / 1000.0
                    h = float(sec_prof.get("height", 100.0)) / 1000.0

                xsecs.append(
                    asb.FuselageXSec(
                        xyz_c=[x, y, z],
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
