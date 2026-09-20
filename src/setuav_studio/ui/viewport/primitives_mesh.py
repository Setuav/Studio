"""OpenGL vertex generation for SDK VisualPrimitives (solid, wireframe, highlight, annotations)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise

from setuav_studio_sdk.primitives import (
    BoxPrimitive,
    CylinderPrimitive,
    LineSegmentsPrimitive,
    LoftPrimitive,
    PlanePrimitive,
    Point3D,
    RingPrimitive,
    TrianglesPrimitive,
    VisualPrimitive,
)

from .constants import (
    FACE_COLORED,
    FACE_TRANSPARENT,
    WIRE_FEATURE,
    WIRE_FULL,
)
from .loft_mesh import (
    _SOLID_GREY,
    _WIRE_GREY,
    FEATURE_EDGE_COLOR,
    SELECTED_WIRE,
    _add_line,
    _add_quad_strip,
    _add_triangle,
    _append_loft_feature_wire,
    _append_loft_wire,
    _append_ring,
    _cap_loop,
    _tessellated_loops,
)
from .raycast import _box_corners, _ortho_basis
from .types import LoftGeometry, Section


def build_primitive_solid_vertices(  # noqa: C901
    primitives: Sequence[VisualPrimitive],
    face_style: str = FACE_COLORED,
) -> list[float]:
    vertices: list[float] = []
    for prim in primitives:
        if not getattr(prim, "solid", True):
            continue
        raw_color = prim.color
        color = raw_color[:3] if face_style in (FACE_COLORED, FACE_TRANSPARENT) else _SOLID_GREY

        if isinstance(prim, BoxPrimitive):
            c = _box_corners(prim.center, prim.size, getattr(prim, "rotation", (0.0, 0.0, 0.0)))
            faces = (
                (c[0], c[1], c[2], c[3]),
                (c[4], c[7], c[6], c[5]),
                (c[0], c[4], c[5], c[1]),
                (c[2], c[6], c[7], c[3]),
                (c[0], c[3], c[7], c[4]),
                (c[1], c[5], c[6], c[2]),
            )
            for p0, p1, p2, p3 in faces:
                _add_triangle(vertices, p0, p1, p2, color)
                _add_triangle(vertices, p0, p2, p3, color)

        elif isinstance(prim, CylinderPrimitive):
            p1, p2 = prim.start, prim.end
            axis = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
            axis_len = math.sqrt(sum(a * a for a in axis))
            if axis_len < 1e-6:
                continue
            u, v = _ortho_basis(axis)
            r = prim.radius
            segs = getattr(prim, "segments", 24)

            ring1: list[Point3D] = []
            ring2: list[Point3D] = []
            for i in range(segs):
                angle = 2.0 * math.pi * i / segs
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                offset = (
                    r * (cos_a * u[0] + sin_a * v[0]),
                    r * (cos_a * u[1] + sin_a * v[1]),
                    r * (cos_a * u[2] + sin_a * v[2]),
                )
                ring1.append((p1[0] + offset[0], p1[1] + offset[1], p1[2] + offset[2]))
                ring2.append((p2[0] + offset[0], p2[1] + offset[1], p2[2] + offset[2]))

            _add_quad_strip(vertices, ring1, ring2, color)
            _cap_loop(vertices, ring1, color, flip=True)
            _cap_loop(vertices, ring2, color, flip=False)

        elif isinstance(prim, PlanePrimitive):
            cx, cy, cz = prim.center
            u, v = _ortho_basis(prim.normal)
            hw, hh = prim.width * 0.5, prim.height * 0.5
            p0 = (
                cx - hw * u[0] - hh * v[0],
                cy - hw * u[1] - hh * v[1],
                cz - hw * u[2] - hh * v[2],
            )
            p1 = (
                cx + hw * u[0] - hh * v[0],
                cy + hw * u[1] - hh * v[1],
                cz + hw * u[2] - hh * v[2],
            )
            p2 = (
                cx + hw * u[0] + hh * v[0],
                cy + hw * u[1] + hh * v[1],
                cz + hw * u[2] + hh * v[2],
            )
            p3 = (
                cx - hw * u[0] + hh * v[0],
                cy - hw * u[1] + hh * v[1],
                cz - hw * u[2] + hh * v[2],
            )

            _add_triangle(vertices, p0, p1, p2, color)
            _add_triangle(vertices, p0, p2, p3, color)
            _add_triangle(vertices, p0, p2, p1, color)
            _add_triangle(vertices, p0, p3, p2, color)

        elif isinstance(prim, TrianglesPrimitive):
            if not getattr(prim, "solid", True):
                continue
            for p0, p1, p2 in prim.triangles:
                _add_triangle(vertices, p0, p1, p2, color)

        elif isinstance(prim, LoftPrimitive):
            if not getattr(prim, "solid", True) or not prim.sections or len(prim.sections) < 2:
                continue
            loft = LoftGeometry(
                component_id="primitive:loft",
                sections=tuple(Section(pts) for pts in prim.sections),
                color=color,
                interpolation=getattr(prim, "interpolation", "smooth"),
                parameterization=getattr(prim, "parameterization", "centripetal"),
                station_spacing=getattr(prim, "station_spacing", 10.0),
                closed_ends=getattr(prim, "closed_ends", True),
            )
            loops = _tessellated_loops(loft)
            if len(loops) >= 2:
                for first, second in pairwise(loops):
                    _add_quad_strip(vertices, first, second, color)
                if loft.closed_ends:
                    _cap_loop(vertices, loops[0], color, flip=True)
                    _cap_loop(vertices, loops[-1], color, flip=False)

    return vertices


def build_primitive_wire_vertices(  # noqa: C901
    primitives: Sequence[VisualPrimitive],
    face_style: str = FACE_COLORED,
    wire_mode: str = WIRE_FEATURE,
) -> list[float]:
    vertices: list[float] = []
    for prim in primitives:
        color = FEATURE_EDGE_COLOR if face_style in (FACE_COLORED, FACE_TRANSPARENT) else _WIRE_GREY

        if isinstance(prim, BoxPrimitive):
            if not getattr(prim, "wireframe", True):
                continue
            c = _box_corners(prim.center, prim.size, getattr(prim, "rotation", (0.0, 0.0, 0.0)))
            edges = (
                (0, 1),
                (1, 2),
                (2, 3),
                (3, 0),
                (4, 5),
                (5, 6),
                (6, 7),
                (7, 4),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
            )
            for i1, i2 in edges:
                _add_line(vertices, c[i1], c[i2], color)
            if wire_mode == WIRE_FULL:
                for i1, i2 in ((0, 2), (4, 6), (0, 5), (2, 7), (0, 7), (1, 6)):
                    _add_line(vertices, c[i1], c[i2], color)

        elif isinstance(prim, CylinderPrimitive):
            if not getattr(prim, "wireframe", True):
                continue
            p1, p2 = prim.start, prim.end
            axis = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
            axis_len = math.sqrt(sum(a * a for a in axis))
            if axis_len < 1e-6:
                continue
            u, v = _ortho_basis(axis)
            r = prim.radius
            segs = getattr(prim, "segments", 24)

            ring1: list[Point3D] = []
            ring2: list[Point3D] = []
            for i in range(segs):
                angle = 2.0 * math.pi * i / segs
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                offset = (
                    r * (cos_a * u[0] + sin_a * v[0]),
                    r * (cos_a * u[1] + sin_a * v[1]),
                    r * (cos_a * u[2] + sin_a * v[2]),
                )
                ring1.append((p1[0] + offset[0], p1[1] + offset[1], p1[2] + offset[2]))
                ring2.append((p2[0] + offset[0], p2[1] + offset[1], p2[2] + offset[2]))

            _append_ring(vertices, ring1, color)
            _append_ring(vertices, ring2, color)
            if wire_mode == WIRE_FULL:
                for idx in range(segs):
                    _add_line(vertices, ring1[idx], ring2[idx], color)
            else:
                for idx in (0, segs // 4, segs // 2, (3 * segs) // 4):
                    _add_line(vertices, ring1[idx], ring2[idx], color)

        elif isinstance(prim, PlanePrimitive):
            if not getattr(prim, "wireframe", True):
                continue
            cx, cy, cz = prim.center
            u, v = _ortho_basis(prim.normal)
            hw, hh = prim.width * 0.5, prim.height * 0.5
            p0 = (
                cx - hw * u[0] - hh * v[0],
                cy - hw * u[1] - hh * v[1],
                cz - hw * u[2] - hh * v[2],
            )
            p1 = (
                cx + hw * u[0] - hh * v[0],
                cy + hw * u[1] - hh * v[1],
                cz + hw * u[2] - hh * v[2],
            )
            p2 = (
                cx + hw * u[0] + hh * v[0],
                cy + hw * u[1] + hh * v[1],
                cz + hw * u[2] + hh * v[2],
            )
            p3 = (
                cx - hw * u[0] + hh * v[0],
                cy - hw * u[1] + hh * v[1],
                cz - hw * u[2] - hh * v[2],
            )
            _append_ring(vertices, (p0, p1, p2, p3), color)
            if wire_mode == WIRE_FULL:
                _add_line(vertices, p0, p2, color)
                _add_line(vertices, p1, p3, color)

        elif isinstance(prim, TrianglesPrimitive):
            for p0, p1, p2 in prim.triangles:
                _add_line(vertices, p0, p1, color)
                _add_line(vertices, p1, p2, color)
                _add_line(vertices, p2, p0, color)

        elif isinstance(prim, LoftPrimitive):
            if not getattr(prim, "wireframe", True) or not prim.sections or len(prim.sections) < 2:
                continue
            loft = LoftGeometry(
                component_id="primitive:loft",
                sections=tuple(Section(pts) for pts in prim.sections),
                color=color,
                interpolation=getattr(prim, "interpolation", "smooth"),
                parameterization=getattr(prim, "parameterization", "centripetal"),
                station_spacing=getattr(prim, "station_spacing", 10.0),
                closed_ends=getattr(prim, "closed_ends", True),
            )
            loops = _tessellated_loops(loft)
            if loops:
                if wire_mode == WIRE_FEATURE:
                    _append_loft_feature_wire(vertices, loft, loops, color)
                else:
                    _append_loft_wire(vertices, loops, color)

    return vertices


def build_primitive_annotation_vertices(
    primitives: Sequence[VisualPrimitive],
    face_style: str = FACE_COLORED,
) -> list[float]:
    """Build vertices for line-based annotation primitives (rings, lines)."""
    vertices: list[float] = []
    for prim in primitives:
        raw_color = prim.color
        color = raw_color[:3] if face_style in (FACE_COLORED, FACE_TRANSPARENT) else _WIRE_GREY

        if isinstance(prim, RingPrimitive):
            cx, cy, cz = prim.center
            u, v = _ortho_basis(prim.normal)
            r = prim.radius
            segs = getattr(prim, "segments", 36)
            ring: list[Point3D] = []
            for i in range(segs):
                angle = 2.0 * math.pi * i / segs
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                ring.append(
                    (
                        cx + r * (cos_a * u[0] + sin_a * v[0]),
                        cy + r * (cos_a * u[1] + sin_a * v[1]),
                        cz + r * (cos_a * u[2] + sin_a * v[2]),
                    )
                )
            _append_ring(vertices, ring, color)

        elif isinstance(prim, LineSegmentsPrimitive):
            for start, end in prim.lines:
                _add_line(vertices, start, end, color)

    return vertices


def build_primitive_highlight_vertices(  # noqa: C901
    primitives: Sequence[VisualPrimitive],
    color: Point3D = SELECTED_WIRE,
) -> list[float]:
    """Build wireframe highlight vertices in specified highlight color for primitives."""
    vertices: list[float] = []
    for prim in primitives:
        if isinstance(prim, BoxPrimitive):
            c = _box_corners(prim.center, prim.size, getattr(prim, "rotation", (0.0, 0.0, 0.0)))
            edges = (
                (0, 1),
                (1, 2),
                (2, 3),
                (3, 0),
                (4, 5),
                (5, 6),
                (6, 7),
                (7, 4),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
            )
            for i1, i2 in edges:
                _add_line(vertices, c[i1], c[i2], color)

        elif isinstance(prim, CylinderPrimitive):
            p1, p2 = prim.start, prim.end
            axis = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
            axis_len = math.sqrt(sum(a * a for a in axis))
            if axis_len < 1e-6:
                continue
            u, v = _ortho_basis(axis)
            r = prim.radius
            segs = getattr(prim, "segments", 24)

            ring1: list[Point3D] = []
            ring2: list[Point3D] = []
            for i in range(segs):
                angle = 2.0 * math.pi * i / segs
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                offset = (
                    r * (cos_a * u[0] + sin_a * v[0]),
                    r * (cos_a * u[1] + sin_a * v[1]),
                    r * (cos_a * u[2] + sin_a * v[2]),
                )
                ring1.append((p1[0] + offset[0], p1[1] + offset[1], p1[2] + offset[2]))
                ring2.append((p2[0] + offset[0], p2[1] + offset[1], p2[2] + offset[2]))

            _append_ring(vertices, ring1, color)
            _append_ring(vertices, ring2, color)
            for idx in (0, segs // 4, segs // 2, (3 * segs) // 4):
                _add_line(vertices, ring1[idx], ring2[idx], color)

        elif isinstance(prim, PlanePrimitive):
            cx, cy, cz = prim.center
            u, v = _ortho_basis(prim.normal)
            hw, hh = prim.width * 0.5, prim.height * 0.5
            p0 = (
                cx - hw * u[0] - hh * v[0],
                cy - hw * u[1] - hh * v[1],
                cz - hw * u[2] - hh * v[2],
            )
            p1 = (
                cx + hw * u[0] - hh * v[0],
                cy + hw * u[1] - hh * v[1],
                cz + hw * u[2] - hh * v[2],
            )
            p2 = (
                cx + hw * u[0] + hh * v[0],
                cy + hw * u[1] + hh * v[1],
                cz + hw * u[2] + hh * v[2],
            )
            p3 = (
                cx - hw * u[0] + hh * v[0],
                cy - hw * u[1] + hh * v[1],
                cz - hw * u[2] - hh * v[2],
            )
            _append_ring(vertices, (p0, p1, p2, p3), color)

        elif isinstance(prim, RingPrimitive):
            cx, cy, cz = prim.center
            u, v = _ortho_basis(prim.normal)
            r = prim.radius
            segs = getattr(prim, "segments", 36)
            ring: list[Point3D] = []
            for i in range(segs):
                angle = 2.0 * math.pi * i / segs
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                ring.append(
                    (
                        cx + r * (cos_a * u[0] + sin_a * v[0]),
                        cy + r * (cos_a * u[1] + sin_a * v[1]),
                        cz + r * (cos_a * u[2] + sin_a * v[2]),
                    )
                )
            _append_ring(vertices, ring, color)

        elif isinstance(prim, LineSegmentsPrimitive):
            for start, end in prim.lines:
                _add_line(vertices, start, end, color)

        elif isinstance(prim, TrianglesPrimitive):
            for p0, p1, p2 in prim.triangles:
                _add_line(vertices, p0, p1, color)
                _add_line(vertices, p1, p2, color)
                _add_line(vertices, p2, p0, color)

        elif isinstance(prim, LoftPrimitive):
            if not prim.sections or len(prim.sections) < 2:
                continue
            loft = LoftGeometry(
                component_id="primitive:loft",
                sections=tuple(Section(pts) for pts in prim.sections),
                color=color,
                interpolation=getattr(prim, "interpolation", "smooth"),
                parameterization=getattr(prim, "parameterization", "centripetal"),
                station_spacing=getattr(prim, "station_spacing", 10.0),
                closed_ends=getattr(prim, "closed_ends", True),
            )
            loops = _tessellated_loops(loft)
            if loops:
                _append_loft_feature_wire(vertices, loft, loops, color)

    return vertices
