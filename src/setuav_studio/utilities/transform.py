"""Spatial transform calculations and attachment utilities for Setuav Studio components."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

from setuav_studio.model.expression import set_expression

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


def _get_comp_dict(item: Any) -> dict[str, Any]:
    """Return the component dictionary of a component dictionary or model."""
    if isinstance(item, dict):
        return item
    raw = getattr(item, "raw_data", None)
    if isinstance(raw, dict):
        return raw
    raise TypeError(f"{type(item).__name__} is not a component.")


def components_by_id(source: Any) -> dict[str, dict[str, Any]]:
    """Index components by id.

    ``source`` is a project document, project data with a ``components`` list, a
    component list, or a mapping of component id to component.
    """
    from setuav_studio.project.document import ProjectDocument

    if isinstance(source, ProjectDocument):
        components = source.data["components"]
    elif isinstance(source, dict) and isinstance(source.get("components"), list):
        components = source["components"]
    elif isinstance(source, dict):
        return {str(key): _get_comp_dict(value) for key, value in source.items()}
    elif isinstance(source, (list, tuple)):
        components = source
    else:
        raise TypeError(f"Cannot index components of a {type(source).__name__}.")
    return {str(comp["id"]): comp for comp in map(_get_comp_dict, components)}


def get_local_transform(comp: dict[str, Any]) -> tuple[Point3D, Rotation3D]:
    """Extract the (position, rotation) of a component relative to what it attaches to."""
    tf = comp.get("transform")
    tf_dict = tf if isinstance(tf, dict) else {}
    pos = tf_dict.get("position")
    pos_dict = pos if isinstance(pos, dict) else {}
    rot = tf_dict.get("rotation")
    rot_dict = rot if isinstance(rot, dict) else {}

    lx = float(pos_dict.get("x", 0.0) or 0.0)
    ly = float(pos_dict.get("y", 0.0) or 0.0)
    lz = float(pos_dict.get("z", 0.0) or 0.0)

    l_roll = float(rot_dict.get("roll", 0.0) or 0.0)
    l_pitch = float(rot_dict.get("pitch", 0.0) or 0.0)
    l_yaw = float(rot_dict.get("yaw", 0.0) or 0.0)

    return (lx, ly, lz), (l_roll, l_pitch, l_yaw)


def resolve_world_transform(
    comp_id: str,
    components: Mapping[str, dict[str, Any]],
) -> tuple[Point3D, Rotation3D]:
    """Return the vehicle-frame (position, rotation) of ``comp_id``.

    A component is placed relative to the component it attaches to, and an unattached
    component relative to the vehicle. Raises ValueError for a component or attach
    target missing from ``components`` and for an attachment cycle.
    """
    chain: list[dict[str, Any]] = []
    current: str | None = comp_id
    while current is not None:
        if any(str(comp["id"]) == current for comp in chain):
            raise ValueError(f"Component '{comp_id}' has an attachment cycle through '{current}'.")
        try:
            comp = components[current]
        except KeyError:
            owner = (
                f"'{current}', which '{chain[-1]['id']}' attaches to," if chain else f"'{current}'"
            )
            raise ValueError(f"Component {owner} is not in the component set.") from None
        chain.append(comp)
        target = comp.get("attach_to")
        current = str(target) if target else None

    world_pos, world_rot = get_local_transform(chain[-1])
    for comp in reversed(chain[:-1]):
        local_pos, local_rot = get_local_transform(comp)
        # R_target * local_pos + p_target
        rx, ry, rz = rotate_vector(local_pos, world_rot)
        world_pos = (world_pos[0] + rx, world_pos[1] + ry, world_pos[2] + rz)
        # R_world = R_target * R_local
        world_rot = matrix_to_euler(
            multiply_rotations(euler_to_matrix(*world_rot), euler_to_matrix(*local_rot))
        )
    return world_pos, world_rot


def attached_component_ids(comp_id: str, components: Mapping[str, dict[str, Any]]) -> set[str]:
    """Return the ids of every component attached to ``comp_id``, directly or through others."""
    attached: set[str] = set()
    frontier = {comp_id}
    while frontier:
        frontier = {
            other_id
            for other_id, other in components.items()
            if str(other.get("attach_to") or "") in frontier and other_id not in attached
        }
        attached |= frontier
    return attached


def compute_attached_transform(
    component: dict[str, Any] | Any,
    target_id: str | None,
    comps_or_project: Any,
) -> tuple[Point3D, Rotation3D]:
    """Return the position and rotation that keep a component in place when it is
    attached to ``target_id`` (None for the vehicle)."""
    comps_map = components_by_id(comps_or_project)
    comp = _get_comp_dict(component)
    comps_map.setdefault(str(comp["id"]), comp)

    world_pos, world_rot = resolve_world_transform(str(comp["id"]), comps_map)
    if target_id is None:
        return world_pos, world_rot

    target_pos, target_rot = resolve_world_transform(target_id, comps_map)
    # Local position: R_target^T * (world_pos - target_pos)
    delta_pos = (
        world_pos[0] - target_pos[0],
        world_pos[1] - target_pos[1],
        world_pos[2] - target_pos[2],
    )
    r_target_inv = transpose_matrix(euler_to_matrix(*target_rot))
    local_pos = rotate_vector(delta_pos, r_target_inv)
    # Local rotation: R_target^T * R_world
    local_rot = matrix_to_euler(multiply_rotations(r_target_inv, euler_to_matrix(*world_rot)))
    return local_pos, local_rot


def attach_component(
    component: dict[str, Any] | Any,
    target_id: str | None,
    comps_or_project: Any,
    *,
    preserve_world_transform: bool,
) -> None:
    """Attach a component to ``target_id``, or to the vehicle when it is None.

    With ``preserve_world_transform`` the component's position and rotation are
    recomputed so it stays where it is; otherwise they are kept and the component
    moves with the new frame. Raises ValueError for an unknown target or a target
    that is attached to the component.
    """
    comp = _get_comp_dict(component)
    comp_id = str(comp["id"])
    if target_id is not None:
        comps_map = components_by_id(comps_or_project)
        if target_id not in comps_map:
            raise ValueError(f"Attach target '{target_id}' is not in the component set.")
        if target_id == comp_id or target_id in attached_component_ids(comp_id, comps_map):
            raise ValueError(f"Component '{comp_id}' cannot attach to '{target_id}': cycle.")

    if preserve_world_transform:
        new_pos, new_rot = compute_attached_transform(comp, target_id, comps_or_project)
        tf = comp.setdefault("transform", {})
        pos = tf.setdefault("position", {})
        rot = tf.setdefault("rotation", {})
        pos.update(x=round(new_pos[0], 4), y=round(new_pos[1], 4), z=round(new_pos[2], 4))
        rot.update(roll=round(new_rot[0], 4), pitch=round(new_rot[1], 4), yaw=round(new_rot[2], 4))
        # The recomputed values replace any expression that defined them.
        for axis in ("x", "y", "z"):
            set_expression(pos, axis, None)
        for axis in ("roll", "pitch", "yaw"):
            set_expression(rot, axis, None)

    if target_id is None:
        comp.pop("attach_to", None)
    else:
        comp["attach_to"] = target_id
