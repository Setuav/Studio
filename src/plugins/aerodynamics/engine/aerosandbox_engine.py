"""AeroSandbox engine implementation for Setuav Studio."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from plugins.geometry.engine.airfoil import (
    airfoil_label,
    apply_airfoil_shaping,
    sample_airfoil_points,
)
from setuav_studio.utilities.transform import euler_to_matrix, resolve_world_transform

from .aerosandbox_analysis import AeroSandboxAnalysisMixin
from .aerosandbox_geometry import AeroSandboxGeometryMixin, metric_frame
from .base import (
    AeroEngine,
    AnalysisMethod,
    AnalysisType,
    EngineCapabilities,
    FlightCondition,
)

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


class AeroSandboxEngine(AeroSandboxAnalysisMixin, AeroSandboxGeometryMixin, AeroEngine):
    """AeroSandbox engine for buildup, vortex, and lifting-line analyses."""

    @property
    def name(self) -> str:
        return "AeroSandbox"

    def is_available(self) -> bool:
        return HAS_AEROSANDBOX

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            methods=frozenset(
                {
                    AnalysisMethod.AERO_BUILDUP,
                    AnalysisMethod.VLM,
                    AnalysisMethod.LIFTING_LINE,
                }
            ),
            analysis_types=frozenset(
                {
                    AnalysisType.SINGLE_POINT,
                    AnalysisType.ALPHA_SWEEP,
                    AnalysisType.BETA_SWEEP,
                    AnalysisType.MULTI_SWEEP,
                    AnalysisType.STABILITY_DERIVATIVES,
                    AnalysisType.CONTROL_CHANNEL,
                }
            ),
            supports_fuselage=True,
            supports_control_surfaces=True,
        )

    def _build_airplane(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition | None = None,
        xyz_ref: tuple[float, float, float] | None = None,
        control_encoding: str = "native",
    ) -> Any:
        """Convert Setuav Studio components list to AeroSandbox Airplane object with attachment hierarchy and control surfaces."""
        wings: list[Any] = []
        fuselages: list[Any] = []

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
                wing_res = self._convert_lifting_surface(
                    comp,
                    comp_by_id=comp_by_id,
                    condition=condition,
                    control_encoding=control_encoding,
                )
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

    def _compute_wing_area(self, wing: Any) -> float:
        area = 0.0
        for i in range(len(wing.xsecs) - 1):
            x1 = wing.xsecs[i]
            x2 = wing.xsecs[i + 1]
            dy = abs(x2.xyz_le[1] - x1.xyz_le[1])
            dz = abs(x2.xyz_le[2] - x1.xyz_le[2])
            span_seg = math.sqrt(dy * dy + dz * dz)
            area += 0.5 * (x1.chord + x2.chord) * span_seg
        return area * (2.0 if wing.symmetric else 1.0)

    def _compute_wing_span_and_area(self, wing: Any) -> tuple[float, float]:
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
        comp_by_id: dict[str, dict[str, Any]],
    ) -> Any:
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

        base_pos, base_rot = metric_frame(*resolve_world_transform(str(comp["id"]), comp_by_id))

        fuselages: list[Any] = []
        for segment_index, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            sections = seg.get("sections", [])
            xsecs: list[Any] = []
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                sec_pos = sec.get("position")
                sec_pos = sec_pos if isinstance(sec_pos, dict) else {}
                sec_prof = sec.get("profile")
                sec_prof = sec_prof if isinstance(sec_prof, dict) else {}

                raw_xyz = np.array(
                    [
                        float(sec_pos.get("x", 0.0)) / 1000.0,
                        float(sec_pos.get("y", 0.0)) / 1000.0,
                        float(sec_pos.get("z", 0.0)) / 1000.0,
                    ]
                )
                xyz_c = base_rot @ raw_xyz + base_pos

                p_type = str(sec_prof.get("type", "circle")).lower()
                w, h, shape = self._fuselage_profile_parameters(sec_prof)

                xyz_normal = self._fuselage_section_normal(sec, base_rot)

                xsecs.append(
                    asb.FuselageXSec(
                        xyz_c=[float(xyz_c[0]), float(xyz_c[1]), float(xyz_c[2])],
                        width=max(w, 1e-4),
                        height=max(h, 1e-4),
                        shape=float(shape),
                        xyz_normal=[
                            float(xyz_normal[0]),
                            float(xyz_normal[1]),
                            float(xyz_normal[2]),
                        ],
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
                segment_tag = str(seg.get("tag") or "").strip()
                base_name = self._component_label(comp)
                if len(segments) > 1:
                    segment_name = f"{base_name} - {segment_tag or f'Segment {segment_index + 1}'}"
                else:
                    segment_name = base_name
                fuselages.append(asb.Fuselage(name=segment_name, xsecs=xsecs))

        if not fuselages:
            return None
        return fuselages[0] if len(fuselages) == 1 else fuselages

    def _fuselage_section_normal(self, section: dict[str, Any], base_rotation: Any) -> Any:
        rotation = section.get("rotation")
        rotation = rotation if isinstance(rotation, dict) else {}
        local_rotation = np.array(
            euler_to_matrix(
                float(rotation.get("x", 0.0)),
                float(rotation.get("y", 0.0)),
                float(rotation.get("z", 0.0)),
            )
        )
        normal = base_rotation @ local_rotation @ np.array([1.0, 0.0, 0.0])
        length = float(np.linalg.norm(normal))
        return normal / length if length > 1e-9 else normal

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
                    return (
                        max((max(ys) - min(ys)) / 1000.0, 1e-4),
                        max((max(zs) - min(zs)) / 1000.0, 1e-4),
                        1.05,
                    )

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
        spec: object,
        shaping: dict[str, Any] | None = None,
    ) -> Any:
        """Resolve a canonical airfoil spec to an asb.Airfoil with standard Selig coordinates."""
        name = airfoil_label(spec)
        # AeroSandbox generates NACA 4-digit sections analytically; keep that
        # native representation when no geometric shaping is requested.
        # Re-sampling it through Studio's display mesh perturbs the lower
        # trailing-edge endpoint and measurably changes the pitching moment
        # relative to a direct AeroSandbox model. NACA 5-digit sections use
        # Studio's generator, the same coordinates the geometry is built from.
        shaping_is_active = isinstance(shaping, dict) and (
            abs(float(shaping.get("te_thickness", 0.0))) >= 1e-6
            or abs(float(shaping.get("thickness_scale", 1.0)) - 1.0) >= 1e-6
            or abs(float(shaping.get("camber_scale", 1.0)) - 1.0) >= 1e-6
        )
        if isinstance(spec, str) and len(spec) == 4 and not shaping_is_active:
            return asb.Airfoil(f"naca{spec}")

        # 1. Sample 2D normalized coordinates of the spec
        raw_coords = sample_airfoil_points(spec)

        # 2. Apply airfoil shaping (TE blunting, thickness scale, camber scale) if present
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

        # 3. Normalize to Selig format (Upper TE [x~1, y>=0] -> LE [x=min] -> Lower TE [x~1, y<=0])
        coords_arr = np.array([[float(p[0]), float(p[1])] for p in raw_coords], dtype=float)
        coords_arr = self._to_selig_format(coords_arr)

        # 4. Construct asb.Airfoil directly from 2D coordinates array
        return asb.Airfoil(name=name, coordinates=coords_arr)

    @staticmethod
    def _to_selig_format(coords: Any) -> Any:
        """Ensure airfoil coordinates are in standard Selig format: Upper TE -> LE -> Lower TE."""
        if len(coords) < 3:
            return coords

        min_x_idx = int(np.argmin(coords[:, 0]))
        x_min = float(coords[min_x_idx, 0])
        x_max = float(np.max(coords[:, 0]))

        # A loop whose first point lies in the leading-edge half runs
        # LE -> upper TE -> lower LE; the leading-edge point itself need not be
        # the first one when the camber line slopes at the nose.
        if float(coords[0, 0]) - x_min < 0.5 * (x_max - x_min):
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

    def _compute_reference_geometry(self, airplane: Any) -> tuple[float, float]:
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
