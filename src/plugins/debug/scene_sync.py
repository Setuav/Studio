"""Synchronization between project debug components and 3D Viewport."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .components import (
    TYPE_DEBUG_ARROW,
    TYPE_DEBUG_BOX,
    TYPE_DEBUG_CYLINDER,
    TYPE_DEBUG_LINE,
    TYPE_DEBUG_LOFT,
    TYPE_DEBUG_PLANE,
    TYPE_DEBUG_POINT,
    TYPE_DEBUG_RING,
    TYPE_DEBUG_TRIANGLE,
    parse_color_rgba,
)

DEBUG_LAYER = "debug"


def _naca_airfoil_loop(
    chord: float = 200.0,
    origin_x: float = 0.0,
    y: float = 0.0,
    origin_z: float = 0.0,
    thickness: float = 0.12,
    points_per_side: int = 16,
) -> tuple[tuple[float, float, float], ...]:
    """Generate a closed loop of (x, y, z) points describing a symmetric NACA airfoil."""
    pts: list[tuple[float, float, float]] = []
    # Upper surface: trailing edge to leading edge
    for i in range(points_per_side, -1, -1):
        x_frac = (1.0 - math.cos(i * math.pi / points_per_side)) / 2.0
        yt = (
            5.0
            * thickness
            * (
                0.2969 * math.sqrt(x_frac)
                - 0.1260 * x_frac
                - 0.3516 * (x_frac**2)
                + 0.2843 * (x_frac**3)
                - 0.1015 * (x_frac**4)
            )
        )
        px = origin_x + x_frac * chord
        pz = origin_z + yt * chord
        pts.append((px, y, pz))
    # Lower surface: leading edge back to trailing edge
    for i in range(1, points_per_side + 1):
        x_frac = (1.0 - math.cos(i * math.pi / points_per_side)) / 2.0
        yt = (
            5.0
            * thickness
            * (
                0.2969 * math.sqrt(x_frac)
                - 0.1260 * x_frac
                - 0.3516 * (x_frac**2)
                + 0.2843 * (x_frac**3)
                - 0.1015 * (x_frac**4)
            )
        )
        px = origin_x + x_frac * chord
        pz = origin_z - yt * chord
        pts.append((px, y, pz))
    return tuple(pts)


def _render_box(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    dx = float(params.get("length", 200.0))
    dy = float(params.get("width", 150.0))
    dz = float(params.get("height", 100.0))
    color = parse_color_rgba(params.get("color", "#4A90E2"))
    viewport.add_box(
        comp_id,
        center=(px, py, pz),
        size=(dx, dy, dz),
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


def _render_cylinder(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    radius = float(params.get("radius", 50.0))
    length = float(params.get("length", 200.0))
    axis = str(params.get("axis", "Z")).upper()
    segments = int(params.get("segments", 32))
    color = parse_color_rgba(params.get("color", "#E67E22"))
    half = length / 2.0
    if axis == "X":
        start = (px - half, py, pz)
        end = (px + half, py, pz)
    elif axis == "Y":
        start = (px, py - half, pz)
        end = (px, py + half, pz)
    else:
        start = (px, py, pz - half)
        end = (px, py, pz + half)
    viewport.add_cylinder(
        comp_id,
        start=start,
        end=end,
        radius=radius,
        segments=segments,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


def _render_ring(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    outer_r = float(params.get("outer_radius", 125.0))
    axis = str(params.get("axis", "Z")).upper()
    normal = (
        (1.0, 0.0, 0.0) if axis == "X" else ((0.0, 1.0, 0.0) if axis == "Y" else (0.0, 0.0, 1.0))
    )
    color = parse_color_rgba(params.get("color", "#F1C40F"))
    viewport.add_ring(
        comp_id,
        center=(px, py, pz),
        normal=normal,
        radius=outer_r,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


def _render_plane(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    w = float(params.get("width", 200.0))
    length = float(params.get("length", 200.0))
    axis = str(params.get("axis", "XY")).upper()
    color = parse_color_rgba(params.get("color", "#2ECC71"))
    normal = (
        (0.0, 1.0, 0.0) if axis == "XZ" else ((1.0, 0.0, 0.0) if axis == "YZ" else (0.0, 0.0, 1.0))
    )
    viewport.add_plane(
        comp_id,
        center=(px, py, pz),
        normal=normal,
        width=w,
        height=length,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


def _render_line(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    length = float(params.get("length", 200.0))
    axis = str(params.get("axis", "X")).upper()
    color = parse_color_rgba(params.get("color", "#E74C3C"))
    half = length / 2.0
    if axis == "Y":
        line_pts = ((px, py - half, pz), (px, py + half, pz))
    elif axis == "Z":
        line_pts = ((px, py, pz - half), (px, py, pz + half))
    else:
        line_pts = ((px - half, py, pz), (px + half, py, pz))
    viewport.add_lines(
        comp_id,
        lines=[line_pts],
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


def _render_triangle(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    bw = float(params.get("base_width", 150.0))
    h = float(params.get("height", 150.0))
    color = parse_color_rgba(params.get("color", "#9B59B6"))
    p0 = (px - bw / 2.0, py, pz)
    p1 = (px + bw / 2.0, py, pz)
    p2 = (px, py, pz + h)
    tris = [(p0, p1, p2), (p0, p2, p1)]
    viewport.add_triangles(
        comp_id,
        triangles=tris,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


def _render_loft(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    span = float(params.get("span", 400.0))
    rc = float(params.get("root_chord", 180.0))
    tc = float(params.get("tip_chord", 90.0))
    sweep_deg = float(params.get("sweep", 5.0))
    dihedral_deg = float(params.get("dihedral", 2.0))
    color = parse_color_rgba(params.get("color", "#3498DB"))
    sweep_rad = math.radians(sweep_deg)
    dih_rad = math.radians(dihedral_deg)
    tip_x = px + span * math.sin(sweep_rad)
    tip_y = py + span * math.cos(dih_rad)
    tip_z = pz + span * math.sin(dih_rad)
    mid_x = (px + tip_x) / 2.0
    mid_y = (py + tip_y) / 2.0
    mid_z = (pz + tip_z) / 2.0
    mid_chord = (rc + tc) / 2.0
    sec_root = _naca_airfoil_loop(chord=rc, origin_x=px, y=py, origin_z=pz)
    sec_mid = _naca_airfoil_loop(chord=mid_chord, origin_x=mid_x, y=mid_y, origin_z=mid_z)
    sec_tip = _naca_airfoil_loop(chord=tc, origin_x=tip_x, y=tip_y, origin_z=tip_z)
    viewport.add_loft(
        comp_id,
        sections=[sec_root, sec_mid, sec_tip],
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


def _render_point(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    count = max(1, int(params.get("count", 100)))
    radius = float(params.get("radius", 150.0))
    pt_size = float(params.get("point_size", 4.0))
    color = parse_color_rgba(params.get("color", "#E74C3C"))
    pts = []
    phi = math.pi * (math.sqrt(5.0) - 1.0)
    for i in range(count):
        y_norm = 1.0 - (i / float(count - 1)) * 2.0 if count > 1 else 0.0
        r_y = math.sqrt(max(0.0, 1.0 - y_norm * y_norm))
        theta = phi * i
        pts.append(
            (
                px + math.cos(theta) * r_y * radius,
                py + math.sin(theta) * r_y * radius,
                pz + y_norm * radius,
            )
        )
    viewport.add_points(
        comp_id,
        points=pts,
        size=pt_size,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


def _render_arrow(
    viewport: Any,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
) -> None:
    length = float(params.get("length", 150.0))
    axis = str(params.get("axis", "All"))
    color = parse_color_rgba(params.get("color", "#1ABC9C"))
    if axis == "X":
        arrows = [((px, py, pz), (px + length, py, pz))]
    elif axis == "Y":
        arrows = [((px, py, pz), (px, py + length, pz))]
    elif axis == "Z":
        arrows = [((px, py, pz), (px, py, pz + length))]
    else:
        arrows = [
            ((px, py, pz), (px + length, py, pz)),
            ((px, py, pz), (px, py + length, pz)),
            ((px, py, pz), (px, py, pz + length)),
        ]
    viewport.add_arrows(
        comp_id,
        arrows=arrows,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
    )


_RENDERERS: dict[
    str,
    Callable[[Any, str, str, dict[str, Any], float, float, float], None],
] = {
    TYPE_DEBUG_BOX: _render_box,
    TYPE_DEBUG_CYLINDER: _render_cylinder,
    TYPE_DEBUG_RING: _render_ring,
    TYPE_DEBUG_PLANE: _render_plane,
    TYPE_DEBUG_LINE: _render_line,
    TYPE_DEBUG_TRIANGLE: _render_triangle,
    TYPE_DEBUG_LOFT: _render_loft,
    TYPE_DEBUG_POINT: _render_point,
    TYPE_DEBUG_ARROW: _render_arrow,
}


def sync_debug_components_to_viewport(viewport: Any, project: Any) -> None:
    """Read all debug components from the project and render or update them in the viewport."""
    if viewport is None:
        return
    if project is None:
        viewport.clear(layer=DEBUG_LAYER)
        return

    comps = project.data.get("components", [])
    if not isinstance(comps, list):
        viewport.clear(layer=DEBUG_LAYER)
        return

    debug_components = [
        c
        for c in comps
        if isinstance(c, dict) and str(c.get("type", "")).startswith("org.setuav.debug:")
    ]

    existing_ids = set(viewport.object_ids(layer=DEBUG_LAYER))
    active_ids = {str(c.get("id")) for c in debug_components}

    # Remove deleted objects from viewport
    for oid in existing_ids - active_ids:
        viewport.remove(oid)

    for comp in debug_components:
        comp_id = str(comp.get("id"))
        name = str(comp.get("name") or comp_id)
        raw_params = comp.get("parameters")
        params: dict[str, Any] = dict(raw_params) if isinstance(raw_params, dict) else {}
        raw_transform = comp.get("transform")
        raw_pos = raw_transform.get("position") if isinstance(raw_transform, dict) else None
        pos = raw_pos if isinstance(raw_pos, dict) else {}
        px = float(pos.get("x", 0.0))
        py = float(pos.get("y", 0.0))
        pz = float(pos.get("z", 0.0))
        ctype = str(comp.get("type", ""))

        renderer = _RENDERERS.get(ctype)
        if renderer is not None:
            renderer(viewport, comp_id, name, params, px, py, pz)
