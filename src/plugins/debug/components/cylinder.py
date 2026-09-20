"""Cylinder primitive component: definition, editor, and 3D scene rendering."""

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

TYPE_DEBUG_CYLINDER = "org.setuav.debug:cylinder"


class CylinderComponentEditor(BaseDebugComponentEditor):
    """Property editor for Cylinder primitive components."""

    FIELDS = (
        ParameterField(
            key="radius",
            label="Radius",
            unit="mm",
            field_type=float,
            default=50.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Radius of the cylinder cross section",
        ),
        ParameterField(
            key="length",
            label="Length",
            unit="mm",
            field_type=float,
            default=200.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Length of the cylinder along its axis",
        ),
        ParameterField(
            key="axis",
            label="Alignment Axis",
            field_type=str,
            default="Z",
            options=(("X", "X-Axis"), ("Y", "Y-Axis"), ("Z", "Z-Axis")),
            tooltip="Longitudinal axis of the cylinder",
        ),
        ParameterField(
            key="segments",
            label="Segments",
            field_type=int,
            default=32,
            min_value=3,
            max_value=128,
            tooltip="Number of circumferential polygon segments",
        ),
        ParameterField(
            key="color",
            label="Surface Color",
            field_type=str,
            default="#E67E22",
            widget_type="color",
            tooltip="Surface color in Hex (e.g. #E67E22)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


def create_cylinder_component(comp_id: str, name: str) -> dict[str, Any]:
    """Create data schema for a Cylinder debug component."""
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_CYLINDER,
        "parent": None,
        "mass": 40.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "cylinder",
            "size_mm": {"x": 100.0, "y": 100.0, "z": 200.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "radius": 50.0,
            "length": 200.0,
            "axis": "Z",
            "segments": 32,
            "color": "#E67E22",
        },
    }


def add_cylinder_to_viewport(
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
    """Add or update a cylinder primitive in the 3D viewport."""
    radius = float(params.get("radius", 50.0))
    length = float(params.get("length", 200.0))
    axis = str(params.get("axis", "Z")).upper()
    segments = int(params.get("segments", 32))
    color = parse_color_rgba(params.get("color", "#E67E22"))
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


# Alias for backward compatibility
render_cylinder = add_cylinder_to_viewport

register_renderer(TYPE_DEBUG_CYLINDER, add_cylinder_to_viewport)
