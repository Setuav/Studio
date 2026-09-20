"""Box primitive component: definition, editor, and 3D scene rendering."""

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
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

TYPE_DEBUG_BOX = "org.setuav.debug:box"


class BoxComponent(Component):
    """Box primitive component definition with unit and parameter metadata."""

    COMPONENT_TYPE = TYPE_DEBUG_BOX

    length = ParameterField(
        label="Length (X)",
        unit="mm",
        field_type=float,
        default=200.0,
        min_value=1.0,
        max_value=50000.0,
        decimals=1,
        tooltip="Box dimension along X axis",
    )
    width = ParameterField(
        label="Width (Y)",
        unit="mm",
        field_type=float,
        default=150.0,
        min_value=1.0,
        max_value=50000.0,
        decimals=1,
        tooltip="Box dimension along Y axis",
    )
    height = ParameterField(
        label="Height (Z)",
        unit="mm",
        field_type=float,
        default=100.0,
        min_value=1.0,
        max_value=50000.0,
        decimals=1,
        tooltip="Box dimension along Z axis",
    )
    color = ParameterField(
        label="Surface Color",
        field_type=str,
        default="#4A90E2",
        widget_type="color",
        tooltip="Surface color in Hex (e.g. #4A90E2)",
    )


class BoxComponentEditor(BaseDebugComponentEditor):
    """Property editor for Box primitive components."""

    def __init__(
        self, api: StudioAPI, component: dict[str, Any] | Component, parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=BoxComponent.get_fields(), parent=parent)


def create_box_component(comp_id: str, name: str) -> BoxComponent:
    """Create data schema for a Box debug component."""
    return BoxComponent(id=comp_id, name=name, mass=50.0)


def add_box_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any] | BoxComponent,
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a box primitive in the 3D viewport."""
    box = params if isinstance(params, BoxComponent) else BoxComponent(params)
    viewport.add_box(
        comp_id,
        center=(px, py, pz),
        size=(box.length, box.width, box.height),
        rotation=rotation,
        name=name,
        layer=DEBUG_LAYER,
        color=parse_color_rgba(box.color),
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_BOX, add_box_to_viewport)
