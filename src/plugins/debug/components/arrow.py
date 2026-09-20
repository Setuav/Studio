"""Arrow primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

from setuav_studio.sdk import Component, ParameterField, ViewportProtocol
from setuav_studio_sdk.primitives import Point3D

from .common import (
    DEBUG_LAYER,
    BaseDebugComponentEditor,
    parse_color_rgba,
    register_renderer,
    rotate_vector,
)

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

TYPE_DEBUG_ARROW = "org.setuav.debug:arrow"


class ArrowComponent(Component):
    """Arrow primitive component definition with unit and parameter metadata."""

    COMPONENT_TYPE = TYPE_DEBUG_ARROW

    length = ParameterField(
        label="Length",
        unit="mm",
        field_type=float,
        default=150.0,
        min_value=1.0,
        max_value=10000.0,
        decimals=1,
        tooltip="Length of each directional arrow",
    )
    axis = ParameterField(
        label="Axes",
        field_type=str,
        default="All",
        options=(
            ("All", "All Axes (X, Y, Z)"),
            ("X", "X-Axis"),
            ("Y", "Y-Axis"),
            ("Z", "Z-Axis"),
        ),
        tooltip="Axes along which arrows are rendered",
    )
    color = ParameterField(
        label="Arrow Color",
        field_type=str,
        default="#1ABC9C",
        widget_type="color",
        tooltip="Arrow color in Hex",
    )


class ArrowComponentEditor(BaseDebugComponentEditor):
    """Property editor for Arrow primitive components."""

    def __init__(
        self, api: StudioAPI, component: dict[str, Any] | Component, parent: QWidget | None = None
    ) -> None:
        super().__init__(
            api, component, parameter_fields=ArrowComponent.get_fields(), parent=parent
        )


def create_arrow_component(comp_id: str, name: str) -> ArrowComponent:
    """Create data schema for an Arrow debug component."""
    return ArrowComponent(id=comp_id, name=name, mass=5.0)


def add_arrow_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any] | ArrowComponent,
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update an arrow primitive in the 3D viewport."""
    arrow = params if isinstance(params, ArrowComponent) else ArrowComponent(params)
    length = float(arrow.length)
    axis = str(arrow.axis)
    color = parse_color_rgba(arrow.color)
    arrows: list[tuple[Point3D, Point3D]] = []
    base_dirs: list[tuple[float, float, float]]
    if axis == "X":
        base_dirs = [(length, 0.0, 0.0)]
    elif axis == "Y":
        base_dirs = [(0.0, length, 0.0)]
    elif axis == "Z":
        base_dirs = [(0.0, 0.0, length)]
    else:
        base_dirs = [(length, 0.0, 0.0), (0.0, length, 0.0), (0.0, 0.0, length)]

    for bdir in base_dirs:
        rdir = rotate_vector(bdir, rotation)
        arrows.append(((px, py, pz), (px + rdir[0], py + rdir[1], pz + rdir[2])))

    viewport.add_arrows(
        comp_id,
        arrows=arrows,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_ARROW, add_arrow_to_viewport)
