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
    """Return the matrix of a component transform (rotation keyed by roll/pitch/yaw)."""
    transform = value if isinstance(value, dict) else {}
    position = transform.get("position")
    position = position if isinstance(position, dict) else {}
    rotation = transform.get("rotation")
    rotation = rotation if isinstance(rotation, dict) else {}
    roll = radians(number_field(rotation, "roll", 0.0))
    pitch = radians(number_field(rotation, "pitch", 0.0))
    yaw = radians(number_field(rotation, "yaw", 0.0))
    cr, sr = cos(roll), sin(roll)
    cp, sp = cos(pitch), sin(pitch)
    cy, sy = cos(yaw), sin(yaw)
    px = number_field(position, "x", 0.0)
    py = number_field(position, "y", 0.0)
    pz = number_field(position, "z", 0.0)
    return (
        (cp * cy, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, px),
        (cp * sy, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, py),
        (-sp, cp * sr, cp * cr, pz),
        (0.0, 0.0, 0.0, 1.0),
    )


def derivation_matrix(value: object) -> Matrix4:
    derivation = value if isinstance(value, dict) else {}
    if derivation.get("type") != "mirror":
        return identity_matrix()
    offset = number_field(derivation, "offset", 0.0)
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
    """Return the matrix of a section frame (rotation keyed by x/y/z axes).

    The rotation pivots about the chord point at ``twist_location * chord``.
    """
    section = value if isinstance(value, dict) else {}
    rotation = section.get("rotation")
    rotation = rotation if isinstance(rotation, dict) else {}
    position = section.get("position")
    position = position if isinstance(position, dict) else {}

    roll = radians(number_field(rotation, "x", 0.0))
    pitch = radians(number_field(rotation, "y", 0.0))
    yaw = radians(number_field(rotation, "z", 0.0))
    cr, sr = cos(roll), sin(roll)
    cp, sp = cos(pitch), sin(pitch)
    cy, sy = cos(yaw), sin(yaw)

    r00, r01, r02 = cp * cy, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr
    r10, r11, r12 = cp * sy, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr
    r20, r21, r22 = -sp, cp * sr, cp * cr

    x_pivot = twist_location * chord
    px = number_field(position, "x", 0.0)
    py = number_field(position, "y", 0.0)
    pz = number_field(position, "z", 0.0)

    tx = px + x_pivot * (1.0 - r00)
    ty = py - x_pivot * r10
    tz = pz - x_pivot * r20

    return (
        (r00, r01, r02, tx),
        (r10, r11, r12, ty),
        (r20, r21, r22, tz),
        (0.0, 0.0, 0.0, 1.0),
    )


def number_field(owner: dict[str, Any], key: str, default: float | None = None) -> float:
    """Read a numeric field of a geometry mapping.

    A missing key returns ``default``; without a default it is an error. A present value
    must be an int or float.
    """
    if key not in owner:
        if default is None:
            raise ValueError(f"Missing numeric field {key!r}")
        return default
    value = owner[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Field {key!r} must be a number, got {value!r}")
    return float(value)
