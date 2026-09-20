"""Plane primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

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

TYPE_DEBUG_PLANE = "org.setuav.debug:plane"


class PlaneComponent(Component):
    """Plane primitive component definition with unit and parameter metadata."""

    COMPONENT_TYPE = TYPE_DEBUG_PLANE

    width = ParameterField(
        label="Width",
        unit="mm",
        field_type=float,
        default=200.0,
        min_value=1.0,
        max_value=50000.0,
        decimals=1,
        tooltip="Width of the rectangular plane",
    )
    length = ParameterField(
        label="Length / Height",
        unit="mm",
        field_type=float,
        default=200.0,
        min_value=1.0,
        max_value=50000.0,
        decimals=1,
        tooltip="Length or height of the rectangular plane",
    )
    axis = ParameterField(
        label="Orientation Plane",
        field_type=str,
        default="XY",
        options=(
            ("XY", "XY-Plane (Z-up)"),
            ("XZ", "XZ-Plane (Y-up)"),
            ("YZ", "YZ-Plane (X-up)"),
        ),
        tooltip="Reference plane determining normal axis",
    )
    color = ParameterField(
        label="Surface Color",
        field_type=str,
        default="#2ECC71",
        widget_type="color",
        tooltip="Plane surface color in Hex",
    )


class PlaneComponentEditor(BaseDebugComponentEditor):
    """Property editor for Plane primitive components."""

    def __init__(
        self, api: StudioAPI, component: dict[str, Any] | Component, parent: QWidget | None = None
    ) -> None:
        super().__init__(
            api, component, parameter_fields=PlaneComponent.get_fields(), parent=parent
        )


def create_plane_component(comp_id: str, name: str) -> PlaneComponent:
    """Create data schema for a Plane debug component."""
    return PlaneComponent(id=comp_id, name=name, mass=5.0)


def add_plane_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any] | PlaneComponent,
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a plane primitive in the 3D viewport."""
    plane = params if isinstance(params, PlaneComponent) else PlaneComponent(params)
    w = float(plane.width)
    length = float(plane.length)
    axis = str(plane.axis).upper()
    color = parse_color_rgba(plane.color)
    base_normal: tuple[float, float, float]
    if axis == "XZ":
        base_normal = (0.0, 1.0, 0.0)
    elif axis == "YZ":
        base_normal = (1.0, 0.0, 0.0)
    else:
        base_normal = (0.0, 0.0, 1.0)
    normal = rotate_vector(base_normal, rotation)
    viewport.add_plane(
        comp_id,
        center=(px, py, pz),
        normal=normal,
        width=w,
        height=length,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_PLANE, add_plane_to_viewport)
