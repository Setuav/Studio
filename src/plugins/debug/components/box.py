"""Box primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

from setuav_studio_sdk import ParameterField, ViewportProtocol

from .common import (
    DEBUG_LAYER,
    BaseDebugComponentEditor,
    parse_color_rgba,
    register_renderer,
)

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

TYPE_DEBUG_BOX = "org.setuav.debug:box"


class BoxComponentEditor(BaseDebugComponentEditor):
    """Property editor for Box primitive components."""

    FIELDS = (
        ParameterField(
            key="length",
            label="Length (X)",
            unit="mm",
            field_type=float,
            default=200.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Box dimension along X axis",
        ),
        ParameterField(
            key="width",
            label="Width (Y)",
            unit="mm",
            field_type=float,
            default=150.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Box dimension along Y axis",
        ),
        ParameterField(
            key="height",
            label="Height (Z)",
            unit="mm",
            field_type=float,
            default=100.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Box dimension along Z axis",
        ),
        ParameterField(
            key="color",
            label="Surface Color",
            field_type=str,
            default="#4A90E2",
            widget_type="color",
            tooltip="Surface color in Hex (e.g. #4A90E2)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


def create_box_component(comp_id: str, name: str) -> dict[str, Any]:
    """Create data schema for a Box debug component."""
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_BOX,
        "parent": None,
        "mass": 50.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 200.0, "y": 150.0, "z": 100.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "length": 200.0,
            "width": 150.0,
            "height": 100.0,
            "color": "#4A90E2",
        },
    }


def add_box_to_viewport(
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
    """Add or update a box primitive in the 3D viewport."""
    dx = float(params.get("length", 200.0))
    dy = float(params.get("width", 150.0))
    dz = float(params.get("height", 100.0))
    color = parse_color_rgba(params.get("color", "#4A90E2"))
    viewport.add_box(
        comp_id,
        center=(px, py, pz),
        size=(dx, dy, dz),
        rotation=rotation,
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


# Alias for backward compatibility
render_box = add_box_to_viewport

register_renderer(TYPE_DEBUG_BOX, add_box_to_viewport)
