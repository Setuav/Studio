"""Scene object representing a single entry in the 3D viewport scene graph."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .layer import DEFAULT_LAYER
from .primitives import (
    BoxPrimitive,
    CylinderPrimitive,
    LineSegmentsPrimitive,
    LoftPrimitive,
    PlanePrimitive,
    RingPrimitive,
    TrianglesPrimitive,
    VisualPrimitive,
)
from .types import EnvelopeWireGeometry


def _cylinder_envelope(prim: CylinderPrimitive) -> dict[str, Any]:
    p1, p2 = prim.start, prim.end
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dz = p2[2] - p1[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    diam = 2.0 * prim.radius
    if length < 1e-6:
        size = {"x": diam, "y": diam, "z": diam}
        axis = "x"
    else:
        ax = dx / length
        ay = dy / length
        az = dz / length
        sx = length * abs(ax) + diam * math.sqrt(max(0.0, 1.0 - ax * ax))
        sy = length * abs(ay) + diam * math.sqrt(max(0.0, 1.0 - ay * ay))
        sz = length * abs(az) + diam * math.sqrt(max(0.0, 1.0 - az * az))
        size = {"x": round(sx, 3), "y": round(sy, 3), "z": round(sz, 3)}
        # The envelope is axis-aligned; it follows the dominant axis direction.
        axis = max(zip((abs(ax), abs(ay), abs(az)), "xyz", strict=True))[1]
    return {
        "shape": "cylinder",
        "axis": axis,
        "size_mm": size,
        "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
    }


def _loft_envelope(prim: LoftPrimitive) -> dict[str, Any] | None:
    pts = [p for sec in prim.sections for p in sec]
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    size_x = max_x - min_x
    size_y = max_y - min_y
    size_z = max_z - min_z

    sections_data: list[dict[str, Any]] = []
    for sec in prim.sections:
        if sec:
            s_xs = [p[0] for p in sec]
            s_ys = [p[1] for p in sec]
            s_zs = [p[2] for p in sec]
            sections_data.append(
                {
                    "station_x_mm": (min(s_ys) + max(s_ys)) * 0.5,
                    "width_mm": max(s_xs) - min(s_xs),
                    "height_mm": max(s_zs) - min(s_zs),
                    "position": {"z": (min(s_zs) + max(s_zs)) * 0.5},
                    "shape": "airfoil",
                }
            )

    return {
        "shape": "box",
        "size_mm": {"x": float(size_x), "y": float(size_y), "z": float(size_z)},
        "offset_mm": {
            "x": float((min_x + max_x) * 0.5),
            "y": float((min_y + max_y) * 0.5),
            "z": float((min_z + max_z) * 0.5),
        },
        "sections": sections_data,
    }


@dataclass
class SceneObject:
    """A named, layered collection of visual primitives in the viewport.

    Each object has a unique ``object_id``, belongs to a ``layer``, carries an
    optional human-readable ``name``, and holds one or more SDK visual
    primitives that the renderer will draw.
    """

    object_id: str
    layer: str = DEFAULT_LAYER
    name: str = ""
    visible: bool = True
    primitives: list[VisualPrimitive] = field(default_factory=list)
    # The component's envelope: wire lines in world coordinates, or an envelope
    # definition (shape, size_mm, offset_mm). Without one it follows the primitives.
    envelope: EnvelopeWireGeometry | dict[str, Any] | None = None

    def get_envelope(self) -> EnvelopeWireGeometry | dict[str, Any] | None:
        """Return the explicit envelope, or the one computed from the visual primitives."""
        if self.envelope is not None:
            return self.envelope
        return self.compute_envelope()

    def compute_envelope(self) -> dict[str, Any] | None:
        """Calculate tight local bounding envelope from the object's visual primitives."""
        if not self.primitives:
            return None

        prim = self.primitives[0]

        if isinstance(prim, BoxPrimitive):
            sx, sy, sz = prim.size
            return {
                "shape": "box",
                "size_mm": {"x": float(sx), "y": float(sy), "z": float(sz)},
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }

        if isinstance(prim, CylinderPrimitive):
            return _cylinder_envelope(prim)

        if isinstance(prim, LoftPrimitive):
            return _loft_envelope(prim)

        if isinstance(prim, PlanePrimitive):
            from .raycast import _ortho_basis

            nx, ny, nz = prim.normal
            norm_len = math.sqrt(nx * nx + ny * ny + nz * nz)
            if norm_len > 1e-6:
                norm = (nx / norm_len, ny / norm_len, nz / norm_len)
            else:
                norm = (0.0, 0.0, 1.0)
            u, v = _ortho_basis(norm)
            thick = 5.0
            w, h = float(prim.width), float(prim.height)
            sx = w * abs(u[0]) + h * abs(v[0]) + thick * abs(norm[0])
            sy = w * abs(u[1]) + h * abs(v[1]) + thick * abs(norm[1])
            sz = w * abs(u[2]) + h * abs(v[2]) + thick * abs(norm[2])
            return {
                "shape": "box",
                "size_mm": {"x": round(sx, 3), "y": round(sy, 3), "z": round(sz, 3)},
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }

        if isinstance(prim, RingPrimitive):
            diam = 2.0 * prim.radius
            nx, ny, nz = prim.normal
            norm_len = math.sqrt(nx * nx + ny * ny + nz * nz)
            if norm_len > 1e-6:
                norm_x, norm_y, norm_z = nx / norm_len, ny / norm_len, nz / norm_len
            else:
                norm_x, norm_y, norm_z = 0.0, 0.0, 1.0
            thick = 10.0
            sx = diam * math.sqrt(max(0.0, 1.0 - norm_x * norm_x)) + thick * abs(norm_x)
            sy = diam * math.sqrt(max(0.0, 1.0 - norm_y * norm_y)) + thick * abs(norm_y)
            sz = diam * math.sqrt(max(0.0, 1.0 - norm_z * norm_z)) + thick * abs(norm_z)
            return {
                "shape": "box",
                "size_mm": {"x": round(sx, 3), "y": round(sy, 3), "z": round(sz, 3)},
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }

        all_pts: list[tuple[float, float, float]] = []
        if isinstance(prim, LineSegmentsPrimitive):
            for p1, p2 in prim.lines:
                all_pts.extend((p1, p2))
        elif isinstance(prim, TrianglesPrimitive):
            for tri in prim.triangles:
                all_pts.extend(tri)

        if all_pts:
            xs = [p[0] for p in all_pts]
            ys = [p[1] for p in all_pts]
            zs = [p[2] for p in all_pts]
            return {
                "shape": "box",
                "size_mm": {
                    "x": max(10.0, max(xs) - min(xs)),
                    "y": max(10.0, max(ys) - min(ys)),
                    "z": max(10.0, max(zs) - min(zs)),
                },
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }

        return None


def is_scene_object_matching(object_id: str, target_id: str | None) -> bool:
    """Determine whether a SceneObject's object_id matches an active selected/hovered component ID.

    Hierarchy & matching rules:
    1. Exact or case-insensitive match: object_id == target_id.
    2. Mirrored counterparts: "wing:mirror" matches "wing".
    3. Attached tip caps belong to the parent lifting surface:
       "wing:tip-cap" and "wing:mirror:tip-cap" match target "wing".
       Tip caps never match if target_id is a child control surface.
    4. Control surfaces are dedicated child components:
       "wing:aileron-1" and "wing:mirror:aileron-1" match target "aileron-1".
       When target_id is "wing" (parent surface), child control surfaces are
       EXCLUDED from the wing body selection so they remain distinct.
    5. Procedural components (fuselage root-stubs):
       "fuselage:stub:..." matches target "fuselage".
    """
    if target_id is None:
        return False
    if object_id == target_id:
        return True

    obj_lower = object_id.lower()
    tgt_lower = target_id.lower()
    if obj_lower == tgt_lower:
        return True

    parts = [p.strip() for p in obj_lower.split(":") if p.strip()]
    if not parts:
        return False

    base_id = parts[0]
    subparts = [p for p in parts[1:] if p not in ("mirror", "stations")]

    tgt_clean = tgt_lower.replace(":mirror", "").strip()

    # Rule A: Check if the target is selecting a control surface subpart
    # (e.g. "aileron-1", "wing:aileron-1", "wing_aileron-1")
    for sub in subparts:
        if sub in ("tip-cap", "stub", "root-stub", "winglet"):
            continue
        if (
            tgt_clean == sub
            or tgt_lower == sub
            or tgt_clean in (f"{base_id}:{sub}", f"{base_id}-{sub}", f"{base_id}_{sub}")
            or tgt_clean.endswith(f":{sub}")
            or tgt_clean.endswith(f"-{sub}")
            or tgt_clean.endswith(f"_{sub}")
        ):
            return True

    # If this scene object is a child control surface (and not a procedural
    # subpart like a tip-cap or root-stub) but target did not match it,
    # do NOT fall back to matching the base component (wing).
    is_procedural = any(sub in ("tip-cap", "stub", "root-stub", "winglet") for sub in subparts)
    if not is_procedural and len(subparts) > 0:
        return False

    # Rule B: Target matches the base component (wing, fuselage, etc.)
    return base_id in (tgt_clean, tgt_lower)
