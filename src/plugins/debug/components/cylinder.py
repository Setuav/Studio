"""Cylinder primitive component: definition, editor, and 3D scene rendering."""

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

TYPE_DEBUG_CYLINDER = "org.setuav.debug:cylinder"


class CylinderComponent(Component):
    """Cylinder primitive component definition with unit and parameter metadata."""

    COMPONENT_TYPE = TYPE_DEBUG_CYLINDER

    radius = ParameterField(
        label="Radius",
        unit="mm",
        field_type=float,
        default=50.0,
        min_value=1.0,
        max_value=10000.0,
        decimals=1,
        tooltip="Radius of the cylinder cross section",
    )
    length = ParameterField(
        label="Length",
        unit="mm",
        field_type=float,
        default=200.0,
        min_value=1.0,
        max_value=50000.0,
        decimals=1,
        tooltip="Length of the cylinder along its axis",
    )
    axis = ParameterField(
        label="Alignment Axis",
        field_type=str,
        default="Z",
        options=(("X", "X-Axis"), ("Y", "Y-Axis"), ("Z", "Z-Axis")),
        tooltip="Longitudinal axis of the cylinder",
    )
    segments = ParameterField(
        label="Segments",
        field_type=int,
        default=32,
        min_value=3,
        max_value=128,
        tooltip="Number of circumferential polygon segments",
    )
    color = ParameterField(
        label="Surface Color",
        field_type=str,
        default="#E67E22",
        widget_type="color",
        tooltip="Surface color in Hex (e.g. #E67E22)",
    )


class CylinderComponentEditor(BaseDebugComponentEditor):
    """Property editor for Cylinder primitive components."""

    def __init__(
        self, api: StudioAPI, component: dict[str, Any] | Component, parent: QWidget | None = None
    ) -> None:
        super().__init__(
            api, component, parameter_fields=CylinderComponent.get_fields(), parent=parent
        )


def create_cylinder_component(comp_id: str, name: str) -> CylinderComponent:
    """Create data schema for a Cylinder debug component."""
    return CylinderComponent(id=comp_id, name=name, mass=40.0)


def add_cylinder_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any] | CylinderComponent,
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a cylinder primitive in the 3D viewport."""
    cyl = params if isinstance(params, CylinderComponent) else CylinderComponent(params)
    radius = float(cyl.radius)
    length = float(cyl.length)
    axis = str(cyl.axis).upper()
    segments = int(cyl.segments)
    color = parse_color_rgba(cyl.color)
    base_axis: tuple[float, float, float]
    if axis == "X":
        base_axis = (1.0, 0.0, 0.0)
    elif axis == "Y":
        base_axis = (0.0, 1.0, 0.0)
    else:
        base_axis = (0.0, 0.0, 1.0)
    dir_axis = rotate_vector(base_axis, rotation)
    half = length * 0.5
    start = (px - half * dir_axis[0], py - half * dir_axis[1], pz - half * dir_axis[2])
    end = (px + half * dir_axis[0], py + half * dir_axis[1], pz + half * dir_axis[2])
    viewport.add_cylinder(
        comp_id,
        start=start,
        end=end,
        radius=radius,
        segments=segments,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_CYLINDER, add_cylinder_to_viewport)
