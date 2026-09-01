from math import cos, radians, sin
from typing import Any, cast

from .data import Point3D

Matrix4 = tuple[tuple[float, float, float, float], ...]


def identity_matrix() -> Matrix4:
    return (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def multiply_matrix(left: Matrix4, right: Matrix4) -> Matrix4:
    return cast(
        Matrix4,
        tuple(
            tuple(sum(left[row][k] * right[k][column] for k in range(4)) for column in range(4))
            for row in range(4)
        ),
    )


def transform_matrix(value: object) -> Matrix4:
    transform = value if isinstance(value, dict) else {}
    position = transform.get("position")
    position = position if isinstance(position, dict) else {}
    rotation = transform.get("rotation")
    rotation = rotation if isinstance(rotation, dict) else {}
    roll_val = rotation.get("roll") if "roll" in rotation else rotation.get("x")
    pitch_val = rotation.get("pitch") if "pitch" in rotation else rotation.get("y")
    yaw_val = rotation.get("yaw") if "yaw" in rotation else rotation.get("z")
    roll = radians(_number(roll_val))
    pitch = radians(_number(pitch_val))
    yaw = radians(_number(yaw_val))
    cr, sr = cos(roll), sin(roll)
    cp, sp = cos(pitch), sin(pitch)
    cy, sy = cos(yaw), sin(yaw)
    return (
        (cp * cy, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, _number(position.get("x"))),
        (cp * sy, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, _number(position.get("y"))),
        (-sp, cp * sr, cp * cr, _number(position.get("z"))),
        (0.0, 0.0, 0.0, 1.0),
    )


def derivation_matrix(value: object) -> Matrix4:
    derivation = value if isinstance(value, dict) else {}
    if derivation.get("type") != "mirror":
        return identity_matrix()
    offset = _number(derivation.get("offset"))
    plane = str(derivation.get("plane", ""))
    axis = {"YZ": 0, "XZ": 1, "XY": 2}.get(plane)
    if axis is None:
        return identity_matrix()
    rows = [list(row) for row in identity_matrix()]
    rows[axis][axis] = -1.0
    rows[axis][3] = 2.0 * offset
    return cast(Matrix4, tuple(tuple(row) for row in rows))


def transform_point(matrix: Matrix4, point: Point3D) -> Point3D:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def section_transform(
    value: object,
    chord: float = 0.0,
    twist_location: float = 0.0,
) -> Matrix4:
    section = value if isinstance(value, dict) else {}
    rotation = section.get("rotation")
    rotation = rotation if isinstance(rotation, dict) else {}
    position = section.get("position")
    position = position if isinstance(position, dict) else {}

    roll_val = rotation.get("roll") if "roll" in rotation else rotation.get("x")
    pitch_val = rotation.get("pitch") if "pitch" in rotation else rotation.get("y")
    yaw_val = rotation.get("yaw") if "yaw" in rotation else rotation.get("z")
    roll = radians(_number(roll_val))
    pitch = radians(_number(pitch_val))
    yaw = radians(_number(yaw_val))
    cr, sr = cos(roll), sin(roll)
    cp, sp = cos(pitch), sin(pitch)
    cy, sy = cos(yaw), sin(yaw)

    r00, r01, r02 = cp * cy, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr
    r10, r11, r12 = cp * sy, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr
    r20, r21, r22 = -sp, cp * sr, cp * cr

    x_pivot = twist_location * chord
    px = _number(position.get("x"))
    py = _number(position.get("y"))
    pz = _number(position.get("z"))

    tx = px + x_pivot * (1.0 - r00)
    ty = py - x_pivot * r10
    tz = pz - x_pivot * r20

    return (
        (r00, r01, r02, tx),
        (r10, r11, r12, ty),
        (r20, r21, r22, tz),
        (0.0, 0.0, 0.0, 1.0),
    )


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
