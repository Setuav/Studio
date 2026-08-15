import math
from typing import Any

from setuav_studio.geometry_data import LoftGeometry, Section


_COLOR = (0.70, 0.70, 0.72)


def build_propulsor_geometry(component: dict[str, Any]) -> tuple[LoftGeometry, ...]:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    diameter = _number(parameters.get("diameter"))
    if diameter <= 0:
        return ()
    blade_count = max(1, int(_number(parameters.get("blade_count")) or 1))
    hub_radius = _number(parameters.get("hub_diameter")) * 0.5
    hub_radius = hub_radius if hub_radius > 0 else diameter * 0.04
    radius = diameter * 0.5
    thickness = max(2.0, diameter * 0.008)
    component_id = str(component.get("id") or "propulsor")
    lofts = [_cylinder(component_id, hub_radius, thickness)]
    for index in range(blade_count):
        angle = 2.0 * math.pi * index / blade_count
        lofts.append(
            _blade(
                component_id,
                angle,
                hub_radius * 0.8,
                radius,
                max(6.0, diameter * 0.035),
                thickness,
            )
        )
    return tuple(lofts)


def _cylinder(component_id: str, radius: float, thickness: float) -> LoftGeometry:
    def ring(x: float) -> Section:
        return Section(
            tuple(
                (
                    x,
                    radius * math.cos(2 * math.pi * index / 48),
                    radius * math.sin(2 * math.pi * index / 48),
                )
                for index in range(48)
            )
        )

    return LoftGeometry(
        component_id,
        (ring(-thickness * 0.5), ring(thickness * 0.5)),
        _COLOR,
        "linear",
        1,
    )


def _blade(
    component_id: str,
    angle: float,
    inner: float,
    outer: float,
    width: float,
    thickness: float,
) -> LoftGeometry:
    radial = (math.cos(angle), math.sin(angle))
    tangent = (-radial[1], radial[0])

    def ring(x: float) -> Section:
        points = []
        for distance, side in ((inner, -1), (outer, -1), (outer, 1), (inner, 1)):
            y = radial[0] * distance + tangent[0] * width * 0.5 * side
            z = radial[1] * distance + tangent[1] * width * 0.5 * side
            points.append((x, y, z))
        return Section(tuple(points))

    return LoftGeometry(
        component_id,
        (ring(-thickness * 0.5), ring(thickness * 0.5)),
        _COLOR,
        "linear",
        1,
    )


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
