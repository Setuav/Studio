from collections.abc import Callable
from copy import deepcopy
from math import cos, radians, sin
from typing import Any

from setuav_studio.geometry_data import GeometryData, LoftGeometry, Point3D, Section
from setuav_studio.project import ProjectDocument


GeometryProvider = Callable[[dict[str, Any]], tuple[LoftGeometry, ...]]
Matrix4 = tuple[tuple[float, float, float, float], ...]


def build_project_geometry(
    project: ProjectDocument,
    providers: dict[str, GeometryProvider],
) -> GeometryData:
    components = project.data.get("components")
    if not isinstance(components, list):
        return GeometryData()

    items = {
        item["id"]: item
        for item in components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    world_cache: dict[str, Matrix4] = {}

    def world_matrix(item_id: str, resolving: frozenset[str] = frozenset()) -> Matrix4:
        if item_id in world_cache:
            return world_cache[item_id]
        if item_id in resolving:
            raise ValueError(f"Component parent cycle at {item_id!r}")
        item = items.get(item_id)
        if item is None:
            return identity_matrix()

        parent_id = item.get("parent")
        parent = (
            world_matrix(parent_id, resolving | {item_id})
            if isinstance(parent_id, str)
            else identity_matrix()
        )
        local = transform_matrix(item.get("transform"))
        if item.get("kind") == "instance":
            source = items.get(item.get("source"))
            source_transform = (
                transform_matrix(source.get("transform"))
                if isinstance(source, dict)
                else identity_matrix()
            )
            derivation = derivation_matrix(item.get("derivation"))
            local = multiply_matrix(local, multiply_matrix(derivation, source_transform))
        result = multiply_matrix(parent, local)
        world_cache[item_id] = result
        return result

    lofts: list[LoftGeometry] = []
    for item_id, item in items.items():
        source = item
        if item.get("kind") == "instance":
            candidate = items.get(item.get("source"))
            if not isinstance(candidate, dict):
                continue
            source = deepcopy(candidate)
            overrides = item.get("parameter_overrides")
            if isinstance(overrides, dict):
                parameters = source.get("parameters")
                if not isinstance(parameters, dict):
                    parameters = {}
                    source["parameters"] = parameters
                _merge(parameters, overrides)

        component_type = source.get("type")
        provider = providers.get(component_type) if isinstance(component_type, str) else None
        if provider is None:
            continue
        matrix = world_matrix(item_id)
        for loft in provider(source):
            lofts.append(_transform_loft(loft, matrix, item_id))
    return GeometryData(tuple(lofts))


def transform_matrix(value: object) -> Matrix4:
    transform = value if isinstance(value, dict) else {}
    position = transform.get("position")
    position = position if isinstance(position, dict) else {}
    rotation = transform.get("rotation")
    rotation = rotation if isinstance(rotation, dict) else {}
    roll = radians(_number(rotation.get("roll")))
    pitch = radians(_number(rotation.get("pitch")))
    yaw = radians(_number(rotation.get("yaw")))
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


def _transform_loft(loft: LoftGeometry, matrix: Matrix4, component_id: str) -> LoftGeometry:
    return LoftGeometry(
        component_id=component_id,
        sections=tuple(
            Section(tuple(transform_point(matrix, point) for point in section.points))
            for section in loft.sections
        ),
        color=loft.color,
        interpolation=loft.interpolation,
        subdivisions=loft.subdivisions,
        closed_ends=loft.closed_ends,
    )


def _merge(target: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
