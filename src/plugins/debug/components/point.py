"""Point cloud primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

from setuav_studio.api import Component, ParameterField
from setuav_studio.ui.viewport import ViewportProtocol

from .common import (
    DEBUG_LAYER,
    BaseDebugComponentEditor,
    parse_color_rgba,
    register_renderer,
    rotate_vector,
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

TYPE_DEBUG_POINT = "org.setuav.debug:point"


class PointComponent(Component):
    """Point cloud primitive component definition with unit and parameter metadata."""

    COMPONENT_TYPE = TYPE_DEBUG_POINT

    count = ParameterField(
        label="Point Count",
        field_type=int,
        default=100,
        min_value=1,
        max_value=10000,
        tooltip="Number of points distributed on sphere surface",
    )
    radius = ParameterField(
        label="Sphere Radius",
        unit="mm",
        field_type=float,
        default=150.0,
        min_value=1.0,
        max_value=10000.0,
        decimals=1,
        tooltip="Radius of the distribution sphere",
    )
    point_size = ParameterField(
        label="Point Size",
        unit="px",
        field_type=float,
        default=4.0,
        min_value=1.0,
        max_value=32.0,
        decimals=1,
        tooltip="Rendered point size in pixels",
    )
    color = ParameterField(
        label="Point Color",
        field_type=str,
        default="#E74C3C",
        widget_type="color",
        tooltip="Point color in Hex",
    )


class PointComponentEditor(BaseDebugComponentEditor):
    """Property editor for Point cloud primitive components."""

    def __init__(
        self, api: StudioAPI, component: dict[str, Any] | Component, parent: QWidget | None = None
    ) -> None:
        super().__init__(
            api, component, parameter_fields=PointComponent.get_fields(), parent=parent
        )


def create_point_component(comp_id: str, name: str) -> PointComponent:
    """Create data schema for a Point debug component."""
    return PointComponent(id=comp_id, name=name, mass=5.0)


def add_point_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any] | PointComponent,
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a point cloud primitive in the 3D viewport."""
    pt = params if isinstance(params, PointComponent) else PointComponent(params)
    count = max(1, int(pt.count))
    radius = float(pt.radius)
    pt_size = float(pt.point_size)
    color = parse_color_rgba(pt.color)
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
