"""Plane primitive component: definition, editor, and 3D scene rendering."""

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

TYPE_DEBUG_PLANE = "org.setuav.debug:plane"


class PlaneComponentEditor(BaseDebugComponentEditor):
    """Property editor for Plane primitive components."""

    FIELDS = (
        ParameterField(
            key="width",
            label="Width",
            unit="mm",
            field_type=float,
            default=200.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Width of the rectangular plane",
        ),
        ParameterField(
            key="length",
            label="Length / Height",
            unit="mm",
            field_type=float,
            default=200.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Length or height of the rectangular plane",
        ),
        ParameterField(
            key="axis",
            label="Orientation Plane",
            field_type=str,
            default="XY",
            options=(
                ("XY", "XY-Plane (Z-up)"),
                ("XZ", "XZ-Plane (Y-up)"),
                ("YZ", "YZ-Plane (X-up)"),
            ),
            tooltip="Reference plane determining normal axis",
        ),
        ParameterField(
            key="color",
            label="Surface Color",
            field_type=str,
            default="#2ECC71",
            widget_type="color",
            tooltip="Plane surface color in Hex",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


def create_plane_component(comp_id: str, name: str) -> dict[str, Any]:
    """Create data schema for a Plane debug component."""
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_PLANE,
        "parent": None,
        "mass": 5.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 200.0, "y": 200.0, "z": 5.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "width": 200.0,
            "length": 200.0,
            "axis": "XY",
            "color": "#2ECC71",
        },
    }


def add_plane_to_viewport(
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
    """Add or update a plane primitive in the 3D viewport."""
    w = float(params.get("width", 200.0))
    length = float(params.get("length", 200.0))
    axis = str(params.get("axis", "XY")).upper()
    color = parse_color_rgba(params.get("color", "#2ECC71"))
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


# Alias for backward compatibility
render_plane = add_plane_to_viewport

register_renderer(TYPE_DEBUG_PLANE, add_plane_to_viewport)
