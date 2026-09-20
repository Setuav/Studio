"""Ring primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

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

TYPE_DEBUG_RING = "org.setuav.debug:ring"


class RingComponentEditor(BaseDebugComponentEditor):
    """Property editor for Ring primitive components."""

    FIELDS = (
        ParameterField(
            key="outer_radius",
            label="Outer Radius",
            unit="mm",
            field_type=float,
            default=125.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Outer boundary radius",
        ),
        ParameterField(
            key="axis",
            label="Normal Axis",
            field_type=str,
            default="Z",
            options=(("X", "X-Axis"), ("Y", "Y-Axis"), ("Z", "Z-Axis")),
            tooltip="Normal axis of the ring plane",
        ),
        ParameterField(
            key="color",
            label="Wireframe Color",
            field_type=str,
            default="#F1C40F",
            widget_type="color",
            tooltip="Ring wireframe color in Hex",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


def create_ring_component(comp_id: str, name: str) -> dict[str, Any]:
    """Create data schema for a Ring debug component."""
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_RING,
        "parent": None,
        "mass": 10.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 250.0, "y": 250.0, "z": 10.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "outer_radius": 125.0,
            "axis": "Z",
            "color": "#F1C40F",
        },
    }


def add_ring_to_viewport(
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
    """Add or update a ring primitive in the 3D viewport."""
    outer_r = float(params.get("outer_radius", 125.0))
    axis = str(params.get("axis", "Z")).upper()
    base_normal: tuple[float, float, float]
    if axis == "X":
        base_normal = (1.0, 0.0, 0.0)
    elif axis == "Y":
        base_normal = (0.0, 1.0, 0.0)
    else:
        base_normal = (0.0, 0.0, 1.0)
    normal = rotate_vector(base_normal, rotation)
    color = parse_color_rgba(params.get("color", "#F1C40F"))
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


# Alias for backward compatibility
render_ring = add_ring_to_viewport

register_renderer(TYPE_DEBUG_RING, add_ring_to_viewport)
