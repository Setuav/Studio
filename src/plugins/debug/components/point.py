"""Point cloud primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

from setuav_studio_sdk import ParameterField, ViewportProtocol

from .common import (
    DEBUG_LAYER,
    BaseDebugComponentEditor,
    parse_color_rgba,
    register_renderer,
    rotate_vector,
)

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

TYPE_DEBUG_POINT = "org.setuav.debug:point"


class PointComponentEditor(BaseDebugComponentEditor):
    """Property editor for Point cloud primitive components."""

    FIELDS = (
        ParameterField(
            key="count",
            label="Point Count",
            field_type=int,
            default=100,
            min_value=1,
            max_value=10000,
            tooltip="Number of points distributed on sphere surface",
        ),
        ParameterField(
            key="radius",
            label="Sphere Radius",
            unit="mm",
            field_type=float,
            default=150.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Radius of the distribution sphere",
        ),
        ParameterField(
            key="point_size",
            label="Point Size",
            unit="px",
            field_type=float,
            default=4.0,
            min_value=1.0,
            max_value=32.0,
            decimals=1,
            tooltip="Rendered point size in pixels",
        ),
        ParameterField(
            key="color",
            label="Point Color",
            field_type=str,
            default="#E74C3C",
            widget_type="color",
            tooltip="Point color in Hex",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


def create_point_component(comp_id: str, name: str) -> dict[str, Any]:
    """Create data schema for a Point debug component."""
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_POINT,
        "parent": None,
        "mass": 5.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "parameters": {
            "count": 100,
            "radius": 150.0,
            "point_size": 4.0,
            "color": "#E74C3C",
        },
    }


def add_point_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a point cloud primitive in the 3D viewport."""
    count = max(1, int(params.get("count", 100)))
    radius = float(params.get("radius", 150.0))
    pt_size = float(params.get("point_size", 4.0))
    color = parse_color_rgba(params.get("color", "#E74C3C"))
    pts: list[tuple[float, float, float]] = []
    phi = math.pi * (math.sqrt(5.0) - 1.0)
    for i in range(count):
        y_norm = 1.0 - (i / float(count - 1)) * 2.0 if count > 1 else 0.0
        r_y = math.sqrt(max(0.0, 1.0 - y_norm * y_norm))
        theta = phi * i
        lx = math.cos(theta) * r_y * radius
        ly = math.sin(theta) * r_y * radius
        lz = y_norm * radius
        rx, ry, rz = rotate_vector((lx, ly, lz), rotation)
        pts.append((px + rx, py + ry, pz + rz))
    viewport.add_points(
        comp_id,
        points=pts,
        size=pt_size,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_POINT, add_point_to_viewport)
