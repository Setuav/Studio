from math import cos, radians, sin
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
    return tuple(
        tuple(sum(left[row][k] * right[k][column] for k in range(4)) for column in range(4))
        for row in range(4)
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
    plane = derivation.get("plane")
    axis = {"YZ": 0, "XZ": 1, "XY": 2}.get(plane)
    if axis is None:
        return identity_matrix()
    rows = [list(row) for row in identity_matrix()]
    rows[axis][axis] = -1.0
    rows[axis][3] = 2.0 * offset
    return tuple(tuple(row) for row in rows)


def transform_point(matrix: Matrix4, point: Point3D) -> Point3D:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def section_transform(value: object) -> Matrix4:
    section = value if isinstance(value, dict) else {}
    rotation = section.get("rotation")
    rotation = rotation if isinstance(rotation, dict) else {}
    return transform_matrix(
        {
            "position": section.get("position"),
            "rotation": {
                "roll": rotation.get("x", 0),
                "pitch": rotation.get("y", 0),
                "yaw": rotation.get("z", 0),
            },
        }
    )


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
