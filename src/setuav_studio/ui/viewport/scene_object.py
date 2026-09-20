"""Scene object representing a single entry in the 3D viewport scene graph."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

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


def _cylinder_envelope(prim: CylinderPrimitive) -> dict[str, Any]:
    p1, p2 = prim.start, prim.end
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dz = p2[2] - p1[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    diam = 2.0 * prim.radius
    if length < 1e-6:
        size = {"x": diam, "y": diam, "z": diam}
    else:
        ax = dx / length
        ay = dy / length
        az = dz / length
        sx = length * abs(ax) + diam * math.sqrt(max(0.0, 1.0 - ax * ax))
        sy = length * abs(ay) + diam * math.sqrt(max(0.0, 1.0 - ay * ay))
        sz = length * abs(az) + diam * math.sqrt(max(0.0, 1.0 - az * az))
        size = {"x": round(sx, 3), "y": round(sy, 3), "z": round(sz, 3)}
    return {
        "shape": "cylinder",
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
    layer: str = "default"
    name: str = ""
    visible: bool = True
    primitives: list[VisualPrimitive] = field(default_factory=list)
    envelope: Any = None

    def get_envelope(self) -> dict[str, Any] | Any | None:
        """Return explicit envelope if set, or automatically compute it from visual primitives."""
        if self.envelope is not None:
            if isinstance(self.envelope, dict) and "size_mm" in self.envelope:
                return self.envelope
            if hasattr(self.envelope, "lines"):
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
