"""Geometry Mount Target and Frame calculation engine.

Defines MountTarget and MountFrame data structures, stable target ID extraction,
mount point/orientation calculation, and propeller clearance analysis.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass, field
from typing import Any, Literal

from .transforms import Matrix4, identity_matrix, multiply_matrix, transform_matrix, transform_point

Point3D = tuple[float, float, float]
Vector3D = tuple[float, float, float]


def _resolve_component_world_matrix(
    comp_id: str,
    comp_map: dict[str, dict[str, Any]],
    resolving: frozenset[str] = frozenset(),
) -> Matrix4:
    """Resolve component world transformation matrix traversing parent/attach_to chain."""
    if comp_id in resolving or comp_id not in comp_map:
        return identity_matrix()
    comp = comp_map[comp_id]
    attach_to = comp.get("attach_to") or comp.get("parent")
    parent_mat = (
        _resolve_component_world_matrix(attach_to, comp_map, resolving | {comp_id})
        if isinstance(attach_to, str) and attach_to
        else identity_matrix()
    )
    local_mat = transform_matrix(comp.get("transform"))
    return multiply_matrix(parent_mat, local_mat)


@dataclass(frozen=True, slots=True)
class MountFrame:
    """Position and reference orientation for a mount location (front or rear)."""

    position: Point3D
    normal: Vector3D = (-1.0, 0.0, 0.0)
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": {
                "x": self.position[0],
                "y": self.position[1],
                "z": self.position[2],
            },
            "normal": {
                "x": self.normal[0],
                "y": self.normal[1],
                "z": self.normal[2],
            },
            "orientation": {
                "roll": self.roll,
                "pitch": self.pitch,
                "yaw": self.yaw,
            },
        }


@dataclass(frozen=True, slots=True)
class MountTarget:
    """A geometry target that can host a motor mount (wing or fuselage segment)."""

    id: str
    type: Literal["wing", "fuselage_segment"]
    parent_id: str
    name: str = ""
    frames: dict[str, MountFrame] = field(default_factory=dict)

    def get_frame(self, position: str) -> MountFrame:
        """Get the specified mount frame ('front' or 'rear')."""
        pos = position.lower()
        if pos in self.frames:
            return self.frames[pos]
        if "front" in self.frames:
            return self.frames["front"]
        if self.frames:
            return next(iter(self.frames.values()))
        return MountFrame(position=(0.0, 0.0, 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "parent_id": self.parent_id,
            "name": self.name,
            "frames": {k: v.to_dict() for k, v in self.frames.items()},
        }


def generate_mount_targets(project: Any) -> list[MountTarget]:
    """Scan project components and publish all mountable geometry targets.

    Supports:
    - Lifting surfaces (wing, tail, fin)
    - Fuselage segments (e.g. fuselage/segment-01, fuselage/segment-02)
    """
    targets: list[MountTarget] = []
    items = _extract_components(project)
    if not items:
        return targets

    for comp in items:
        ctype = comp.get("type", "")
        cid = str(comp.get("id", ""))
        cname = str(comp.get("name") or cid)
        params = comp.get("parameters")
        params_dict = params if isinstance(params, dict) else {}
        geom = params_dict.get("geometry")
        geom_dict = geom if isinstance(geom, dict) else {}

        if ctype == "org.setuav.core:lifting-surface":
            target = _build_wing_mount_target(cid, cname, geom_dict)
            if target is not None:
                targets.append(target)

        elif ctype == "org.setuav.core:fuselage":
            fuse_targets = _build_fuselage_mount_targets(cid, cname, geom_dict)
            targets.extend(fuse_targets)

    return targets


def _extract_components(project: Any) -> list[dict[str, Any]]:
    if project is None:
        return []
    data = getattr(project, "data", project)
    if isinstance(data, dict):
        comps = data.get("components")
        if isinstance(comps, list):
            return [c for c in comps if isinstance(c, dict)]
    return []


def _build_wing_mount_target(
    comp_id: str,
    comp_name: str,
    geom: dict[str, Any],
) -> MountTarget | None:
    profiles = geom.get("profiles") or geom.get("sections")
    if not isinstance(profiles, list) or not profiles:
        return None

    # Use root profile (index 0) to establish reference front (LE) and rear (TE) frames
    root = profiles[0] if isinstance(profiles[0], dict) else {}
    root_pos = root.get("position", {}) if isinstance(root.get("position"), dict) else {}
    rx = float(root_pos.get("x", 0.0))
    ry = float(root_pos.get("y", 0.0))
    rz = float(root_pos.get("z", 0.0))
    chord = float(root.get("chord", 100.0))

    front_frame = MountFrame(
        position=(rx, ry, rz),
        normal=(-1.0, 0.0, 0.0),
        roll=0.0,
        pitch=0.0,
        yaw=0.0,
    )
    rear_frame = MountFrame(
        position=(rx + chord, ry, rz),
        normal=(1.0, 0.0, 0.0),
        roll=0.0,
        pitch=0.0,
        yaw=0.0,
    )

    return MountTarget(
        id=comp_id,
        type="wing",
        parent_id=comp_id,
        name=comp_name,
        frames={"front": front_frame, "rear": rear_frame},
    )


def _build_fuselage_mount_targets(
    comp_id: str,
    comp_name: str,
    geom: dict[str, Any],
) -> list[MountTarget]:
    segments = geom.get("segments")
    if not isinstance(segments, list) or not segments:
        return []

    targets: list[MountTarget] = []
    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        sections = seg.get("sections")
        if not isinstance(sections, list) or not sections:
            continue

        target_id = f"{comp_id}/segment-{idx+1:02d}"
        tag = seg.get("tag")
        label = f"{comp_name} Segment {idx+1}" + (f" ({tag})" if tag else "")

        # Front section: minimum x or first section
        first_sec = sections[0] if isinstance(sections[0], dict) else {}
        first_pos = first_sec.get("position", {}) if isinstance(first_sec.get("position"), dict) else {}
        fx = float(first_pos.get("x", 0.0))
        fy = float(first_pos.get("y", 0.0))
        fz = float(first_pos.get("z", 0.0))

        # Rear section: maximum x or last section
        last_sec = sections[-1] if isinstance(sections[-1], dict) else {}
        last_pos = last_sec.get("position", {}) if isinstance(last_sec.get("position"), dict) else {}
        lx = float(last_pos.get("x", 0.0))
        ly = float(last_pos.get("y", 0.0))
        lz = float(last_pos.get("z", 0.0))

        front_frame = MountFrame(
            position=(fx, fy, fz),
            normal=(-1.0, 0.0, 0.0),
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
        )
        rear_frame = MountFrame(
            position=(lx, ly, lz),
            normal=(1.0, 0.0, 0.0),
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
        )

        targets.append(
            MountTarget(
                id=target_id,
                type="fuselage_segment",
                parent_id=comp_id,
                name=label,
                frames={"front": front_frame, "rear": rear_frame},
            )
        )

    return targets


def resolve_mount_point(
    target: MountTarget,
    position: str = "front",
    offset: dict[str, float] | None = None,
    orientation: dict[str, float] | None = None,
) -> tuple[Point3D, tuple[float, float, float]]:
    """Compute local 3D mount point and orientation from a target, position, offset, and orientation."""
    frame = target.get_frame(position)
    off = offset or {}
    ori = orientation or {}

    mx = frame.position[0] + float(off.get("x", 0.0))
    my = frame.position[1] + float(off.get("y", 0.0))
    mz = frame.position[2] + float(off.get("z", 0.0))

    r = frame.roll + float(ori.get("roll", 0.0))
    p = frame.pitch + float(ori.get("pitch", 0.0))
    y = frame.yaw + float(ori.get("yaw", 0.0))

    return (mx, my, mz), (r, p, y)


def _check_wing_edge_margin(
    root: dict[str, Any],
    pos_lower: str,
    mount_pt: Point3D,
    prop_radius: float,
) -> tuple[float, bool, list[str]]:
    root_chord = float(root.get("chord", 100.0))
    root_pos = root.get("position", {}) if isinstance(root.get("position"), dict) else {}
    le_x = float(root_pos.get("x", 0.0))
    te_x = le_x + root_chord
    vertical_dist = abs(mount_pt[2] - float(root_pos.get("z", 0.0)))
    wing_thickness = root_chord * 0.15

    prop_standoff = 20.0
    if pos_lower == "front":
        prop_x = mount_pt[0] - prop_standoff
        dx = le_x - prop_x
        label = "leading"
    else:
        prop_x = mount_pt[0] + prop_standoff
        dx = prop_x - te_x
        label = "trailing"

    if dx < 0:
        margin = vertical_dist - (prop_radius + wing_thickness * 0.5)
        if margin < 0:
            return margin, True, [f"Propeller intersects wing {label} edge by {-margin:.1f} mm."]
        return max(margin, 5.0), False, []

    return max(dx, 5.0), False, []


def _extract_fuselage_sections(
    fuselage: dict[str, Any], fuse_world_mat: Matrix4
) -> list[tuple[float, float, float, float]]:
    f_params = fuselage.get("parameters", {})
    f_geom = f_params.get("geometry", {})
    f_segs = f_geom.get("segments", [])

    sections_info: list[tuple[float, float, float, float]] = []
    for seg in f_segs:
        if not isinstance(seg, dict):
            continue
        for sec in seg.get("sections", []):
            if not isinstance(sec, dict):
                continue
            pos = sec.get("position", {}) if isinstance(sec.get("position"), dict) else {}
            prof = sec.get("profile", {}) if isinstance(sec.get("profile"), dict) else {}
            sec_local_pt = (
                float(pos.get("x", 0.0)),
                float(pos.get("y", 0.0)),
                float(pos.get("z", 0.0)),
            )
            sec_world_pt = transform_point(fuse_world_mat, sec_local_pt)
            w = float(prof.get("width") or prof.get("diameter") or 80.0) * 0.5
            h = float(prof.get("height") or prof.get("diameter") or 80.0) * 0.5
            sections_info.append((sec_world_pt[0], w, sec_world_pt[2], h))
    return sections_info


def _check_fuselage_proximity(
    world_mount_pt: Point3D,
    prop_radius: float,
    items: list[dict[str, Any]],
    comp_map: dict[str, dict[str, Any]] | None = None,
) -> tuple[float, bool, list[str]]:
    fuselage = next((c for c in items if c.get("type") == "org.setuav.core:fuselage"), None)
    if not fuselage:
        return 999.0, False, []

    fuse_id = str(fuselage.get("id") or "")
    fuse_world_mat = (
        _resolve_component_world_matrix(fuse_id, comp_map)
        if comp_map and fuse_id
        else identity_matrix()
    )

    sections_info = _extract_fuselage_sections(fuselage, fuse_world_mat)
    if not sections_info:
        return 999.0, False, []

    wx, wy, wz = world_mount_pt
    min_fuse_x = min(s[0] for s in sections_info)
    max_fuse_x = max(s[0] for s in sections_info)

    if wx < min_fuse_x - 30.0:
        return min_fuse_x - wx, False, []
    if wx > max_fuse_x + 30.0:
        return wx - max_fuse_x, False, []

    nearby = [s for s in sections_info if abs(s[0] - wx) <= max(prop_radius * 0.5, 60.0)]
    if not nearby:
        nearby = [min(sections_info, key=lambda s: abs(s[0] - wx))]

    wy_abs = abs(wy)
    min_margin = min(
        max(wy_abs - (semi_w + prop_radius), abs(wz - center_z) - (semi_h + prop_radius))
        for _sec_x, semi_w, center_z, semi_h in nearby
    )

    if min_margin < 0:
        return min_margin, True, [f"Propeller collides with fuselage by {-min_margin:.1f} mm."]
    return min_margin, False, []


def _check_wing_clearance(
    geom: dict[str, Any],
    pos_lower: str,
    mount_pt: Point3D,
    world_mount_pt: Point3D,
    prop_radius: float,
    items: list[dict[str, Any]],
    comp_map: dict[str, dict[str, Any]],
) -> tuple[float, bool, list[str]]:
    profiles = geom.get("profiles") or geom.get("sections") or []
    root = profiles[0] if profiles and isinstance(profiles[0], dict) else {}

    clearance_mm, has_coll, msgs = _check_wing_edge_margin(root, pos_lower, mount_pt, prop_radius)
    fuse_margin, fuse_coll, fuse_msgs = _check_fuselage_proximity(world_mount_pt, prop_radius, items, comp_map)

    if fuse_coll:
        has_coll = True
        msgs.extend(fuse_msgs)
    clearance_mm = min(clearance_mm, fuse_margin)

    return clearance_mm, has_coll, msgs


def _check_fuselage_clearance(
    geom: dict[str, Any],
    target_id: str,
    pos_lower: str,
    prop_radius: float,
) -> float:
    segments = geom.get("segments", [])
    seg_idx = 0
    with contextlib.suppress(Exception):
        seg_idx = int(target_id.split("-")[-1]) - 1

    if 0 <= seg_idx < len(segments):
        seg = segments[seg_idx]
        secs = seg.get("sections", [])
        sec = secs[0] if pos_lower == "front" and secs else (secs[-1] if secs else {})
        prof = sec.get("profile", {}) if isinstance(sec, dict) else {}
        sec_radius = float(prof.get("width") or prof.get("diameter") or 50.0) * 0.5
        return max(prop_radius - sec_radius, 15.0)
    return 50.0


def compute_propeller_clearance(
    project: Any,
    target_id: str,
    position: str,
    offset: dict[str, float],
    orientation: dict[str, float],
    propeller_diameter: float,
) -> dict[str, Any]:
    """Check propeller clearance against mount surfaces and fuselage/wing geometry."""
    targets = generate_mount_targets(project)
    target = next((t for t in targets if t.id == target_id), None)
    if target is None:
        return {
            "valid": False,
            "clearance_mm": 0.0,
            "has_collision": True,
            "mount_point": (0.0, 0.0, 0.0),
            "orientation": (0.0, 0.0, 0.0),
            "target_id": target_id,
            "message": f"Mount target '{target_id}' not found in project.",
        }

    mount_pt, mount_ori = resolve_mount_point(target, position, offset, orientation)
    prop_radius = max(propeller_diameter * 0.5, 0.0)
    items = _extract_components(project)
    comp_map = {str(c.get("id")): c for c in items if isinstance(c, dict)}
    parent_comp = comp_map.get(target.parent_id)
    params = parent_comp.get("parameters", {}) if parent_comp else {}
    geom = params.get("geometry", {}) if isinstance(params, dict) else {}

    world_mat = _resolve_component_world_matrix(target.parent_id, comp_map)
    world_mount_pt = transform_point(world_mat, mount_pt)

    pos_lower = position.lower()
    clearance_mm = 50.0
    has_collision = False
    warning_msgs: list[str] = []

    if target.type == "wing":
        clearance_mm, has_collision, warning_msgs = _check_wing_clearance(
            geom, pos_lower, mount_pt, world_mount_pt, prop_radius, items, comp_map
        )
    elif target.type == "fuselage_segment":
        clearance_mm = _check_fuselage_clearance(geom, target_id, pos_lower, prop_radius)

    msg = (
        "; ".join(warning_msgs)
        if has_collision
        else f"Clearance OK: {clearance_mm:.1f} mm margin"
    )

    return {
        "valid": True,
        "clearance_mm": round(clearance_mm, 2),
        "has_collision": has_collision,
        "mount_point": mount_pt,
        "orientation": mount_ori,
        "target_id": target_id,
        "message": msg,
    }


def generate_clearance_circle_points(
    mount_point: Point3D,
    orientation: tuple[float, float, float],
    diameter: float,
    num_points: int = 36,
    normal: Point3D | None = None,
) -> tuple[Point3D, ...]:
    """Generate 3D points for the propeller clearance circle wireframe."""
    radius = max(diameter * 0.5, 1.0)
    if normal is not None:
        mag = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2)
        n = (1.0, 0.0, 0.0) if mag < 1e-6 else (normal[0] / mag, normal[1] / mag, normal[2] / mag)
        ref = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (0.0, 1.0, 0.0)
        u = (
            n[1] * ref[2] - n[2] * ref[1],
            n[2] * ref[0] - n[0] * ref[2],
            n[0] * ref[1] - n[1] * ref[0],
        )
        u_mag = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2) or 1.0
        u = (u[0] / u_mag, u[1] / u_mag, u[2] / u_mag)
        v = (
            n[1] * u[2] - n[2] * u[1],
            n[2] * u[0] - n[0] * u[2],
            n[0] * u[1] - n[1] * u[0],
        )
    else:
        roll, pitch, yaw = orientation
        cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))
        cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
        cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))

        # Base normal is along X axis: (1, 0, 0)
        # Perpendicular unit vectors in disk plane:
        # u vector along Y axis, v vector along Z axis rotated by roll, pitch, yaw
        # Rotation matrix columns:
        # Col 1 (Y): (cy*sp*sr - sy*cr, sy*sp*sr + cy*cr, cp*sr)
        # Col 2 (Z): (cy*sp*cr + sy*sr, sy*sp*cr - cy*sr, cp*cr)
        u = (cy * sp * sr - sy * cr, sy * sp * sr + cy * cr, cp * sr)
        v = (cy * sp * cr + sy * sr, sy * sp * cr - cy * sr, cp * cr)

    points: list[Point3D] = []
    mx, my, mz = mount_point
    for i in range(num_points):
        theta = 2.0 * math.pi * i / num_points
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        px = mx + radius * (cos_t * u[0] + sin_t * v[0])
        py = my + radius * (cos_t * u[1] + sin_t * v[1])
        pz = mz + radius * (cos_t * u[2] + sin_t * v[2])
        points.append((px, py, pz))

    return tuple(points)
