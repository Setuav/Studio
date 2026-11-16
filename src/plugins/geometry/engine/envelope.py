"""Geometry-derived physical envelope computation for CAD components.

Implements station-by-station trapezoidal (frustum / yamuk) slice integration
for fuselages and lifting surfaces, deriving exact volumetric centroids,
slice breakdowns, 3D inertia tensors, total volume, and cross-section bboxes.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from setuav_studio.model.expression import set_expression

from .airfoil import apply_airfoil_shaping, sample_airfoil_points
from .fuselage_geometry import build_fuselage_geometry, sample_profile
from .lifting_surface_geometry import _build_profile_section, build_lifting_surface_geometry
from .transforms import number_field, section_transform, transform_point

_LIFTING_SURFACE_TYPE = "org.setuav.core:lifting-surface"
_FUSELAGE_TYPE = "org.setuav.core:fuselage"
_CONTROL_SURFACE_TYPE = "org.setuav.core:control-surface"

GEOMETRY_COMPONENT_TYPES = frozenset(
    {
        _LIFTING_SURFACE_TYPE,
        _FUSELAGE_TYPE,
        _CONTROL_SURFACE_TYPE,
    }
)


def compute_geometry_envelope(
    component: dict[str, Any],
    surface: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compute local 3D physical envelope (with trapezoidal slices) from CAD geometry."""
    ctype = str(component.get("type") or "")
    if ctype == _LIFTING_SURFACE_TYPE:
        return _compute_lifting_surface_envelope(component)
    if ctype == _FUSELAGE_TYPE:
        return _compute_fuselage_envelope(component)
    if ctype == _CONTROL_SURFACE_TYPE:
        return _compute_control_surface_envelope(component, surface)
    return None


def sync_component_envelope(
    component: dict[str, Any],
    surface: dict[str, Any] | None = None,
) -> bool:
    """Compute and update the envelope on the component if applicable.

    Returns True if the component envelope was changed.
    """
    env = compute_geometry_envelope(component, surface)
    if env is None:
        return False
    if component.get("envelope") == env:
        return False
    component["envelope"] = env
    return True


def sync_project_geometry_envelopes(project: Any) -> int:
    """Ensure all geometry components in the project document have up-to-date envelopes.

    Returns the count of components whose envelope was updated.
    """
    if project is None:
        return 0
    from setuav_studio.project.document import ProjectDocument

    data = project.data if isinstance(project, ProjectDocument) else project
    if not isinstance(data, dict):
        return 0
    components = data.get("components")
    if not isinstance(components, list):
        return 0

    all_components = list(components)

    by_id: dict[str, dict[str, Any]] = {
        str(c.get("id")): c for c in all_components if isinstance(c, dict) and c.get("id")
    }

    updated = 0
    for comp in all_components:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "")
        if ctype not in GEOMETRY_COMPONENT_TYPES:
            continue
        target_id = comp.get("attach_to")
        surface = by_id.get(str(target_id)) if target_id else None
        if sync_component_envelope(comp, surface):
            updated += 1

    return updated


# =============================================================================
# Mathematical Helpers
# =============================================================================


def _dict_field(owner: dict[str, Any], key: str) -> dict[str, Any]:
    value = owner.get(key)
    return value if isinstance(value, dict) else {}


def _position(position: dict[str, Any]) -> tuple[float, float, float]:
    return (
        number_field(position, "x", 0.0),
        number_field(position, "y", 0.0),
        number_field(position, "z", 0.0),
    )


def _polygon_cross_section_properties(
    vertices: list[tuple[float, float]] | tuple[tuple[float, float], ...],
) -> tuple[float, float, float, float, float, float]:
    """Compute (area, cx, cz, izz_c, ixx_c, ixz_c) of a 2D closed polygon using Green's theorem.

    izz_c: centroidal second moment about Z (chordwise, int (x - cx)^2 dA)
    ixx_c: centroidal second moment about X (thicknesswise, int (z - cz)^2 dA)
    ixz_c: centroidal product moment of area (int (x - cx)(z - cz) dA)
    """
    n = len(vertices)
    if n < 3:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    area_acc = 0.0
    cx_acc = 0.0
    cz_acc = 0.0
    izz_acc = 0.0
    ixx_acc = 0.0
    ixz_acc = 0.0
    for i in range(n):
        x1, z1 = vertices[i]
        x2, z2 = vertices[(i + 1) % n]
        cross = x1 * z2 - x2 * z1
        area_acc += cross
        cx_acc += (x1 + x2) * cross
        cz_acc += (z1 + z2) * cross
        izz_acc += cross * (x1 * x1 + x1 * x2 + x2 * x2)
        ixx_acc += cross * (z1 * z1 + z1 * z2 + z2 * z2)
        ixz_acc += cross * (2.0 * x1 * z1 + x1 * z2 + x2 * z1 + 2.0 * x2 * z2)

    signed_area = area_acc * 0.5
    area = abs(signed_area)
    if area < 1e-9:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    sign = 1.0 if signed_area >= 0.0 else -1.0
    cx = cx_acc / (6.0 * signed_area)
    cz = cz_acc / (6.0 * signed_area)

    izz_0 = (izz_acc / 12.0) * sign
    ixx_0 = (ixx_acc / 12.0) * sign
    ixz_0 = (ixz_acc / 24.0) * sign

    izz_c = max(izz_0 - area * (cx**2), 0.0)
    ixx_c = max(ixx_0 - area * (cz**2), 0.0)
    ixz_c = ixz_0 - area * cx * cz

    return area, cx, cz, izz_c, ixx_c, ixz_c


def _profile_chord(profile: dict[str, Any]) -> float:
    chord = number_field(profile, "chord")
    if chord <= 0.0:
        raise ValueError(f"Lifting surface profile chord must be positive, got {chord}")
    return chord


def _mean_gyration_sq(moments: tuple[tuple[float, float], ...]) -> float:
    """Average ``moment / area`` over the sections with a non-zero area."""
    values = [moment / area for moment, area in moments if area > 0.0]
    if not values:
        raise ValueError("Radius of gyration needs at least one section with area")
    return sum(values) / len(values)


def _polygon_area_and_centroid(
    vertices: list[tuple[float, float]] | tuple[tuple[float, float], ...],
) -> tuple[float, float, float]:
    """Compute (area, cx, cz) of a 2D closed polygon using the Shoelace formula."""
    area, cx, cz, _, _, _ = _polygon_cross_section_properties(vertices)
    return area, cx, cz


def _compute_section_properties(
    profile: dict[str, Any],
) -> tuple[float, float, float, float, float]:
    """Compute (area, width, height, cy_rel, cz_rel) for a fuselage profile."""
    profile_type = profile.get("type")

    if profile_type == "circle":
        d = number_field(profile, "diameter")
        r = d * 0.5
        return math.pi * r * r, d, d, 0.0, 0.0
    if profile_type == "ellipse":
        w = number_field(profile, "width")
        h = number_field(profile, "height")
        return math.pi * 0.25 * w * h, w, h, 0.0, 0.0
    if profile_type == "rectangle":
        w = number_field(profile, "width")
        h = number_field(profile, "height")
        cr = number_field(profile, "corner_radius")
        area = w * h - (4.0 - math.pi) * (cr**2)
        return max(area, 0.0), w, h, 0.0, 0.0
    if profile_type == "trapezoid":
        top = number_field(profile, "top_width")
        bot = number_field(profile, "bottom_width")
        h = number_field(profile, "height")
        area = 0.5 * (top + bot) * h
        w = max(top, bot)
        cz = (h / 6.0) * (top - bot) / ((top + bot) * 0.5) if (top + bot) > 0.0 else 0.0
        return max(area, 0.0), w, h, 0.0, cz
    if profile_type == "triangle":
        bw = number_field(profile, "base_width")
        h = number_field(profile, "height")
        area = 0.5 * bw * h
        cz = -h / 6.0 if profile.get("orientation") == "down" else h / 6.0
        return max(area, 0.0), bw, h, 0.0, cz

    pts = sample_profile(profile)
    area, cy, cz = _polygon_area_and_centroid(pts)
    w = max(p[0] for p in pts) - min(p[0] for p in pts)
    h = max(p[1] for p in pts) - min(p[1] for p in pts)
    return area, w, h, cy, cz


def _compute_fuselage_section_bbox(
    section: dict[str, Any],
    index: int = 0,
    segment_tag: str = "main",
) -> dict[str, Any]:
    """Compute the 2D/3D bounding quadrilateral cross-section for a fuselage section."""
    prof = _dict_field(section, "profile")
    ptype = prof.get("type")
    y_center = 0.0
    z_center = 0.0

    if ptype == "circle":
        d = number_field(prof, "diameter")
        h = d
        top_w, bot_w = d, d
        shape = "rectangle"
        area = d * d
    elif ptype in ("ellipse", "rectangle"):
        w = number_field(prof, "width")
        h = number_field(prof, "height")
        top_w, bot_w = w, w
        shape = "rectangle"
        area = w * h
    elif ptype == "trapezoid":
        top_w = number_field(prof, "top_width")
        bot_w = number_field(prof, "bottom_width")
        h = number_field(prof, "height")
        shape = "trapezoid"
        area = 0.5 * (top_w + bot_w) * h
    elif ptype == "triangle":
        bw = number_field(prof, "base_width")
        h = number_field(prof, "height")
        shape = "triangle"
        top_w = 0.0 if prof.get("orientation") != "down" else bw
        bot_w = bw if prof.get("orientation") != "down" else 0.0
        area = 0.5 * bw * h
    else:
        outline = sample_profile(prof)
        outline_ys = [p[0] for p in outline]
        outline_zs = [p[1] for p in outline]
        w = max(outline_ys) - min(outline_ys)
        h = max(outline_zs) - min(outline_zs)
        y_center = (max(outline_ys) + min(outline_ys)) * 0.5
        z_center = (max(outline_zs) + min(outline_zs)) * 0.5
        top_w, bot_w = w, w
        shape = "rectangle"
        area = w * h

    z_top = z_center + h * 0.5
    z_bottom = z_center - h * 0.5
    local_corners = (
        (0.0, y_center - top_w * 0.5, z_top),  # top-left
        (0.0, y_center + top_w * 0.5, z_top),  # top-right
        (0.0, y_center + bot_w * 0.5, z_bottom),  # bottom-right
        (0.0, y_center - bot_w * 0.5, z_bottom),  # bottom-left
    )
    matrix = section_transform(section)
    world_corners = [transform_point(matrix, p) for p in local_corners]
    world_center = transform_point(matrix, (0.0, 0.0, 0.0))

    ys = [p[1] for p in world_corners]
    zs = [p[2] for p in world_corners]

    return {
        "index": index,
        "segment": segment_tag,
        "station_x_mm": round(world_center[0], 2),
        "position": {
            "x": round(world_center[0], 2),
            "y": round(world_center[1], 2),
            "z": round(world_center[2], 2),
        },
        "width_mm": round(max(ys) - min(ys), 2),
        "height_mm": round(max(zs) - min(zs), 2),
        "shape": shape,
        "top_width_mm": round(top_w, 2),
        "bottom_width_mm": round(bot_w, 2),
        "y_bounds_mm": [round(min(ys), 2), round(max(ys), 2)],
        "z_bounds_mm": [round(min(zs), 2), round(max(zs), 2)],
        "area_mm2": round(area, 2),
        "corners_3d": [
            {"x": round(p[0], 2), "y": round(p[1], 2), "z": round(p[2], 2)} for p in world_corners
        ],
    }


def _compute_airfoil_properties(
    airfoil: Any,
    te_thickness: float = 0.0,
    thickness_scale: float = 1.0,
    camber_scale: float = 1.0,
) -> tuple[float, float, float, float, float, float]:
    """Compute normalized (area, cx, cz, izz_c, ixx_c, ixz_c) for an airfoil in [0, 1] coordinates."""
    pts = apply_airfoil_shaping(
        sample_airfoil_points(airfoil),
        te_thickness=te_thickness,
        thickness_scale=thickness_scale,
        camber_scale=camber_scale,
    )
    return _polygon_cross_section_properties(pts)


# =============================================================================
# Fuselage Slice & Section Integration
# =============================================================================


def _compute_fuselage_trapezoidal_slices(
    segments: list[Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    float,
    tuple[float, float, float],
    dict[str, float],
]:
    """Integrate station-by-station frustum slices and section bboxes for a fuselage.

    Returns:
        (sections_list, slices_list, total_volume_mm3, (cg_x, cg_y, cg_z), unit_inertia_m2)
    """
    sections: list[dict[str, Any]] = []
    slices: list[dict[str, Any]] = []
    total_vol = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    weighted_z = 0.0

    slice_data: list[
        tuple[float, tuple[float, float, float], tuple[float, float, float]]
    ] = []  # (V_i, cg_i, (Ixx_i, Iyy_i, Izz_i))

    slice_idx = 0
    sec_global_idx = 0
    for seg_idx, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        seg_tag = str(segment.get("tag") or f"seg_{seg_idx}")
        raw_sections = segment.get("sections")
        if not isinstance(raw_sections, list) or len(raw_sections) < 2:
            continue

        valid_sections: list[dict[str, Any]] = [s for s in raw_sections if isinstance(s, dict)]
        # Sort along X
        valid_sections.sort(key=lambda s: number_field(_dict_field(s, "position"), "x", 0.0))

        # Compute BBox cross-sections for all sections in this segment
        seg_section_bboxes = [
            _compute_fuselage_section_bbox(s, sec_global_idx + s_i, seg_tag)
            for s_i, s in enumerate(valid_sections)
        ]
        sections.extend(seg_section_bboxes)
        sec_global_idx += len(valid_sections)

        for i in range(len(valid_sections) - 1):
            s1 = valid_sections[i]
            s2 = valid_sections[i + 1]
            bbox1 = seg_section_bboxes[i]
            bbox2 = seg_section_bboxes[i + 1]

            pos1 = _dict_field(s1, "position")
            pos2 = _dict_field(s2, "position")
            prof1 = _dict_field(s1, "profile")

            x1, y1, z1 = _position(pos1)
            x2, y2, z2 = _position(pos2)

            # Section properties
            a1, w1, h1, cy1, cz1 = _compute_section_properties(prof1)
            prof2 = _dict_field(s2, "profile")
            a2, w2, h2, cy2, cz2 = _compute_section_properties(prof2)

            dx = x2 - x1
            length = dx if dx > 0.0 else math.sqrt(dx**2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
            if length < 1e-4:
                continue

            # Frustum volume formula: V = (L / 3) * (A1 + A2 + sqrt(A1 * A2))
            geom_mean = math.sqrt(max(a1 * a2, 0.0))
            vol = (length / 3.0) * (a1 + a2 + geom_mean)
            if vol <= 0.0:
                continue

            denom = 4.0 * (a1 + a2 + geom_mean)
            t = (a1 + 2.0 * geom_mean + 3.0 * a2) / denom if denom > 1e-9 else 0.5

            c1 = (x1, y1 + cy1, z1 + cz1)
            c2 = (x2, y2 + cy2, z2 + cz2)
            cg_slice = (
                c1[0] + t * (c2[0] - c1[0]),
                c1[1] + t * (c2[1] - c1[1]),
                c1[2] + t * (c2[2] - c1[2]),
            )

            # Longitudinal moment distribution along the slice
            factor = (
                (a1 + 3.0 * geom_mean + 6.0 * a2) / (10.0 * (a1 + a2 + geom_mean)) - t**2
                if denom > 1e-9
                else 1.0 / 12.0
            )
            jl = vol * (length**2) * max(factor, 0.0)

            # Transverse cross-section distribution
            w_avg = (w1 + w2) * 0.5
            h_avg = (h1 + h2) * 0.5
            p_type = prof1.get("type")
            div = 16.0 if p_type in ("circle", "ellipse") else 12.0
            jy = vol * (h_avg**2) / div
            jz = vol * (w_avg**2) / div

            ixx_slice = jy + jz
            iyy_slice = jl + jy
            izz_slice = jl + jz

            total_vol += vol
            weighted_x += vol * cg_slice[0]
            weighted_y += vol * cg_slice[1]
            weighted_z += vol * cg_slice[2]

            slice_data.append((vol, cg_slice, (ixx_slice, iyy_slice, izz_slice)))
            slices.append(
                {
                    "index": slice_idx,
                    "segment": seg_tag,
                    "start_section_index": bbox1["index"],
                    "end_section_index": bbox2["index"],
                    "station_start_mm": round(x1, 2),
                    "station_end_mm": round(x2, 2),
                    "length_mm": round(length, 2),
                    "start_dimensions_mm": {"width": round(w1, 2), "height": round(h1, 2)},
                    "end_dimensions_mm": {"width": round(w2, 2), "height": round(h2, 2)},
                    "volume_mm3": round(vol, 2),
                    "centroid_mm": {
                        "x": round(cg_slice[0], 2),
                        "y": round(cg_slice[1], 2),
                        "z": round(cg_slice[2], 2),
                    },
                }
            )
            slice_idx += 1

    if total_vol <= 0.0:
        return (
            sections,
            [],
            0.0,
            (0.0, 0.0, 0.0),
            {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0},
        )

    cg_total = (
        weighted_x / total_vol,
        weighted_y / total_vol,
        weighted_z / total_vol,
    )

    # Parallel Axis Theorem (Steiner's theorem) to fuselage total centroid
    ixx_total = 0.0
    iyy_total = 0.0
    izz_total = 0.0
    ixy_total = 0.0
    ixz_total = 0.0
    iyz_total = 0.0

    for vol, (cx, cy, cz), (ixx_s, iyy_s, izz_s) in slice_data:
        dx = cx - cg_total[0]
        dy = cy - cg_total[1]
        dz = cz - cg_total[2]

        ixx_total += ixx_s + vol * (dy**2 + dz**2)
        iyy_total += iyy_s + vol * (dx**2 + dz**2)
        izz_total += izz_s + vol * (dx**2 + dy**2)
        ixy_total -= vol * dx * dy
        ixz_total -= vol * dx * dz
        iyz_total -= vol * dy * dz

    # Convert mm^5 / mm^3 (mm^2) to unit inertia in m^2 (divide by 1e6)
    scale = total_vol * 1e6
    unit_inertia = {
        "ixx": round(ixx_total / scale, 8),
        "iyy": round(iyy_total / scale, 8),
        "izz": round(izz_total / scale, 8),
        "ixy": round(ixy_total / scale, 8),
        "ixz": round(ixz_total / scale, 8),
        "iyz": round(iyz_total / scale, 8),
    }

    return sections, slices, total_vol, cg_total, unit_inertia


# =============================================================================
# Lifting Surface Slice Integration
# =============================================================================


def _compute_lifting_surface_trapezoidal_slices(
    geometry: dict[str, Any],
    profiles: list[Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    float,
    tuple[float, float, float],
    dict[str, float],
]:
    """Integrate station-by-station trapezoidal panel slices for a lifting surface.

    Handles taper, sweep, dihedral, airfoil thickness, and mirror symmetry.
    Returns:
        (sections_list, slices_list, total_volume_mm3, (cg_x, cg_y, cg_z), unit_inertia_m2)
    """
    valid_profiles: list[dict[str, Any]] = [p for p in profiles if isinstance(p, dict)]
    if len(valid_profiles) < 2:
        return (
            [],
            [],
            0.0,
            (0.0, 0.0, 0.0),
            {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0},
        )

    valid_profiles.sort(key=lambda p: abs(number_field(_dict_field(p, "position"), "y", 0.0)))
    chords = [_profile_chord(p) for p in valid_profiles]

    mirror = bool(geometry.get("mirror", False))

    sections: list[dict[str, Any]] = []
    slices: list[dict[str, Any]] = []
    semi_vol = 0.0
    panel_data: list[Panel] = []

    # Compute section bboxes for all profiles
    shaping = geometry.get("airfoil_shaping")
    shaping = shaping if isinstance(shaping, dict) else {}
    twist_loc = number_field(geometry, "twist_location", 0.25)
    te_th = number_field(shaping, "te_thickness", 0.0)
    th_scale = number_field(shaping, "thickness_scale", 1.0)
    cb_scale = number_field(shaping, "camber_scale", 1.0)
    sec_align = str(geometry.get("section_align", "xz")).lower()

    for i, (prof, chord) in enumerate(zip(valid_profiles, chords, strict=True)):
        px, py, pz = _position(_dict_field(prof, "position"))
        (
            a_norm,
            _,
            _,
            _,
            _,
            _,
        ) = _compute_airfoil_properties(prof.get("airfoil"), te_th, th_scale, cb_scale)

        sec_geo = _build_profile_section(
            prof,
            twist_location=twist_loc,
            te_thickness=te_th,
            thickness_scale=th_scale,
            camber_scale=cb_scale,
            section_align=sec_align,
        )

        if sec_geo is None:
            raise ValueError(f"Lifting surface profile {prof!r} has no section geometry")
        pts = sec_geo.points
        le = min(pts, key=lambda p: p[0])
        te = max(pts, key=lambda p: p[0])
        bot_z = min(p[2] for p in pts)
        top_z = max(p[2] for p in pts)
        min_x = min(p[0] for p in pts)
        max_x = max(p[0] for p in pts)
        min_y = min(p[1] for p in pts)
        max_y = max(p[1] for p in pts)
        y_center = (min_y + max_y) * 0.5

        thick = round(top_z - bot_z, 2)
        x_bounds = [round(min_x, 2), round(max_x, 2)]
        z_bounds = [round(bot_z, 2), round(top_z, 2)]
        corners = [
            {"x": round(le[0], 2), "y": round(le[1], 2), "z": round(bot_z, 2)},
            {"x": round(te[0], 2), "y": round(te[1], 2), "z": round(bot_z, 2)},
            {"x": round(te[0], 2), "y": round(te[1], 2), "z": round(top_z, 2)},
            {"x": round(le[0], 2), "y": round(le[1], 2), "z": round(top_z, 2)},
        ]

        sections.append(
            {
                "index": i,
                "span_y_mm": round(y_center, 2),
                "position": {"x": round(px, 2), "y": round(py, 2), "z": round(pz, 2)},
                "chord_mm": round(chord, 2),
                "thickness_mm": thick,
                "x_bounds_mm": x_bounds,
                "z_bounds_mm": z_bounds,
                "area_mm2": round(a_norm * (chord**2), 2),
                "shape": "airfoil",
                "corners_3d": corners,
            }
        )

    for i in range(len(valid_profiles) - 1):
        p1 = valid_profiles[i]
        p2 = valid_profiles[i + 1]

        x1, y1, z1 = _position(_dict_field(p1, "position"))
        x2, y2, z2 = _position(_dict_field(p2, "position"))
        c1 = chords[i]
        c2 = chords[i + 1]

        (
            a_norm1,
            cx_norm1,
            cz_norm1,
            izz_norm1,
            ixx_norm1,
            _ixz_norm1,
        ) = _compute_airfoil_properties(p1.get("airfoil"), te_th, th_scale, cb_scale)
        (
            a_norm2,
            cx_norm2,
            cz_norm2,
            izz_norm2,
            ixx_norm2,
            _ixz_norm2,
        ) = _compute_airfoil_properties(p2.get("airfoil"), te_th, th_scale, cb_scale)

        a1 = a_norm1 * (c1**2)
        a2 = a_norm2 * (c2**2)

        span_len = abs(y2 - y1)
        if span_len < 1e-4:
            span_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
        if span_len < 1e-4:
            continue

        # Radii of gyration squared (normalized by chord^2) from Green's theorem,
        # averaged over the end sections that have cross-section area.
        c_avg = (c1 + c2) * 0.5
        panel = _frustum_panel(
            span_len,
            (a1, a2),
            (
                (x1 + c1 * cx_norm1, y1, z1 + c1 * cz_norm1),
                (x2 + c2 * cx_norm2, y2, z2 + c2 * cz_norm2),
            ),
            (
                (c_avg**2) * _mean_gyration_sq(((izz_norm1, a_norm1), (izz_norm2, a_norm2))),
                (c_avg**2) * _mean_gyration_sq(((ixx_norm1, a_norm1), (ixx_norm2, a_norm2))),
            ),
        )
        if panel is None:
            continue
        vol, cg_panel, _ = panel
        semi_vol += vol
        panel_data.append(panel)
        slices.append(
            {
                "index": i,
                "start_section_index": i,
                "end_section_index": i + 1,
                "span_start_mm": round(y1, 2),
                "span_end_mm": round(y2, 2),
                "length_mm": round(span_len, 2),
                "chord_start_mm": round(c1, 2),
                "chord_end_mm": round(c2, 2),
                "volume_mm3": round(vol, 2),
                "centroid_mm": {
                    "x": round(cg_panel[0], 2),
                    "y": round(cg_panel[1], 2),
                    "z": round(cg_panel[2], 2),
                },
            }
        )

    if semi_vol <= 0.0:
        return (
            sections,
            [],
            0.0,
            (0.0, 0.0, 0.0),
            {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0},
        )

    total_vol, cg_total, unit_inertia = _combine_panels(panel_data, mirror=mirror)
    return sections, slices, total_vol, cg_total, unit_inertia


Panel = tuple[float, tuple[float, float, float], tuple[float, float, float]]
"""Volume, centroid and principal inertia about the centroid of one slice."""


def _frustum_panel(
    span_len: float,
    areas: tuple[float, float],
    centroids: tuple[tuple[float, float, float], tuple[float, float, float]],
    gyration_sq: tuple[float, float],
) -> Panel | None:
    """Return the slice between two sections of ``areas`` and ``centroids``.

    The slice is a prismatoid; ``gyration_sq`` holds its chordwise and thickness
    radii of gyration squared.
    """
    a1, a2 = areas
    geom_mean = math.sqrt(max(a1 * a2, 0.0))
    vol = (span_len / 3.0) * (a1 + a2 + geom_mean)
    if vol <= 0.0:
        return None
    denom = 4.0 * (a1 + a2 + geom_mean)
    t = (a1 + 2.0 * geom_mean + 3.0 * a2) / denom if denom > 1e-9 else 0.5
    first, second = centroids
    centroid = (
        first[0] + t * (second[0] - first[0]),
        first[1] + t * (second[1] - first[1]),
        first[2] + t * (second[2] - first[2]),
    )
    factor = (
        (a1 + 3.0 * geom_mean + 6.0 * a2) / (10.0 * (a1 + a2 + geom_mean)) - t**2
        if denom > 1e-9
        else 1.0 / 12.0
    )
    j_span = vol * (span_len**2) * max(factor, 0.0)
    j_chord = vol * gyration_sq[0]
    j_thick = vol * gyration_sq[1]
    return vol, centroid, (j_span + j_thick, j_chord + j_thick, j_span + j_chord)


def _combine_panels(
    panel_data: list[Panel], *, mirror: bool
) -> tuple[float, tuple[float, float, float], dict[str, float]]:
    """Return the volume, centroid and unit inertia of ``panel_data``.

    ``mirror`` adds the panels' image in the XZ plane.
    """
    semi_vol = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    weighted_z = 0.0
    for vol, centroid, _inertia in panel_data:
        semi_vol += vol
        weighted_x += vol * centroid[0]
        weighted_y += vol * centroid[1]
        weighted_z += vol * centroid[2]
    cg_x = weighted_x / semi_vol
    cg_z = weighted_z / semi_vol
    cg_y = 0.0 if mirror else (weighted_y / semi_vol)
    cg_total = (cg_x, cg_y, cg_z)

    total_vol = semi_vol * (2.0 if mirror else 1.0)

    # Parallel Axis Theorem
    ixx_total = 0.0
    iyy_total = 0.0
    izz_total = 0.0
    ixy_total = 0.0
    ixz_total = 0.0
    iyz_total = 0.0

    for vol, (cx, cy, cz), (ixx_p, iyy_p, izz_p) in panel_data:
        dx = cx - cg_x
        dz = cz - cg_z

        if mirror:
            dy = cy
            ixx_total += 2.0 * (ixx_p + vol * (dy**2 + dz**2))
            iyy_total += 2.0 * (iyy_p + vol * (dx**2 + dz**2))
            izz_total += 2.0 * (izz_p + vol * (dx**2 + dy**2))
            ixz_total -= 2.0 * (vol * dx * dz)
        else:
            dy = cy - cg_y
            ixx_total += ixx_p + vol * (dy**2 + dz**2)
            iyy_total += iyy_p + vol * (dx**2 + dz**2)
            izz_total += izz_p + vol * (dx**2 + dy**2)
            ixy_total -= vol * dx * dy
            ixz_total -= vol * dx * dz
            iyz_total -= vol * dy * dz

    scale = total_vol * 1e6
    unit_inertia = {
        "ixx": round(ixx_total / scale, 8),
        "iyy": round(iyy_total / scale, 8),
        "izz": round(izz_total / scale, 8),
        "ixy": round(ixy_total / scale, 8),
        "ixz": round(ixz_total / scale, 8),
        "iyz": round(iyz_total / scale, 8),
    }
    return total_vol, cg_total, unit_inertia


# =============================================================================
# Component Envelope Builders
# =============================================================================


def _compute_lifting_surface_envelope(component: dict[str, Any]) -> dict[str, Any] | None:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    profiles = geometry.get("profiles")
    if not isinstance(profiles, list) or len(profiles) < 2:
        return None

    # Compute exact trapezoidal panel slices and centroid
    sections, slices, total_vol, cg, unit_inertia = _compute_lifting_surface_trapezoidal_slices(
        geometry, profiles
    )

    # Outer bounding dimensions from the 3D loft mesh
    lofts = build_lifting_surface_geometry(component)
    pts = [p for loft in lofts for sec in loft.sections for p in sec.points]
    if not pts:
        return None
    mirror = bool(geometry.get("mirror", False))

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    if mirror:
        size_y = round(max(abs(y) for y in ys) * 2.0, 1)
        center_y = 0.0
    else:
        size_y = round(max(ys) - min(ys), 1)
        center_y = (max(ys) + min(ys)) * 0.5
    size_x = round(max(xs) - min(xs), 1)
    size_z = round(max(zs) - min(zs), 1)
    center = ((max(xs) + min(xs)) * 0.5, center_y, (max(zs) + min(zs)) * 0.5)
    offset = cg if total_vol > 0.0 else center

    return {
        "shape": "box",
        "size_mm": {"x": size_x, "y": size_y, "z": size_z},
        "offset_mm": {
            "x": round(offset[0], 1),
            "y": round(offset[1], 1),
            "z": round(offset[2], 1),
        },
        "volume_mm3": round(total_vol, 1),
        "unit_inertia": unit_inertia,
        "sections": sections,
        "slices": slices,
    }


def _compute_fuselage_envelope(component: dict[str, Any]) -> dict[str, Any] | None:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    segments = geometry.get("segments")
    if not isinstance(segments, list) or not segments:
        return None

    # Compute exact frustum slices, section bboxes, volume, centroid, and inertia
    sections, slices, total_vol, cg, unit_inertia = _compute_fuselage_trapezoidal_slices(segments)

    # Outer bounding dimensions from the 3D loft mesh
    lofts = build_fuselage_geometry(component)
    pts = [p for loft in lofts for sec in loft.sections for p in sec.points]
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    center = (
        (max(xs) + min(xs)) * 0.5,
        (max(ys) + min(ys)) * 0.5,
        (max(zs) + min(zs)) * 0.5,
    )
    offset = cg if total_vol > 0.0 else center

    return {
        "shape": "trapezoid",
        "size_mm": {
            "x": round(max(xs) - min(xs), 1),
            "y": round(max(ys) - min(ys), 1),
            "z": round(max(zs) - min(zs), 1),
        },
        "offset_mm": {
            "x": round(offset[0], 1),
            "y": round(offset[1], 1),
            "z": round(offset[2], 1),
        },
        "volume_mm3": round(total_vol, 1),
        "unit_inertia": unit_inertia,
        "sections": sections,
        "slices": slices,
    }


def _compute_control_surface_envelope(
    component: dict[str, Any],
    surface: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Envelope of a control surface cut from the lifting surface it attaches to.

    A control surface not attached to a lifting surface, or whose span does not cut it,
    has no geometry and so no envelope.
    """
    if surface is None or surface.get("type") != _LIFTING_SURFACE_TYPE:
        return None
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}

    ctrl_id = str(component.get("id") or "CS")
    ctrl_geom = deepcopy(geometry)
    ctrl_geom["id"] = ctrl_id
    ctrl_geom["deflection"] = 0.0
    set_expression(ctrl_geom, "deflection", None)

    lofts = build_lifting_surface_geometry(surface, control_surfaces=[ctrl_geom])
    control_loft = next(
        (loft for loft in lofts if loft.component_id.lower().endswith(f":{ctrl_id.lower()}")),
        None,
    )
    if control_loft is None or len(control_loft.sections) < 2:
        return None

    sections: list[dict[str, Any]] = []
    all_pts = [p for sec in control_loft.sections for p in sec.points]
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    zs = [p[2] for p in all_pts]

    size_x = round(max(xs) - min(xs), 1)
    size_y = round(max(ys) - min(ys), 1)
    size_z = round(max(zs) - min(zs), 1)

    offset_x = round((max(xs) + min(xs)) * 0.5, 1)
    offset_y = round((max(ys) + min(ys)) * 0.5, 1)
    offset_z = round((max(zs) + min(zs)) * 0.5, 1)

    # Area, centroid and chordwise / thickness second moments of each section.
    section_properties: list[tuple[float, tuple[float, float, float], float, float]] = []
    slices: list[dict[str, Any]] = []

    for idx, sec in enumerate(control_loft.sections):
        pts = sec.points
        if not pts:
            continue
        le = min(pts, key=lambda p: p[0])
        te = max(pts, key=lambda p: p[0])
        bot_z = min(p[2] for p in pts)
        top_z = max(p[2] for p in pts)
        min_x = min(p[0] for p in pts)
        max_x = max(p[0] for p in pts)
        min_y = min(p[1] for p in pts)
        max_y = max(p[1] for p in pts)
        y_center = (min_y + max_y) * 0.5
        area, cx, cz, izz_c, ixx_c, _ixz_c = _polygon_cross_section_properties(
            [(p[0], p[2]) for p in pts]
        )
        section_properties.append((area, (cx, y_center, cz), izz_c, ixx_c))

        thick = round(top_z - bot_z, 2)
        c_sec = round(max_x - min_x, 2)

        corners = [
            {"x": round(le[0], 2), "y": round(le[1], 2), "z": round(bot_z, 2)},
            {"x": round(te[0], 2), "y": round(te[1], 2), "z": round(bot_z, 2)},
            {"x": round(te[0], 2), "y": round(te[1], 2), "z": round(top_z, 2)},
            {"x": round(le[0], 2), "y": round(le[1], 2), "z": round(top_z, 2)},
        ]

        sections.append(
            {
                "index": idx,
                "span_y_mm": round(y_center, 2),
                "position": {
                    "x": round(min_x, 2),
                    "y": round(y_center, 2),
                    "z": round((bot_z + top_z) * 0.5, 2),
                },
                "chord_mm": c_sec,
                "thickness_mm": thick,
                "x_bounds_mm": [round(min_x, 2), round(max_x, 2)],
                "z_bounds_mm": [round(bot_z, 2), round(top_z, 2)],
                "area_mm2": round(area, 2),
                "shape": "wedge",
                "corners_3d": corners,
            }
        )

    panels: list[Panel] = []
    for i in range(len(sections) - 1):
        a1, cg1, izz1, ixx1 = section_properties[i]
        a2, cg2, izz2, ixx2 = section_properties[i + 1]
        y1, y2 = cg1[1], cg2[1]
        span_len = abs(y2 - y1)
        panel = _frustum_panel(
            span_len,
            (a1, a2),
            (cg1, cg2),
            (
                _mean_gyration_sq(((izz1, a1), (izz2, a2))),
                _mean_gyration_sq(((ixx1, a1), (ixx2, a2))),
            ),
        )
        if panel is None:
            continue
        panels.append(panel)
        vol, cg_slice, _ = panel
        slices.append(
            {
                "index": i,
                "start_section_index": i,
                "end_section_index": i + 1,
                "span_start_mm": round(y1, 2),
                "span_end_mm": round(y2, 2),
                "length_mm": round(span_len, 2),
                "chord_start_mm": sections[i]["chord_mm"],
                "chord_end_mm": sections[i + 1]["chord_mm"],
                "volume_mm3": round(vol, 2),
                "centroid_mm": {
                    "x": round(cg_slice[0], 2),
                    "y": round(cg_slice[1], 2),
                    "z": round(cg_slice[2], 2),
                },
            }
        )

    total_vol = 0.0
    unit_inertia = {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0}
    if panels:
        total_vol, centroid, unit_inertia = _combine_panels(panels, mirror=False)
        offset_x = round(centroid[0], 1)
        offset_y = round(centroid[1], 1)
        offset_z = round(centroid[2], 1)

    env_dict = {
        "shape": "box",
        "size_mm": {"x": size_x, "y": size_y, "z": size_z},
        "offset_mm": {"x": offset_x, "y": offset_y, "z": offset_z},
        "volume_mm3": round(total_vol, 1),
        "unit_inertia": unit_inertia,
        "sections": sections,
        "slices": slices,
    }
    if control_loft.hinge_points and len(control_loft.hinge_points) >= 2:
        env_dict["hinge_axis"] = [
            {
                "x": round(control_loft.hinge_points[0][0], 2),
                "y": round(control_loft.hinge_points[0][1], 2),
                "z": round(control_loft.hinge_points[0][2], 2),
            },
            {
                "x": round(control_loft.hinge_points[-1][0], 2),
                "y": round(control_loft.hinge_points[-1][1], 2),
                "z": round(control_loft.hinge_points[-1][2], 2),
            },
        ]
    return env_dict


__all__ = [
    "GEOMETRY_COMPONENT_TYPES",
    "compute_geometry_envelope",
    "sync_component_envelope",
    "sync_project_geometry_envelopes",
]
