"""Triangle primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

from setuav_studio.sdk import Component, ParameterField, ViewportProtocol

from .common import (
    DEBUG_LAYER,
    BaseDebugComponentEditor,
    parse_color_rgba,
    register_renderer,
    rotate_vector,
)

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

TYPE_DEBUG_TRIANGLE = "org.setuav.debug:triangle"


class TriangleComponent(Component):
    """Triangle primitive component definition with unit and parameter metadata."""

    COMPONENT_TYPE = TYPE_DEBUG_TRIANGLE

    base_width = ParameterField(
        label="Base Width",
        unit="mm",
        field_type=float,
        default=150.0,
        min_value=1.0,
        max_value=50000.0,
        decimals=1,
        tooltip="Width of triangle base along X axis",
    )
    height = ParameterField(
        label="Apex Height",
        unit="mm",
        field_type=float,
        default=150.0,
        min_value=1.0,
        max_value=50000.0,
        decimals=1,
        tooltip="Height of triangle apex along Z axis",
    )
    color = ParameterField(
        label="Surface Color",
        field_type=str,
        default="#9B59B6",
        widget_type="color",
        tooltip="Triangle surface color in Hex",
    )


class TriangleComponentEditor(BaseDebugComponentEditor):
    """Property editor for Triangle primitive components."""

    def __init__(
        self, api: StudioAPI, component: dict[str, Any] | Component, parent: QWidget | None = None
    ) -> None:
        super().__init__(
            api, component, parameter_fields=TriangleComponent.get_fields(), parent=parent
        )


def create_triangle_component(comp_id: str, name: str) -> TriangleComponent:
    """Create data schema for a Triangle debug component."""
    return TriangleComponent(id=comp_id, name=name, mass=3.0)


def add_triangle_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any] | TriangleComponent,
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a triangle primitive in the 3D viewport."""
    tri = params if isinstance(params, TriangleComponent) else TriangleComponent(params)
    bw = float(tri.base_width)
    h = float(tri.height)
    color = parse_color_rgba(tri.color)
    d0 = rotate_vector((-bw * 0.5, 0.0, 0.0), rotation)
    d1 = rotate_vector((bw * 0.5, 0.0, 0.0), rotation)
    d2 = rotate_vector((0.0, 0.0, h), rotation)
    p0 = (px + d0[0], py + d0[1], pz + d0[2])
    p1 = (px + d1[0], py + d1[1], pz + d1[2])
    p2 = (px + d2[0], py + d2[1], pz + d2[2])
    tris = [(p0, p1, p2), (p0, p2, p1)]
    viewport.add_triangles(
        comp_id,
        triangles=tris,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_TRIANGLE, add_triangle_to_viewport)
