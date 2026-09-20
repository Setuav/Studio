"""Spatial transform calculations and reparenting utilities for Setuav Studio components."""

from __future__ import annotations

import math
from typing import Any, cast

Point3D = tuple[float, float, float]
Rotation3D = tuple[float, float, float]
Matrix3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


def euler_to_matrix(roll_deg: float, pitch_deg: float, yaw_deg: float) -> Matrix3:
    """Compute 3x3 rotation matrix from Euler angles (roll, pitch, yaw) in degrees.

    Uses the standard aircraft Z-Y-X (yaw-pitch-roll) convention:
    R = R_z(yaw) * R_y(pitch) * R_x(roll)
    """
    r = math.radians(roll_deg)
    p = math.radians(pitch_deg)
    y = math.radians(yaw_deg)
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    return (
        (cp * cy, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (cp * sy, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def matrix_to_euler(matrix: Matrix3) -> Rotation3D:
    """Extract Euler angles (roll, pitch, yaw) in degrees from a 3x3 rotation matrix.

    Handles gimbal locks (pitch near +/-90 degrees) cleanly.
    """
    sp = -matrix[2][0]
    sp = max(-1.0, min(1.0, sp))
    pitch = math.asin(sp)
    cp = math.cos(pitch)
    if abs(cp) > 1e-6:
        roll = math.atan2(matrix[2][1], matrix[2][2])
        yaw = math.atan2(matrix[1][0], matrix[0][0])
    else:
        roll = 0.0
        if sp > 0:  # pitch = +90 deg
            yaw = math.atan2(-matrix[0][1], matrix[0][2])
        else:  # pitch = -90 deg
            yaw = math.atan2(-matrix[0][1], matrix[1][1])
    return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))


def rotate_vector(vec: Point3D, rot: Rotation3D | Matrix3) -> Point3D:
    """Rotate a 3D vector by Euler angles (roll, pitch, yaw) or a 3x3 rotation matrix."""
    if isinstance(rot[0], tuple):
        mat = cast(Matrix3, rot)
    else:
        r_rot = cast(Rotation3D, rot)
        mat = euler_to_matrix(r_rot[0], r_rot[1], r_rot[2])
    x, y_val, z = vec
    return (
        mat[0][0] * x + mat[0][1] * y_val + mat[0][2] * z,
        mat[1][0] * x + mat[1][1] * y_val + mat[1][2] * z,
        mat[2][0] * x + mat[2][1] * y_val + mat[2][2] * z,
    )


def inverse_rotate_vector(vec: Point3D, rot: Rotation3D | Matrix3) -> Point3D:
    """Rotate a 3D vector by the inverse (transpose) of Euler angles or rotation matrix."""
    if isinstance(rot[0], tuple):
        mat = cast(Matrix3, rot)
    else:
        r_rot = cast(Rotation3D, rot)
        mat = euler_to_matrix(r_rot[0], r_rot[1], r_rot[2])
    x, y_val, z = vec
    return (
        mat[0][0] * x + mat[1][0] * y_val + mat[2][0] * z,
        mat[0][1] * x + mat[1][1] * y_val + mat[2][1] * z,
        mat[0][2] * x + mat[1][2] * y_val + mat[2][2] * z,
    )


def multiply_rotations(left: Matrix3, right: Matrix3) -> Matrix3:
    """Multiply two 3x3 rotation matrices."""
    return (
        (
            sum(left[0][k] * right[k][0] for k in range(3)),
            sum(left[0][k] * right[k][1] for k in range(3)),
            sum(left[0][k] * right[k][2] for k in range(3)),
        ),
        (
            sum(left[1][k] * right[k][0] for k in range(3)),
            sum(left[1][k] * right[k][1] for k in range(3)),
            sum(left[1][k] * right[k][2] for k in range(3)),
        ),
        (
            sum(left[2][k] * right[k][0] for k in range(3)),
            sum(left[2][k] * right[k][1] for k in range(3)),
            sum(left[2][k] * right[k][2] for k in range(3)),
        ),
    )


def transpose_matrix(matrix: Matrix3) -> Matrix3:
    """Transpose a 3x3 matrix (which is its inverse for rotation matrices)."""
    return (
        (matrix[0][0], matrix[1][0], matrix[2][0]),
        (matrix[0][1], matrix[1][1], matrix[2][1]),
        (matrix[0][2], matrix[1][2], matrix[2][2]),
    )


def _get_comp_dict(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        return item
    raw = getattr(item, "raw_data", None)
    if isinstance(raw, dict):
        return raw
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        res = to_dict()
        if isinstance(res, dict):
            return res
    return None


def _build_comps_map(comps_or_project: Any) -> dict[str, dict[str, Any]]:
    if isinstance(comps_or_project, dict):
        if "components" in comps_or_project and isinstance(comps_or_project["components"], list):
            comps = comps_or_project["components"]
        else:
            return {
                str(k): d
                for k, v in comps_or_project.items()
                for d in [_get_comp_dict(v)]
                if d is not None
            }
    elif hasattr(comps_or_project, "data") and isinstance(comps_or_project.data, dict):
        comps = comps_or_project.data.get("components", [])
    elif isinstance(comps_or_project, (list, tuple, set)):
        comps = comps_or_project
    else:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for c in comps:
        d = _get_comp_dict(c)
        if d is not None and d.get("id"):
            result[str(d["id"])] = d
    return result


def get_local_transform(comp: dict[str, Any]) -> tuple[Point3D, Rotation3D]:
    """Extract local (position, rotation) from a component dictionary."""
    tf = comp.get("transform")
    tf_dict = tf if isinstance(tf, dict) else {}
    pos = tf_dict.get("position")
    pos_dict = pos if isinstance(pos, dict) else {}
    rot = tf_dict.get("rotation")
    rot_dict = rot if isinstance(rot, dict) else {}

    lx = float(pos_dict.get("x", comp.get("x", 0.0)) or 0.0)
    ly = float(pos_dict.get("y", comp.get("y", 0.0)) or 0.0)
    lz = float(pos_dict.get("z", comp.get("z", 0.0)) or 0.0)

    l_roll = float(rot_dict.get("roll", rot_dict.get("x", comp.get("roll", 0.0))) or 0.0)
    l_pitch = float(rot_dict.get("pitch", rot_dict.get("y", comp.get("pitch", 0.0))) or 0.0)
    l_yaw = float(rot_dict.get("yaw", rot_dict.get("z", comp.get("yaw", 0.0))) or 0.0)

    return (lx, ly, lz), (l_roll, l_pitch, l_yaw)


def resolve_world_transform(
    comp_or_id: str | dict[str, Any] | Any,
    comps_or_project: Any,
    resolving: frozenset[str] = frozenset(),
) -> tuple[Point3D, Rotation3D]:
    """Compute (world_position, world_rotation) by traversing the attachment parent chain."""
    comps_map = _build_comps_map(comps_or_project)

    if isinstance(comp_or_id, str):
        comp_id = comp_or_id
        comp = comps_map.get(comp_id)
    else:
        comp = _get_comp_dict(comp_or_id)
        comp_id = str(comp.get("id") or "") if comp else ""

    if comp is None or not comp_id or comp_id in resolving:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    local_pos, local_rot = get_local_transform(comp)
    parent_id = comp.get("attach_to") or comp.get("parent")
    if not parent_id or str(parent_id) not in comps_map:
        return local_pos, local_rot

    p_pos, p_rot = resolve_world_transform(str(parent_id), comps_map, resolving | {comp_id})

    # R_parent * local_pos + p_pos
    rx, ry, rz = rotate_vector(local_pos, p_rot)
    world_pos = (p_pos[0] + rx, p_pos[1] + ry, p_pos[2] + rz)

    # R_world = R_parent * R_local
    R_p = euler_to_matrix(*p_rot)
    R_l = euler_to_matrix(*local_rot)
    R_world = multiply_rotations(R_p, R_l)
    world_rot = matrix_to_euler(R_world)

    return world_pos, world_rot


def compute_reparented_transform(
    child: dict[str, Any] | Any,
    new_parent_id: str | None,
    comps_or_project: Any,
) -> tuple[Point3D, Rotation3D]:
    """Calculate the new local position and rotation for a child attached to new_parent_id
    such that its absolute world position and orientation remain identical.
    """
    comps_map = _build_comps_map(comps_or_project)
    child_dict = _get_comp_dict(child)
    if child_dict is None:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    # 1. Current world transform of the child
    child_world_pos, child_world_rot = resolve_world_transform(child_dict, comps_map)

    # 2. Target parent's world transform
    clean_parent = (new_parent_id.strip() if isinstance(new_parent_id, str) else None) or None
    if clean_parent is None or clean_parent not in comps_map:
        # Attaching to World: new local transform IS the world transform!
        return child_world_pos, child_world_rot

    parent_world_pos, parent_world_rot = resolve_world_transform(clean_parent, comps_map)

    # 3. New local position: R_parent^T * (child_world_pos - parent_world_pos)
    delta_pos = (
        child_world_pos[0] - parent_world_pos[0],
        child_world_pos[1] - parent_world_pos[1],
        child_world_pos[2] - parent_world_pos[2],
    )
    R_p = euler_to_matrix(*parent_world_rot)
    R_p_inv = transpose_matrix(R_p)
    new_local_pos = rotate_vector(delta_pos, R_p_inv)

    # 4. New local rotation: R_parent^T * R_child_world
    R_child = euler_to_matrix(*child_world_rot)
    R_local = multiply_rotations(R_p_inv, R_child)
    new_local_rot = matrix_to_euler(R_local)

    return new_local_pos, new_local_rot


def reparent_component(
    component: dict[str, Any] | Any,
    new_parent_id: str | None,
    comps_or_project: Any,
    *,
    preserve_world_transform: bool = True,
) -> None:
    """Reparent a component to new_parent_id (or None for World), recalculating its
    local transform so its world coordinates and visual appearance do not change.
    """
    comp = _get_comp_dict(component)
    if comp is None:
        return

    clean_parent = (new_parent_id.strip() if isinstance(new_parent_id, str) else None) or None

    if preserve_world_transform:
        new_pos, new_rot = compute_reparented_transform(comp, clean_parent, comps_or_project)

        tf = comp.setdefault("transform", {})
        if not isinstance(tf, dict):
            tf = {}
            comp["transform"] = tf
        pos = tf.setdefault("position", {})
        if not isinstance(pos, dict):
            pos = {}
            tf["position"] = pos
        rot = tf.setdefault("rotation", {})
        if not isinstance(rot, dict):
            rot = {}
            tf["rotation"] = rot

        pos["x"] = round(new_pos[0], 4)
        pos["y"] = round(new_pos[1], 4)
        pos["z"] = round(new_pos[2], 4)

        rot["roll"] = round(new_rot[0], 4)
        rot["pitch"] = round(new_rot[1], 4)
        rot["yaw"] = round(new_rot[2], 4)

        if "x" in comp:
            comp["x"] = pos["x"]
        if "y" in comp:
            comp["y"] = pos["y"]
        if "z" in comp:
            comp["z"] = pos["z"]

        # Clear expressions on transform so they don't overwrite the recalculated local transform
        if isinstance(pos, dict) and "_expressions" in pos:
            pos.pop("_expressions", None)
        if isinstance(rot, dict) and "_expressions" in rot:
            rot.pop("_expressions", None)
        if "transform_expressions" in comp:
            comp.pop("transform_expressions", None)
        params = comp.get("parameters")
        if isinstance(params, dict) and "transform_expressions" in params:
            params.pop("transform_expressions", None)

    if clean_parent:
        comp["attach_to"] = clean_parent
        comp["parent"] = clean_parent
    else:
        comp.pop("attach_to", None)
        comp.pop("parent", None)
