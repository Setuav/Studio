"""Envelope bounding wireframe vertex generation for components and scene objects."""

from __future__ import annotations

import math
from typing import Any

from setuav_studio_sdk.primitives import CylinderPrimitive, Point3D

from .loft_mesh import _add_line, _append_ring
from .raycast import _box_corners, _ortho_basis
from .types import GeometryData

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
    obj: Any,
    color: Point3D,
) -> None:
    env = obj.get_envelope() if hasattr(obj, "get_envelope") else getattr(obj, "envelope", None)
    if env is None:
        return

    # 1. EnvelopeWireGeometry (or any object with .lines)
    if hasattr(env, "lines"):
        for start, end in env.lines:
            _add_line(vertices, start, end, color)
        return

    # 2. Dictionary with envelope definition
    if isinstance(env, dict) and "size_mm" in env:
        shape = str(env.get("shape", "box")).lower()
        raw_size = env.get("size_mm", {})
        raw_offset = env.get("offset_mm", {})
        sx = float(raw_size.get("x", 0.0)) if isinstance(raw_size, dict) else float(raw_size[0])
        sy = float(raw_size.get("y", 0.0)) if isinstance(raw_size, dict) else float(raw_size[1])
        sz = float(raw_size.get("z", 0.0)) if isinstance(raw_size, dict) else float(raw_size[2])
        ox = (
            float(raw_offset.get("x", 0.0))
            if isinstance(raw_offset, dict)
            else (float(raw_offset[0]) if raw_offset else 0.0)
        )
        oy = (
            float(raw_offset.get("y", 0.0))
            if isinstance(raw_offset, dict)
            else (float(raw_offset[1]) if raw_offset else 0.0)
        )
        oz = (
            float(raw_offset.get("z", 0.0))
            if isinstance(raw_offset, dict)
            else (float(raw_offset[2]) if raw_offset else 0.0)
        )

        primitives = getattr(obj, "primitives", ())
        prim0 = primitives[0] if primitives else None
        base_center: Point3D = (0.0, 0.0, 0.0)
        rotation: Point3D = (0.0, 0.0, 0.0)
        if prim0 is not None:
            if isinstance(prim0, CylinderPrimitive):
                base_center = (
                    (prim0.start[0] + prim0.end[0]) * 0.5,
                    (prim0.start[1] + prim0.end[1]) * 0.5,
                    (prim0.start[2] + prim0.end[2]) * 0.5,
                )
            else:
                base_center = getattr(prim0, "center", (0.0, 0.0, 0.0))
            rotation = getattr(prim0, "rotation", (0.0, 0.0, 0.0))

        center = (base_center[0] + ox, base_center[1] + oy, base_center[2] + oz)
        if shape == "cylinder":
            _append_cylinder_wire(vertices, center, max(sx, sy) * 0.5, sz, color)
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
    data: GeometryData | None,
    selected_envelope_component_id: str | None,
    color: Point3D = ENVELOPE_HIGHLIGHT,
    selected_component_id: str | None = None,
    scene_objects: dict[str, Any] | None = None,
) -> list[float]:
    """Build vertices for the green wireframe envelope highlighting the selected component's bounding volume."""
    target_clean = (
        selected_envelope_component_id.lower().replace(":envelope", "")
        if selected_envelope_component_id
        else ""
    )
    comp_clean = (
        selected_component_id.lower().replace(":envelope", "") if selected_component_id else ""
    )
    vertices: list[float] = []
    if data is not None:
        for env in getattr(data, "envelopes", ()):
            env_clean = env.component_id.lower().replace(":envelope", "")
            is_prop_clearance = (
                ":propeller_clearance" in env_clean
                or ":clearance" in env_clean
                or "motor" in env_clean
            )

            is_selected = False
            if target_clean:
                is_selected = env_clean == target_clean or env_clean.startswith(f"{target_clean}:")
            if not is_selected and comp_clean and is_prop_clearance:
                is_selected = env_clean == comp_clean or env_clean.startswith(f"{comp_clean}:")

            if is_prop_clearance:
                line_color = (1.0, 1.0, 1.0)
            elif is_selected:
                line_color = color
            else:
                continue

            for start, end in env.lines:
                _add_line(vertices, start, end, line_color)

    if scene_objects and target_clean:
        for obj_id, obj in scene_objects.items():
            clean_id = obj_id.lower().replace(":envelope", "")
            if (
                clean_id == target_clean
                or clean_id.startswith(f"{target_clean}:")
                or target_clean.startswith(f"{clean_id}:")
            ):
                _append_scene_object_envelope_wire(vertices, obj, color)

    return vertices
