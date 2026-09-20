"""Triangle primitive component: definition, editor, and 3D scene rendering."""

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

TYPE_DEBUG_TRIANGLE = "org.setuav.debug:triangle"


class TriangleComponentEditor(BaseDebugComponentEditor):
    """Property editor for Triangle primitive components."""

    FIELDS = (
        ParameterField(
            key="base_width",
            label="Base Width",
            unit="mm",
            field_type=float,
            default=150.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Width of triangle base along X axis",
        ),
        ParameterField(
            key="height",
            label="Apex Height",
            unit="mm",
            field_type=float,
            default=150.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Height of triangle apex along Z axis",
        ),
        ParameterField(
            key="color",
            label="Surface Color",
            field_type=str,
            default="#9B59B6",
            widget_type="color",
            tooltip="Triangle surface color in Hex",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


def create_triangle_component(comp_id: str, name: str) -> dict[str, Any]:
    """Create data schema for a Triangle debug component."""
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_TRIANGLE,
        "parent": None,
        "mass": 3.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 150.0, "y": 10.0, "z": 150.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "base_width": 150.0,
            "height": 150.0,
            "color": "#9B59B6",
        },
    }


def add_triangle_to_viewport(
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
    """Add or update a triangle primitive in the 3D viewport."""
    bw = float(params.get("base_width", 150.0))
    h = float(params.get("height", 150.0))
    color = parse_color_rgba(params.get("color", "#9B59B6"))
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


# Alias for backward compatibility
render_triangle = add_triangle_to_viewport

register_renderer(TYPE_DEBUG_TRIANGLE, add_triangle_to_viewport)
