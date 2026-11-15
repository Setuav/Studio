"""Universal physical envelope, centroid, and mass-inertia property calculations for 3D components."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

Point3D = tuple[float, float, float]
Triangle3D = tuple[Point3D, Point3D, Point3D]
UnitInertia6D = tuple[float, float, float, float, float, float]


def _to_vec3(val: Any, default: Point3D = (0.0, 0.0, 0.0)) -> Point3D:
    if isinstance(val, dict):
        return (
            float(val.get("x", default[0]) or 0.0),
            float(val.get("y", default[1]) or 0.0),
            float(val.get("z", default[2]) or 0.0),
        )
    if isinstance(val, (tuple, list)) and len(val) >= 3:
        return (float(val[0]), float(val[1]), float(val[2]))
    return default


def _resample_loop(loop: Sequence[Point3D], target_count: int) -> list[Point3D]:
    """Resample a closed 3D polygon loop to exactly target_count points along perimeter."""
    n = len(loop)
    if n == target_count:
        return list(loop)
    if n < 3 or target_count < 3:
        return list(loop)

    # Compute cumulative perimeter distances
    cum_dists: list[float] = [0.0]
    total_len = 0.0
    for i in range(n):
        p1 = loop[i]
        p2 = loop[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        total_len += d
        cum_dists.append(total_len)

    if total_len < 1e-9:
        return [loop[0]] * target_count

    result: list[Point3D] = []
    step = total_len / float(target_count)
    curr_seg = 0
    for k in range(target_count):
        target_s = k * step
        while curr_seg < n and cum_dists[curr_seg + 1] < target_s:
            curr_seg += 1
        if curr_seg >= n:
            curr_seg = n - 1
        s0 = cum_dists[curr_seg]
        s1 = cum_dists[curr_seg + 1]
        seg_len = s1 - s0
        t = (target_s - s0) / seg_len if seg_len > 1e-9 else 0.0
        p0 = loop[curr_seg]
        p1 = loop[(curr_seg + 1) % n]
        result.append(
            (
                p0[0] + t * (p1[0] - p0[0]),
                p0[1] + t * (p1[1] - p0[1]),
                p0[2] + t * (p1[2] - p0[2]),
            )
        )
    return result


def _triangulate_quad_strip(
    loop1: Sequence[Point3D],
    loop2: Sequence[Point3D],
) -> list[Triangle3D]:
    """Triangulate the surface quad-strip between two consecutive closed section loops."""
    m = len(loop1)
    if len(loop2) != m:
        m = max(len(loop1), len(loop2), 16)
        loop1 = _resample_loop(loop1, m)
        loop2 = _resample_loop(loop2, m)

    triangles: list[Triangle3D] = []
    for j in range(m):
        j_next = (j + 1) % m
        p0 = loop1[j]
        p1 = loop1[j_next]
        p2 = loop2[j_next]
        p3 = loop2[j]
        triangles.append((p0, p1, p2))
        triangles.append((p0, p2, p3))
    return triangles


def _cap_polygon(loop: Sequence[Point3D], reverse: bool = False) -> list[Triangle3D]:
    """Triangulate a planar or near-planar closed loop as an end cap fan."""
    n = len(loop)
    if n < 3:
        return []
    # Centroid of loop as fan apex
    cx = sum(p[0] for p in loop) / float(n)
    cy = sum(p[1] for p in loop) / float(n)
    cz = sum(p[2] for p in loop) / float(n)
    center: Point3D = (cx, cy, cz)

    triangles: list[Triangle3D] = []
    for i in range(n):
        p1 = loop[i]
        p2 = loop[(i + 1) % n]
        if reverse:
            triangles.append((center, p2, p1))
        else:
            triangles.append((center, p1, p2))
    return triangles


def compute_mesh_mass_properties(
    triangles: Sequence[Triangle3D],
) -> tuple[float, Point3D, Point3D, UnitInertia6D]:
    """Analytic closed-polyhedron integration using divergence theorem.

    Returns:
        (volume_mm3, centroid_mm, bounding_box_size_mm, unit_inertia_m2)
        where unit_inertia_m2 is (ixx, iyy, izz, ixy, ixz, iyz) expressed in m^2.
    """
    if not triangles:
        return 0.0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    vol6 = 0.0
    c_x24 = 0.0
    c_y24 = 0.0
    c_z24 = 0.0

    int_x2_120 = 0.0
    int_y2_120 = 0.0
    int_z2_120 = 0.0
    int_xy_120 = 0.0
    int_xz_120 = 0.0
    int_yz_120 = 0.0

    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    for p0, p1, p2 in triangles:
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        x2, y2, z2 = p2

        # Bounding box accumulation
        for x, y, z in (p0, p1, p2):
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
            if z < min_z:
                min_z = z
            if z > max_z:
                max_z = z

        # Face normal via cross product
        d1x = x1 - x0
        d1y = y1 - y0
        d1z = z1 - z0
        d2x = x2 - x0
        d2y = y2 - y0
        d2z = z2 - z0

        nx = d1y * d2z - d1z * d2y
        ny = d1z * d2x - d1x * d2z
        nz = d1x * d2y - d1y * d2x

        det = x0 * nx + y0 * ny + z0 * nz

        vol6 += det
        c_x24 += det * (x0 + x1 + x2)
        c_y24 += det * (y0 + y1 + y2)
        c_z24 += det * (z0 + z1 + z2)

        # Diagonal second moments
        int_x2_120 += det * 2.0 * (x0 * x0 + x1 * x1 + x2 * x2 + x0 * x1 + x1 * x2 + x2 * x0)
        int_y2_120 += det * 2.0 * (y0 * y0 + y1 * y1 + y2 * y2 + y0 * y1 + y1 * y2 + y2 * y0)
        int_z2_120 += det * 2.0 * (z0 * z0 + z1 * z1 + z2 * z2 + z0 * z1 + z1 * z2 + z2 * z0)

        # Off-diagonal product moments
        int_xy_120 += det * (
            2.0 * (x0 * y0 + x1 * y1 + x2 * y2)
            + x0 * y1
            + x1 * y0
            + x1 * y2
            + x2 * y1
            + x2 * y0
            + x0 * y2
        )
        int_xz_120 += det * (
            2.0 * (x0 * z0 + x1 * z1 + x2 * z2)
            + x0 * z1
            + x1 * z0
            + x1 * z2
            + x2 * z1
            + x2 * z0
            + x0 * z2
        )
        int_yz_120 += det * (
            2.0 * (y0 * z0 + y1 * z1 + y2 * z2)
            + y0 * z1
            + y1 * z0
            + y1 * z2
            + y2 * z1
            + y2 * z0
            + y0 * z2
        )

    vol = vol6 / 6.0
    abs_vol = abs(vol)

    size_x = max(max_x - min_x, 1.0) if max_x >= min_x else 1.0
    size_y = max(max_y - min_y, 1.0) if max_y >= min_y else 1.0
    size_z = max(max_z - min_z, 1.0) if max_z >= min_z else 1.0
    size_box: Point3D = (size_x, size_y, size_z)

    if abs_vol < 1e-9:
        mid_x = (min_x + max_x) * 0.5 if max_x >= min_x else 0.0
        mid_y = (min_y + max_y) * 0.5 if max_y >= min_y else 0.0
        mid_z = (min_z + max_z) * 0.5 if max_z >= min_z else 0.0
        return 0.0, (mid_x, mid_y, mid_z), size_box, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    sign = 1.0 if vol6 >= 0.0 else -1.0
    cx = c_x24 / (4.0 * vol6)
    cy = c_y24 / (4.0 * vol6)
    cz = c_z24 / (4.0 * vol6)
    centroid: Point3D = (cx, cy, cz)

    # Second moments of volume relative to origin
    m_x2 = (int_x2_120 / 120.0) * sign
    m_y2 = (int_y2_120 / 120.0) * sign
    m_z2 = (int_z2_120 / 120.0) * sign
    m_xy = (int_xy_120 / 120.0) * sign
    m_xz = (int_xz_120 / 120.0) * sign
    m_yz = (int_yz_120 / 120.0) * sign

    # Parallel axis shift to centroid: int (x - cx)^2 = int x^2 - V * cx^2
    c_x2 = max(m_x2 - abs_vol * (cx * cx), 0.0)
    c_y2 = max(m_y2 - abs_vol * (cy * cy), 0.0)
    c_z2 = max(m_z2 - abs_vol * (cz * cz), 0.0)
    c_xy = m_xy - abs_vol * (cx * cy)
    c_xz = m_xz - abs_vol * (cx * cz)
    c_yz = m_yz - abs_vol * (cy * cz)

    # Principal inertia tensor moments: Ixx = \int (y^2 + z^2)
    # Scaled to unit inertia (m^2) by dividing by volume (mm^3) and 10^6 (mm^2 -> m^2)
    vol_scale = abs_vol * 1.0e6
    unit_ixx = (c_y2 + c_z2) / vol_scale
    unit_iyy = (c_x2 + c_z2) / vol_scale
    unit_izz = (c_x2 + c_y2) / vol_scale
    unit_ixy = c_xy / vol_scale
    unit_ixz = c_xz / vol_scale
    unit_iyz = c_yz / vol_scale

    return (
        abs_vol,
        centroid,
        size_box,
        (unit_ixx, unit_iyy, unit_izz, unit_ixy, unit_ixz, unit_iyz),  # type: ignore[return-value]
    )


def compute_loft_envelope(
    sections: Sequence[Sequence[Point3D]],
    *,
    closed_ends: bool = True,
    mirror_y: bool = False,
) -> dict[str, Any]:
    """Compute physical envelope directly from ordered loft section loops."""
    valid_sections = [sec for sec in sections if len(sec) >= 3]
    if len(valid_sections) < 2:
        return _empty_envelope()

    triangles: list[Triangle3D] = []
    for i in range(len(valid_sections) - 1):
        triangles.extend(_triangulate_quad_strip(valid_sections[i], valid_sections[i + 1]))

    if closed_ends:
        triangles.extend(_cap_polygon(valid_sections[0], reverse=True))
        triangles.extend(_cap_polygon(valid_sections[-1], reverse=False))

    if mirror_y:
        # Reflect across Y=0 with reversed triangle winding to keep outward normal
        mirrored: list[Triangle3D] = []
        for p0, p1, p2 in triangles:
            mp0 = (p0[0], -p0[1], p0[2])
            mp1 = (p1[0], -p1[1], p1[2])
            mp2 = (p2[0], -p2[1], p2[2])
            mirrored.append((mp0, mp2, mp1))
        triangles.extend(mirrored)

    vol, centroid, size_box, unit_inertia = compute_mesh_mass_properties(triangles)
    u_ixx, u_iyy, u_izz, u_ixy, u_ixz, u_iyz = unit_inertia

    # Build section station summary and slice breakdowns
    section_summaries = []
    for idx, sec in enumerate(valid_sections):
        xs = [p[0] for p in sec]
        ys = [p[1] for p in sec]
        zs = [p[2] for p in sec]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        sec_cx = sum(xs) / len(xs)
        sec_cy = sum(ys) / len(ys)
        sec_cz = sum(zs) / len(zs)
        w = max(max_y - min_y, 0.1)
        h = max(max_z - min_z, 0.1)
        chord_len = max(max_x - min_x, 0.1)

        # 4 corners in 3D representing section bounding extent
        corners = [
            {"x": round(min_x, 2), "y": round(sec_cy, 2), "z": round(min_z, 2)},
            {"x": round(max_x, 2), "y": round(sec_cy, 2), "z": round(min_z, 2)},
            {"x": round(max_x, 2), "y": round(sec_cy, 2), "z": round(max_z, 2)},
            {"x": round(min_x, 2), "y": round(sec_cy, 2), "z": round(max_z, 2)},
        ]

        section_summaries.append(
            {
                "index": idx,
                "station_x_mm": round(sec_cx, 2),
                "span_y_mm": round(sec_cy, 2),
                "position": {
                    "x": round(sec_cx, 2),
                    "y": round(sec_cy, 2),
                    "z": round(sec_cz, 2),
                },
                "width_mm": round(w, 2),
                "height_mm": round(h, 2),
                "chord_mm": round(chord_len, 2),
                "thickness_mm": round(h, 2),
                "x_bounds_mm": [round(min_x, 2), round(max_x, 2)],
                "y_bounds_mm": [round(min_y, 2), round(max_y, 2)],
                "z_bounds_mm": [round(min_z, 2), round(max_z, 2)],
                "corners_3d": corners,
            }
        )

    # Compute individual slice breakdowns between consecutive stations
    slice_summaries = []
    for i in range(len(valid_sections) - 1):
        s_tri = _triangulate_quad_strip(valid_sections[i], valid_sections[i + 1])
        s_tri.extend(_cap_polygon(valid_sections[i], reverse=True))
        s_tri.extend(_cap_polygon(valid_sections[i + 1], reverse=False))
        s_vol, s_cen, _, _ = compute_mesh_mass_properties(s_tri)
        slice_summaries.append(
            {
                "index": i,
                "station_x_mm": round(s_cen[0], 2),
                "station_y_mm": round(s_cen[1], 2),
                "volume_mm3": round(s_vol, 1),
            }
        )

    return {
        "shape": "box",
        "size_mm": {
            "x": round(size_box[0], 1),
            "y": round(size_box[1], 1),
            "z": round(size_box[2], 1),
        },
        "offset_mm": {
            "x": round(centroid[0], 1),
            "y": round(centroid[1], 1) if not mirror_y else 0.0,
            "z": round(centroid[2], 1),
        },
        "volume_mm3": round(vol, 1),
        "unit_inertia": {
            "ixx": round(u_ixx, 8),
            "iyy": round(u_iyy, 8),
            "izz": round(u_izz, 8),
            "ixy": round(u_ixy, 8) if not mirror_y else 0.0,
            "ixz": round(u_ixz, 8),
            "iyz": round(u_iyz, 8) if not mirror_y else 0.0,
        },
        "sections": section_summaries,
        "slices": slice_summaries,
    }


def compute_box_envelope(
    size_mm: Point3D | dict[str, float],
    offset_mm: Point3D | dict[str, float] = (0.0, 0.0, 0.0),
) -> dict[str, Any]:
    """Compute physical envelope for a cuboid / box."""
    sx, sy, sz = _to_vec3(size_mm)
    ox, oy, oz = _to_vec3(offset_mm)
    vol = max(sx * sy * sz, 0.0)

    # Unit inertia for solid cuboid in m^2 (mm^2 / 10^6)
    scale = 1.0e6
    u_ixx = ((sy * sy + sz * sz) / 12.0) / scale
    u_iyy = ((sx * sx + sz * sz) / 12.0) / scale
    u_izz = ((sx * sx + sy * sy) / 12.0) / scale

    return {
        "shape": "box",
        "size_mm": {"x": round(sx, 1), "y": round(sy, 1), "z": round(sz, 1)},
        "offset_mm": {"x": round(ox, 1), "y": round(oy, 1), "z": round(oz, 1)},
        "volume_mm3": round(vol, 1),
        "unit_inertia": {
            "ixx": round(u_ixx, 8),
            "iyy": round(u_iyy, 8),
            "izz": round(u_izz, 8),
            "ixy": 0.0,
            "ixz": 0.0,
            "iyz": 0.0,
        },
        "sections": [],
        "slices": [],
    }


def compute_cylinder_envelope(
    diameter_mm: float,
    length_mm: float,
    axis: str = "x",
    offset_mm: Point3D | dict[str, float] = (0.0, 0.0, 0.0),
) -> dict[str, Any]:
    """Compute physical envelope for a solid cylinder."""
    r = max(diameter_mm * 0.5, 0.0)
    l_val = max(length_mm, 0.0)
    vol = math.pi * r * r * l_val
    ox, oy, oz = _to_vec3(offset_mm)

    scale = 1.0e6
    # Axial moment: 1/2 r^2; Transverse: 1/12 L^2 + 1/4 r^2
    axial = (0.5 * r * r) / scale
    transverse = ((l_val * l_val / 12.0) + (0.25 * r * r)) / scale

    axis_lower = axis.lower()
    if axis_lower == "x":
        u_ixx, u_iyy, u_izz = axial, transverse, transverse
        size = (l_val, diameter_mm, diameter_mm)
    elif axis_lower == "y":
        u_ixx, u_iyy, u_izz = transverse, axial, transverse
        size = (diameter_mm, l_val, diameter_mm)
    else:
        u_ixx, u_iyy, u_izz = transverse, transverse, axial
        size = (diameter_mm, diameter_mm, l_val)

    return {
        "shape": "cylinder",
        "size_mm": {"x": round(size[0], 1), "y": round(size[1], 1), "z": round(size[2], 1)},
        "offset_mm": {"x": round(ox, 1), "y": round(oy, 1), "z": round(oz, 1)},
        "volume_mm3": round(vol, 1),
        "unit_inertia": {
            "ixx": round(u_ixx, 8),
            "iyy": round(u_iyy, 8),
            "izz": round(u_izz, 8),
            "ixy": 0.0,
            "ixz": 0.0,
            "iyz": 0.0,
        },
        "sections": [],
        "slices": [],
    }


def _envelope_from_lofts(
    component: dict[str, Any],
    lofts: Sequence[Any],
) -> dict[str, Any] | None:
    combined_triangles: list[Triangle3D] = []
    is_mirror = bool(component.get("parameters", {}).get("geometry", {}).get("mirror"))
    for loft in lofts:
        raw_sections = getattr(loft, "sections", ())
        sec_pts: list[list[Point3D]] = []
        for s in raw_sections:
            pts = getattr(s, "points", s)
            if isinstance(pts, (list, tuple)) and len(pts) >= 3:
                sec_pts.append([_to_vec3(p) for p in pts])
        if len(sec_pts) >= 2:
            for i in range(len(sec_pts) - 1):
                combined_triangles.extend(_triangulate_quad_strip(sec_pts[i], sec_pts[i + 1]))
            combined_triangles.extend(_cap_polygon(sec_pts[0], reverse=True))
            combined_triangles.extend(_cap_polygon(sec_pts[-1], reverse=False))

    if not combined_triangles:
        return None

    if is_mirror:
        mirrored: list[Triangle3D] = []
        for p0, p1, p2 in combined_triangles:
            mp0 = (p0[0], -p0[1], p0[2])
            mp1 = (p1[0], -p1[1], p1[2])
            mp2 = (p2[0], -p2[1], p2[2])
            mirrored.append((mp0, mp2, mp1))
        combined_triangles.extend(mirrored)

    vol, centroid, size_box, unit_inertia = compute_mesh_mass_properties(combined_triangles)
    u_ixx, u_iyy, u_izz, u_ixy, u_ixz, u_iyz = unit_inertia
    return {
        "shape": "custom",
        "size_mm": {
            "x": round(size_box[0], 1),
            "y": round(size_box[1], 1),
            "z": round(size_box[2], 1),
        },
        "offset_mm": {
            "x": round(centroid[0], 1),
            "y": round(centroid[1], 1) if not is_mirror else 0.0,
            "z": round(centroid[2], 1),
        },
        "volume_mm3": round(vol, 1),
        "unit_inertia": {
            "ixx": round(u_ixx, 8),
            "iyy": round(u_iyy, 8),
            "izz": round(u_izz, 8),
            "ixy": round(u_ixy, 8) if not is_mirror else 0.0,
            "ixz": round(u_ixz, 8),
            "iyz": round(u_iyz, 8) if not is_mirror else 0.0,
        },
        "sections": [],
        "slices": [],
    }


def resolve_component_envelope(
    component: dict[str, Any],
    lofts: Sequence[Any] | None = None,
    project_or_components: Any = None,
) -> dict[str, Any]:
    """Universal envelope resolver for any component.

    Resolves high-precision envelope from 3D lofts when available; aggregates child
    envelopes for parent assemblies; or falls back to explicit component parameters
    or existing declared envelope.
    """
    # 0. Check if this is an assembly with child components
    if project_or_components is not None and not lofts:
        from setuav_studio.utilities.mass_balance import get_component_children

        comp_id = str(component.get("id") or "")
        if comp_id and get_component_children(comp_id, project_or_components, recursive=False):
            return resolve_component_aggregate_envelope(component, project_or_components)

    # 1. From provided 3D Lofts (e.g. from LoftGeometry or LoftPrimitive)
    if lofts:
        loft_env = _envelope_from_lofts(component, lofts)
        if loft_env is not None:
            return loft_env

    # 2. Existing envelope defined on component
    existing = component.get("envelope")
    if isinstance(existing, dict) and "size_mm" in existing:
        size = _to_vec3(existing.get("size_mm"))
        offset = _to_vec3(existing.get("offset_mm"))
        shape = str(existing.get("shape", "box")).lower()
        if shape == "cylinder":
            d = max(size[1], size[2])
            return compute_cylinder_envelope(d, size[0], offset_mm=offset)
        return compute_box_envelope(size, offset_mm=offset)

    # 3. Direct dimensions in parameters (e.g. length/width/height)
    params = component.get("parameters")
    if isinstance(params, dict):
        lx = float(params.get("length", params.get("x", 0.0)) or 0.0)
        ly = float(params.get("width", params.get("wingspan", params.get("span", 0.0))) or 0.0)
        lz = float(params.get("height", params.get("thickness", 0.0)) or 0.0)
        if lx > 0.0 or ly > 0.0 or lz > 0.0:
            size_vec = (max(lx, 1.0), max(ly, 1.0), max(lz, 1.0))
            return compute_box_envelope(size_vec, offset_mm=(lx * 0.5, 0.0, 0.0))

    return _empty_envelope()


def resolve_component_aggregate_envelope(
    component: dict[str, Any],
    project_or_components: Any = None,
) -> dict[str, Any]:
    """Resolve aggregate bounding envelope for a component, unioning all its children if any exist."""
    comp_id = str(component.get("id") or "")
    if not comp_id or project_or_components is None:
        return resolve_component_envelope(component)

    from setuav_studio.utilities.mass_balance import get_component_children
    from setuav_studio.utilities.transform import (
        inverse_rotate_vector,
        resolve_world_transform,
        rotate_vector,
    )

    children = get_component_children(comp_id, project_or_components, recursive=True)
    if not children:
        return resolve_component_envelope(component)

    # 1. World transform of the parent component
    p_world_pos, p_world_rot = resolve_world_transform(comp_id, project_or_components)

    corners_in_parent: list[Point3D] = []
    total_volume_mm3 = 0.0

    # 2. Check parent's own intrinsic envelope
    parent_env = resolve_component_envelope(component)
    p_size = _to_vec3(parent_env.get("size_mm"))
    if p_size[0] > 0.0 or p_size[1] > 0.0 or p_size[2] > 0.0:
        p_offset = _to_vec3(parent_env.get("offset_mm"))
        total_volume_mm3 += float(parent_env.get("volume_mm3", 0.0) or 0.0)
        for dx in (-0.5 * p_size[0], 0.5 * p_size[0]):
            for dy in (-0.5 * p_size[1], 0.5 * p_size[1]):
                for dz in (-0.5 * p_size[2], 0.5 * p_size[2]):
                    corners_in_parent.append((p_offset[0] + dx, p_offset[1] + dy, p_offset[2] + dz))

    # 3. Add all child envelopes transformed into parent's coordinate frame
    for child in children:
        c_id = str(child.get("id") or "")
        c_env = resolve_component_envelope(child)
        c_size = _to_vec3(c_env.get("size_mm"))
        c_offset = _to_vec3(c_env.get("offset_mm"))
        total_volume_mm3 += float(c_env.get("volume_mm3", 0.0) or 0.0)

        c_world_pos, c_world_rot = resolve_world_transform(c_id, project_or_components)
        is_mirror = bool(child.get("parameters", {}).get("geometry", {}).get("mirror"))

        # 8 corners in child's local frame
        for dx in (-0.5 * c_size[0], 0.5 * c_size[0]):
            for dy in (-0.5 * c_size[1], 0.5 * c_size[1]):
                for dz in (-0.5 * c_size[2], 0.5 * c_size[2]):
                    local_pt = (c_offset[0] + dx, c_offset[1] + dy, c_offset[2] + dz)
                    rx, ry, rz = rotate_vector(local_pt, c_world_rot)
                    world_pt = (c_world_pos[0] + rx, c_world_pos[1] + ry, c_world_pos[2] + rz)

                    # Transform into parent's coordinate frame
                    delta = (
                        world_pt[0] - p_world_pos[0],
                        world_pt[1] - p_world_pos[1],
                        world_pt[2] - p_world_pos[2],
                    )
                    parent_pt = inverse_rotate_vector(delta, p_world_rot)
                    corners_in_parent.append(parent_pt)

                    if is_mirror:
                        mirrored_world = (world_pt[0], -world_pt[1], world_pt[2])
                        delta_m = (
                            mirrored_world[0] - p_world_pos[0],
                            mirrored_world[1] - p_world_pos[1],
                            mirrored_world[2] - p_world_pos[2],
                        )
                        parent_m_pt = inverse_rotate_vector(delta_m, p_world_rot)
                        corners_in_parent.append(parent_m_pt)

    if not corners_in_parent:
        return _empty_envelope()

    min_x = min(pt[0] for pt in corners_in_parent)
    max_x = max(pt[0] for pt in corners_in_parent)
    min_y = min(pt[1] for pt in corners_in_parent)
    max_y = max(pt[1] for pt in corners_in_parent)
    min_z = min(pt[2] for pt in corners_in_parent)
    max_z = max(pt[2] for pt in corners_in_parent)

    size_x = max(max_x - min_x, 1.0)
    size_y = max(max_y - min_y, 1.0)
    size_z = max(max_z - min_z, 1.0)

    offset_x = (min_x + max_x) * 0.5
    offset_y = (min_y + max_y) * 0.5
    offset_z = (min_z + max_z) * 0.5

    box_env = compute_box_envelope((size_x, size_y, size_z), (offset_x, offset_y, offset_z))
    if total_volume_mm3 > 0.0:
        box_env["volume_mm3"] = round(total_volume_mm3, 1)
    return box_env


def _empty_envelope() -> dict[str, Any]:
    return {
        "shape": "box",
        "size_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        "volume_mm3": 0.0,
        "unit_inertia": {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0},
        "sections": [],
        "slices": [],
    }
