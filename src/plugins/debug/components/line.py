"""Line primitive component: definition, editor, and 3D scene rendering."""

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

TYPE_DEBUG_LINE = "org.setuav.debug:line"


class LineComponentEditor(BaseDebugComponentEditor):
    """Property editor for Line primitive components."""

    FIELDS = (
        ParameterField(
            key="length",
            label="Length",
            unit="mm",
            field_type=float,
            default=200.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Length of the line segment",
        ),
        ParameterField(
            key="axis",
            label="Direction Axis",
            field_type=str,
            default="X",
            options=(("X", "X-Axis"), ("Y", "Y-Axis"), ("Z", "Z-Axis")),
            tooltip="Direction of the line",
        ),
        ParameterField(
            key="color",
            label="Line Color",
            field_type=str,
            default="#E74C3C",
            widget_type="color",
            tooltip="Line segment color in Hex",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


def create_line_component(comp_id: str, name: str) -> dict[str, Any]:
    """Create data schema for a Line debug component."""
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_LINE,
        "parent": None,
        "mass": 1.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "parameters": {
            "length": 200.0,
            "axis": "X",
            "color": "#E74C3C",
        },
    }


def add_line_to_viewport(
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
    """Add or update a line primitive in the 3D viewport."""
    length = float(params.get("length", 200.0))
    axis = str(params.get("axis", "X")).upper()
    color = parse_color_rgba(params.get("color", "#E74C3C"))
    base_dir: tuple[float, float, float]
    if axis == "Y":
        base_dir = (0.0, 1.0, 0.0)
    elif axis == "Z":
        base_dir = (0.0, 0.0, 1.0)
    else:
        base_dir = (1.0, 0.0, 0.0)
    half = length * 0.5
    dir_v = rotate_vector((half * base_dir[0], half * base_dir[1], half * base_dir[2]), rotation)
    line_pts = (
        (px - dir_v[0], py - dir_v[1], pz - dir_v[2]),
        (px + dir_v[0], py + dir_v[1], pz + dir_v[2]),
    )
    viewport.add_lines(
        comp_id,
        lines=[line_pts],
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_LINE, add_line_to_viewport)
