"""3D raycasting, hit testing, and geometric intersection math."""

from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import pairwise

from .loft_mesh import _centroid, tessellated_loops
from .primitives import (
    BoxPrimitive,
    CylinderPrimitive,
    LoftPrimitive,
    PlanePrimitive,
    Point3D,
    RingPrimitive,
    TrianglesPrimitive,
    VisualPrimitive,
)
from .scene_object import SceneObject
from .types import LoftGeometry, Section


def _dot(left: Point3D, right: Point3D) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(left: Point3D, right: Point3D) -> Point3D:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _subtract(left: Point3D, right: Point3D) -> Point3D:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _ortho_basis(normal: Point3D) -> tuple[Point3D, Point3D]:
    nx, ny, nz = normal
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length > 1e-9:
        nx, ny, nz = nx / length, ny / length, nz / length
    else:
        nx, ny, nz = 0.0, 0.0, 1.0

    if abs(nx) < 0.9:
        ax, ay, az = 1.0, 0.0, 0.0
    else:
        ax, ay, az = 0.0, 1.0, 0.0

    ux = ny * az - nz * ay
    uy = nz * ax - nx * az
    uz = nx * ay - ny * ax
    u_len = math.sqrt(ux * ux + uy * uy + uz * uz)
    u = (ux / u_len, uy / u_len, uz / u_len)

    vx = ny * u[2] - nz * u[1]
    vy = nz * u[0] - nx * u[2]
    vz = nx * u[1] - ny * u[0]
    v = (vx, vy, vz)
    return u, v


def _box_corners(
    center: Point3D,
    size: Point3D,
    rotation: Point3D = (0.0, 0.0, 0.0),
) -> list[Point3D]:
    cx, cy, cz = center
    sx, sy, sz = size
    hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
    raw_corners = (
        (-hx, -hy, -hz),
        (hx, -hy, -hz),
        (hx, hy, -hz),
        (-hx, hy, -hz),
        (-hx, -hy, hz),
        (hx, -hy, hz),
        (hx, hy, hz),
        (-hx, hy, hz),
    )
    roll, pitch, yaw = rotation if len(rotation) >= 3 else (0.0, 0.0, 0.0)
    if abs(roll) > 1e-6 or abs(pitch) > 1e-6 or abs(yaw) > 1e-6:
        r = math.radians(roll)
        p = math.radians(pitch)
        y_rad = math.radians(yaw)
        cr, sr = math.cos(r), math.sin(r)
        cp, sp = math.cos(p), math.sin(p)
        cy, sy = math.cos(y_rad), math.sin(y_rad)
        rotated: list[Point3D] = []
        for x, y, z in raw_corners:
            rx = (cp * cy) * x + (cy * sp * sr - sy * cr) * y + (cy * sp * cr + sy * sr) * z
            ry = (cp * sy) * x + (sy * sp * sr + cy * cr) * y + (sy * sp * cr - cy * sr) * z
            rz = (-sp) * x + (cp * sr) * y + (cp * cr) * z
            rotated.append((cx + rx, cy + ry, cz + rz))
        return rotated
    return [(cx + x, cy + y, cz + z) for x, y, z in raw_corners]


def _ray_triangle_intersection(
    origin: Point3D,
    direction: Point3D,
    triangle: tuple[Point3D, Point3D, Point3D],
) -> float | None:
    first, second, third = triangle
    edge1 = _subtract(second, first)
    edge2 = _subtract(third, first)
    cross = _cross(direction, edge2)
    determinant = _dot(edge1, cross)
    if abs(determinant) < 1e-9:
        return None
    inverse = 1.0 / determinant
    offset = _subtract(origin, first)
    u = _dot(offset, cross) * inverse
    if u < 0.0 or u > 1.0:
        return None
    perpendicular = _cross(offset, edge1)
    v = _dot(direction, perpendicular) * inverse
    if v < 0.0 or u + v > 1.0:
        return None
    distance = _dot(edge2, perpendicular) * inverse
    return distance if distance >= 0.0 else None


def _loft_cap_hit_distance(
    loft: LoftGeometry,
    loops: list[tuple[Point3D, ...]],
    origin: Point3D,
    direction: Point3D,
    current_best: float | None,
) -> float | None:
    if not loft.closed_ends:
        return None
    best = current_best
    found = False
    for loop, flip in ((loops[0], True), (loops[-1], False)):
        centre = _centroid(loop)
        for index, point in enumerate(loop):
            following = loop[(index + 1) % len(loop)]
            triangle = (centre, following, point) if flip else (centre, point, following)
            distance = _ray_triangle_intersection(origin, direction, triangle)
            if distance is not None and (best is None or distance < best):
                best = distance
                found = True
    return best if found else None


def _ray_primitive_intersection(  # noqa: C901
    origin: Point3D,
    direction: Point3D,
    prim: VisualPrimitive,
) -> float | None:
    best: float | None = None

    if isinstance(prim, BoxPrimitive):
        c = _box_corners(prim.center, prim.size, prim.rotation)
        faces = (
            (c[0], c[1], c[2], c[3]),
            (c[4], c[7], c[6], c[5]),
            (c[0], c[4], c[5], c[1]),
            (c[2], c[6], c[7], c[3]),
            (c[0], c[3], c[7], c[4]),
            (c[1], c[5], c[6], c[2]),
        )
        for p0, p1, p2, p3 in faces:
            for tri in ((p0, p1, p2), (p0, p2, p3)):
                d = _ray_triangle_intersection(origin, direction, tri)
                if d is not None and (best is None or d < best):
                    best = d

    elif isinstance(prim, CylinderPrimitive):
        p1, p2 = prim.start, prim.end
        axis = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
        axis_len = math.sqrt(sum(a * a for a in axis))
        if axis_len > 1e-6:
            u, v = _ortho_basis(axis)
            r = prim.radius
            segs = prim.segments
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

            for i in range(segs):
                nxt = (i + 1) % segs
                for tri in (
                    (ring1[i], ring1[nxt], ring2[i]),
                    (ring1[nxt], ring2[nxt], ring2[i]),
                    (p1, ring1[nxt], ring1[i]),
                    (p2, ring2[i], ring2[nxt]),
                ):
                    d = _ray_triangle_intersection(origin, direction, tri)
                    if d is not None and (best is None or d < best):
                        best = d

    elif isinstance(prim, PlanePrimitive):
        cx, cy, cz = prim.center
        u, v = _ortho_basis(prim.normal)
        hw, hh = prim.width * 0.5, prim.height * 0.5
        p0 = (cx - hw * u[0] - hh * v[0], cy - hw * u[1] - hh * v[1], cz - hw * u[2] - hh * v[2])
        p1 = (cx + hw * u[0] - hh * v[0], cy + hw * u[1] - hh * v[1], cz + hw * u[2] - hh * v[2])
        p2 = (cx + hw * u[0] + hh * v[0], cy + hw * u[1] + hh * v[1], cz + hw * u[2] + hh * v[2])
        p3 = (cx - hw * u[0] + hh * v[0], cy - hw * u[1] + hh * v[1], cz - hw * u[2] + hh * v[2])
        for tri in ((p0, p1, p2), (p0, p2, p3)):
            d = _ray_triangle_intersection(origin, direction, tri)
            if d is not None and (best is None or d < best):
                best = d

    elif isinstance(prim, TrianglesPrimitive):
        for tri in prim.triangles:
            d = _ray_triangle_intersection(origin, direction, tri)
            if d is not None and (best is None or d < best):
                best = d

    elif isinstance(prim, RingPrimitive):
        n_len = math.sqrt(sum(c * c for c in prim.normal))
        if n_len > 1e-9:
            normal = (prim.normal[0] / n_len, prim.normal[1] / n_len, prim.normal[2] / n_len)
            denom = _dot(normal, direction)
            if abs(denom) > 1e-9:
                offset = _subtract(prim.center, origin)
                t = _dot(offset, normal) / denom
                if t >= 0.0:
                    hit_pt = (
                        origin[0] + t * direction[0],
                        origin[1] + t * direction[1],
                        origin[2] + t * direction[2],
                    )
                    dist_sq = sum((hit_pt[i] - prim.center[i]) ** 2 for i in range(3))
                    if dist_sq <= prim.radius * prim.radius:
                        best = t

    elif isinstance(prim, LoftPrimitive):
        if prim.sections and len(prim.sections) >= 2:
            loft = LoftGeometry(
                component_id="primitive:loft",
                sections=tuple(Section(pts) for pts in prim.sections),
                interpolation=prim.interpolation,
                station_spacing=prim.station_spacing,
                closed_ends=prim.closed_ends,
            )
            loops = tessellated_loops(loft)
            if loops:
                for current, following in pairwise(loops):
                    for index in range(len(current)):
                        next_index = (index + 1) % len(current)
                        tri1 = (current[index], current[next_index], following[index])
                        tri2 = (current[next_index], following[next_index], following[index])
                        for tri in (tri1, tri2):
                            d = _ray_triangle_intersection(origin, direction, tri)
                            if d is not None and (best is None or d < best):
                                best = d
                cap_d = _loft_cap_hit_distance(loft, loops, origin, direction, best)
                if cap_d is not None and (best is None or cap_d < best):
                    best = cap_d

    return best


def hit_test_scene(
    scene_objects: Mapping[str, SceneObject],
    origin: Point3D,
    direction: Point3D,
) -> str | None:
    """The component of the nearest visible scene object the ray hits; objects
    that draw no component are not picked."""
    best_distance: float | None = None
    best_id: str | None = None
    for obj in scene_objects.values():
        if not obj.visible or obj.component_id is None:
            continue
        for prim in obj.primitives:
            distance = _ray_primitive_intersection(origin, direction, prim)
            if distance is not None and (best_distance is None or distance < best_distance):
                best_distance = distance
                best_id = obj.component_id
    return best_id
