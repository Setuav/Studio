"""Envelope bounding wireframe vertex generation for components and scene objects."""

from __future__ import annotations

import math
from collections.abc import Sequence

from setuav_studio.utilities.transform import rotate_vector

from .loft_mesh import _add_line, _append_ring
from .primitives import BoxPrimitive, CylinderPrimitive, PlanePrimitive, Point3D, RingPrimitive
from .raycast import _box_corners, _ortho_basis
from .scene_object import SceneObject
from .types import EnvelopeWireGeometry

ENVELOPE_HIGHLIGHT: Point3D = (0.15, 1.0, 0.25)


def _append_cylinder_wire(
    vertices: list[float],
    center: Point3D,
    radius: float,
    length: float,
    color: Point3D,
    axis: Point3D = (0.0, 0.0, 1.0),
    segments: int = 24,
) -> None:
    u, v = _ortho_basis(axis)
    half = length * 0.5
    cx, cy, cz = center
    p1 = (cx - half * axis[0], cy - half * axis[1], cz - half * axis[2])
    p2 = (cx + half * axis[0], cy + half * axis[1], cz + half * axis[2])
    ring1: list[Point3D] = []
    ring2: list[Point3D] = []
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        offset = (
            radius * (cos_a * u[0] + sin_a * v[0]),
            radius * (cos_a * u[1] + sin_a * v[1]),
            radius * (cos_a * u[2] + sin_a * v[2]),
        )
        ring1.append((p1[0] + offset[0], p1[1] + offset[1], p1[2] + offset[2]))
        ring2.append((p2[0] + offset[0], p2[1] + offset[1], p2[2] + offset[2]))
    _append_ring(vertices, ring1, color)
    _append_ring(vertices, ring2, color)
    for idx in (0, segments // 4, segments // 2, (3 * segments) // 4):
        _add_line(vertices, ring1[idx], ring2[idx], color)


def _append_scene_object_envelope_wire(
    vertices: list[float],
    obj: SceneObject,
    color: Point3D,
) -> None:
    env = obj.get_envelope()
    if env is None:
        return

    if isinstance(env, EnvelopeWireGeometry):
        for start, end in env.lines:
            _add_line(vertices, start, end, color)
        return

    shape = str(env["shape"]).lower()
    size = env["size_mm"]
    offset = env["offset_mm"]
    sx, sy, sz = float(size["x"]), float(size["y"]), float(size["z"])
    ox, oy, oz = float(offset["x"]), float(offset["y"]), float(offset["z"])

    prim0 = obj.primitives[0] if obj.primitives else None
    base_center: Point3D = (0.0, 0.0, 0.0)
    rotation: Point3D = (0.0, 0.0, 0.0)
    if isinstance(prim0, CylinderPrimitive):
        base_center = (
            (prim0.start[0] + prim0.end[0]) * 0.5,
            (prim0.start[1] + prim0.end[1]) * 0.5,
            (prim0.start[2] + prim0.end[2]) * 0.5,
        )
    elif isinstance(prim0, (BoxPrimitive, PlanePrimitive, RingPrimitive)):
        base_center = prim0.center
    if isinstance(prim0, BoxPrimitive):
        rotation = prim0.rotation

    center = (base_center[0] + ox, base_center[1] + oy, base_center[2] + oz)
    if shape == "cylinder":
        cyl_axis: Point3D
        cyl_len: float
        cyl_radius: float
        if isinstance(prim0, CylinderPrimitive):
            dx = prim0.end[0] - prim0.start[0]
            dy = prim0.end[1] - prim0.start[1]
            dz = prim0.end[2] - prim0.start[2]
            axis_len = math.sqrt(dx * dx + dy * dy + dz * dz)
            if axis_len > 1e-6:
                cyl_axis = (dx / axis_len, dy / axis_len, dz / axis_len)
                cyl_len = axis_len
            else:
                cyl_axis = (0.0, 0.0, 1.0)
                cyl_len = max(sz, 10.0)
            cyl_radius = prim0.radius
        elif isinstance(prim0, (PlanePrimitive, RingPrimitive)):
            norm = prim0.normal
            norm_len = math.sqrt(norm[0] ** 2 + norm[1] ** 2 + norm[2] ** 2)
            cyl_axis = (
                (norm[0] / norm_len, norm[1] / norm_len, norm[2] / norm_len)
                if norm_len > 1e-6
                else (0.0, 0.0, 1.0)
            )
            cyl_len = max(sz, 10.0)
            cyl_radius = max(sx, sy, sz) * 0.5
        else:
            axis_index = "xyz".index(str(env["axis"]))
            sizes = (sx, sy, sz)
            base_axis: Point3D = (
                float(axis_index == 0),
                float(axis_index == 1),
                float(axis_index == 2),
            )
            cyl_len = sizes[axis_index]
            cyl_radius = max(v for i, v in enumerate(sizes) if i != axis_index) * 0.5
            cyl_axis = (
                rotate_vector(base_axis, rotation) if rotation != (0.0, 0.0, 0.0) else base_axis
            )
        _append_cylinder_wire(vertices, center, cyl_radius, cyl_len, color, axis=cyl_axis)
    else:
        c = _box_corners(center, (sx, sy, sz), rotation)
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


def build_envelope_wire_vertices(
    scene_objects: dict[str, SceneObject],
    selected_envelope_component_id: str | Sequence[str] | None,
    color: Point3D = ENVELOPE_HIGHLIGHT,
) -> list[float]:
    """Build vertices for the green wireframe envelope highlighting the selected component's bounding volume."""
    if isinstance(selected_envelope_component_id, str):
        targets = {selected_envelope_component_id} if selected_envelope_component_id else set()
    else:
        targets = {str(x) for x in selected_envelope_component_id or () if x}

    def belongs(element_id: str, target: str) -> bool:
        return element_id == target or element_id.startswith(f"{target}:")

    vertices: list[float] = []
    for obj_id, obj in scene_objects.items():
        if any(belongs(obj_id, target) or belongs(target, obj_id) for target in targets):
            _append_scene_object_envelope_wire(vertices, obj, color)
    return vertices
