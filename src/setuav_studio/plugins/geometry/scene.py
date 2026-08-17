from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .data import GeometryData, LoftGeometry, Section
from .transforms import (
    Matrix4,
    derivation_matrix,
    identity_matrix,
    multiply_matrix,
    transform_matrix,
    transform_point,
)

GeometryProvider = Callable[[dict[str, Any]], tuple[LoftGeometry, ...]]


def build_project_geometry(
    project: Any,
    providers: dict[str, GeometryProvider],
) -> GeometryData:
    project_data = getattr(project, "data", project) if project is not None else {}
    components = project_data.get("components") if isinstance(project_data, dict) else None
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

            # Invert deflection on mirrored instances for anti-symmetric surfaces (aileron, elevon)
            derivation = item.get("derivation")
            if isinstance(derivation, dict) and derivation.get("type") == "mirror":
                plane = derivation.get("plane", "XZ")
                if plane in ("XZ", "1", None):
                    params = source.get("parameters") if isinstance(source.get("parameters"), dict) else {}
                    geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}
                    cs_list = geom.get("control_surfaces")
                    if isinstance(cs_list, list):
                        for cs in cs_list:
                            if isinstance(cs, dict) and str(cs.get("type", "aileron")).lower() in ("aileron", "elevon"):
                                cs["deflection"] = -float(cs.get("deflection", 0.0))

        component_type = source.get("type")
        provider = providers.get(component_type) if isinstance(component_type, str) else None
        if provider is None:
            continue
        matrix = world_matrix(item_id)
        for loft in provider(source):
            lofts.append(_transform_loft(loft, matrix, item_id))
    return GeometryData(tuple(lofts))


def _transform_loft(loft: LoftGeometry, matrix: Matrix4, component_id: str) -> LoftGeometry:
    target_id = component_id
    if ":" in loft.component_id:
        sub_tag = loft.component_id.split(":", 1)[1]
        target_id = f"{component_id}:{sub_tag}"
    return LoftGeometry(
        component_id=target_id,
        sections=tuple(
            Section(tuple(transform_point(matrix, point) for point in section.points))
            for section in loft.sections
        ),
        color=loft.color,
        interpolation=loft.interpolation,
        station_spacing=loft.station_spacing,
        closed_ends=loft.closed_ends,
    )


def _merge(target: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)
