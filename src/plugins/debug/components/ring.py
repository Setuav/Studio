"""Ring primitive component: definition, editor, and 3D scene rendering."""

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

TYPE_DEBUG_RING = "org.setuav.debug:ring"


class RingComponent(Component):
    """Ring primitive component definition with unit and parameter metadata."""

    COMPONENT_TYPE = TYPE_DEBUG_RING

    outer_radius = ParameterField(
        label="Outer Radius",
        unit="mm",
        field_type=float,
        default=125.0,
        min_value=1.0,
        max_value=10000.0,
        decimals=1,
        tooltip="Outer boundary radius",
    )
    axis = ParameterField(
        label="Normal Axis",
        field_type=str,
        default="Z",
        options=(("X", "X-Axis"), ("Y", "Y-Axis"), ("Z", "Z-Axis")),
        tooltip="Normal axis of the ring plane",
    )
    color = ParameterField(
        label="Wireframe Color",
        field_type=str,
        default="#F1C40F",
        widget_type="color",
        tooltip="Ring wireframe color in Hex",
    )


class RingComponentEditor(BaseDebugComponentEditor):
    """Property editor for Ring primitive components."""

    def __init__(
        self, api: StudioAPI, component: dict[str, Any] | Component, parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=RingComponent.get_fields(), parent=parent)


def create_ring_component(comp_id: str, name: str) -> RingComponent:
    """Create data schema for a Ring debug component."""
    return RingComponent(id=comp_id, name=name, mass=10.0)


def add_ring_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any] | RingComponent,
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a ring primitive in the 3D viewport."""
    ring = params if isinstance(params, RingComponent) else RingComponent(params)
    outer_r = float(ring.outer_radius)
    axis = str(ring.axis).upper()
    base_normal: tuple[float, float, float]
    if axis == "X":
        base_normal = (1.0, 0.0, 0.0)
    elif axis == "Y":
        base_normal = (0.0, 1.0, 0.0)
    else:
        base_normal = (0.0, 0.0, 1.0)
    normal = rotate_vector(base_normal, rotation)
    color = parse_color_rgba(ring.color)
    viewport.add_ring(
        comp_id,
        center=(px, py, pz),
        normal=normal,
        radius=outer_r,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_RING, add_ring_to_viewport)
