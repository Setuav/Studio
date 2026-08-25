"""Small dependency-free spatial transform helpers for mass calculations."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin
from typing import Any

from ..models import Vector3

Matrix3 = tuple[tuple[float, float, float], ...]
Matrix4 = tuple[tuple[float, float, float, float], ...]


class TransformError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorldTransform:
    matrix: Matrix4

    @property
    def rotation(self) -> Matrix3:
        return tuple(tuple(self.matrix[row][column] for column in range(3)) for row in range(3))

    def point_mm_to_m(self, point_mm: Vector3) -> Vector3:
        point = transform_point(self.matrix, point_mm)
        return tuple(value / 1000.0 for value in point)  # type: ignore[return-value]


def identity_matrix() -> Matrix4:
    return (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def multiply_matrix(left: Matrix4, right: Matrix4) -> Matrix4:
    return tuple(
        tuple(
            sum(left[row][index] * right[index][column] for index in range(4))
            for column in range(4)
        )
        for row in range(4)
    )


def transform_matrix(value: object) -> Matrix4:
    transform = value if isinstance(value, dict) else {}
    position = transform.get("position")
    position = position if isinstance(position, dict) else {}
    rotation = transform.get("rotation")
    rotation = rotation if isinstance(rotation, dict) else {}

    roll = radians(_number(rotation.get("roll", rotation.get("x", 0.0))))
    pitch = radians(_number(rotation.get("pitch", rotation.get("y", 0.0))))
    yaw = radians(_number(rotation.get("yaw", rotation.get("z", 0.0))))
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
    axis = {"YZ": 0, "XZ": 1, "XY": 2}.get(str(derivation.get("plane", "XZ")))
    if axis is None:
        return identity_matrix()
    rows = [list(row) for row in identity_matrix()]
    rows[axis][axis] = -1.0
    rows[axis][3] = 2.0 * _number(derivation.get("offset"))
    return tuple(tuple(row) for row in rows)


def transform_point(matrix: Matrix4, point: Vector3) -> Vector3:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def frame_parent(component: dict[str, Any]) -> str | None:
    attach_to = component.get("attach_to")
    if isinstance(attach_to, str) and attach_to:
        return attach_to
    parent = component.get("parent")
    return parent if isinstance(parent, str) and parent else None


def resolve_world_transforms(
    components: list[dict[str, Any]],
) -> dict[str, WorldTransform]:
    by_id = {
        str(component["id"]): component
        for component in components
        if isinstance(component.get("id"), str)
    }
    cache: dict[str, WorldTransform] = {}

    def resolve(component_id: str, resolving: frozenset[str] = frozenset()) -> WorldTransform:
        if component_id in cache:
            return cache[component_id]
        if component_id in resolving:
            raise TransformError(f"Component transform cycle at {component_id!r}")
        component = by_id.get(component_id)
        if component is None:
            raise TransformError(f"Unknown component transform parent {component_id!r}")

        parent_id = frame_parent(component)
        parent = (
            resolve(parent_id, resolving | {component_id}).matrix
            if parent_id is not None
            else identity_matrix()
        )
        local = transform_matrix(component.get("transform"))
        if component.get("kind") == "instance":
            source = by_id.get(str(component.get("source") or ""))
            if source is not None:
                local = multiply_matrix(
                    local,
                    multiply_matrix(
                        derivation_matrix(component.get("derivation")),
                        transform_matrix(source.get("transform")),
                    ),
                )
        result = WorldTransform(multiply_matrix(parent, local))
        cache[component_id] = result
        return result

    for component_id in by_id:
        resolve(component_id)
    return cache


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
