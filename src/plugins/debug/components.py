"""Component schemas, property editors, and creation helpers for debug primitives."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QWidget

from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio_sdk import ParameterField, StudioAPI

# Component Type IDs
TYPE_DEBUG_BOX = "org.setuav.debug:box"
TYPE_DEBUG_CYLINDER = "org.setuav.debug:cylinder"
TYPE_DEBUG_RING = "org.setuav.debug:ring"
TYPE_DEBUG_PLANE = "org.setuav.debug:plane"
TYPE_DEBUG_LINE = "org.setuav.debug:line"
TYPE_DEBUG_TRIANGLE = "org.setuav.debug:triangle"
TYPE_DEBUG_LOFT = "org.setuav.debug:loft"
TYPE_DEBUG_POINT = "org.setuav.debug:point"
TYPE_DEBUG_ARROW = "org.setuav.debug:arrow"

ALL_DEBUG_TYPES = (
    TYPE_DEBUG_BOX,
    TYPE_DEBUG_CYLINDER,
    TYPE_DEBUG_RING,
    TYPE_DEBUG_PLANE,
    TYPE_DEBUG_LINE,
    TYPE_DEBUG_TRIANGLE,
    TYPE_DEBUG_LOFT,
    TYPE_DEBUG_POINT,
    TYPE_DEBUG_ARROW,
)


def _parse_sequence_rgba(nums: list[float]) -> tuple[float, float, float, float]:
    if any(v > 1.0 for v in nums[:3]):
        r = min(1.0, max(0.0, nums[0] / 255.0))
        g = min(1.0, max(0.0, nums[1] / 255.0))
        b = min(1.0, max(0.0, nums[2] / 255.0))
        a = min(1.0, max(0.0, nums[3] / 255.0)) if len(nums) >= 4 else 1.0
    else:
        r = min(1.0, max(0.0, nums[0]))
        g = min(1.0, max(0.0, nums[1]))
        b = min(1.0, max(0.0, nums[2]))
        a = min(1.0, max(0.0, nums[3])) if len(nums) >= 4 else 1.0
    return (r, g, b, a)


def _parse_hex_rgba(text: str) -> tuple[float, float, float, float] | None:
    try:
        if len(text) == 7:
            return (
                int(text[1:3], 16) / 255.0,
                int(text[3:5], 16) / 255.0,
                int(text[5:7], 16) / 255.0,
                1.0,
            )
        if len(text) == 4:
            return (
                int(text[1] * 2, 16) / 255.0,
                int(text[2] * 2, 16) / 255.0,
                int(text[3] * 2, 16) / 255.0,
                1.0,
            )
        if len(text) == 9:
            return (
                int(text[1:3], 16) / 255.0,
                int(text[3:5], 16) / 255.0,
                int(text[5:7], 16) / 255.0,
                int(text[7:9], 16) / 255.0,
            )
    except ValueError:
        pass
    return None


def parse_color_rgba(
    val: Any, default: tuple[float, float, float, float] = (0.3, 0.6, 0.9, 1.0)
) -> tuple[float, float, float, float]:
    """Parse color value into an (r, g, b, a) tuple in 0.0 - 1.0 range."""
    if isinstance(val, (tuple, list)) and len(val) >= 3:
        try:
            return _parse_sequence_rgba([float(v) for v in val[:4]])
        except (ValueError, TypeError):
            return default

    if isinstance(val, str):
        text = val.strip()
        if not text:
            return default

        if text.startswith("#"):
            parsed_hex = _parse_hex_rgba(text)
            if parsed_hex is not None:
                return parsed_hex

        if text.lower().startswith("rgb"):
            left_paren = text.find("(")
            right_paren = text.rfind(")")
            if left_paren != -1 and right_paren != -1:
                text = text[left_paren + 1 : right_paren]

        clean = text.strip("()[]")
        parts = [p.strip() for p in clean.replace(";", ",").split(",") if p.strip()]
        if len(parts) < 3:
            parts = [p.strip() for p in clean.split() if p.strip()]
        if len(parts) >= 3:
            try:
                return _parse_sequence_rgba([float(p) for p in parts[:4]])
            except ValueError:
                pass

    return default


# ----------------------------------------------------------------------
# Property Editors
# ----------------------------------------------------------------------


class BoxComponentEditor(BaseComponentEditor):
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


class CylinderComponentEditor(BaseComponentEditor):
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


class RingComponentEditor(BaseComponentEditor):
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
            key="inner_radius",
            label="Inner Radius",
            unit="mm",
            field_type=float,
            default=25.0,
            min_value=0.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Inner hub radius",
        ),
        ParameterField(
            key="axis",
            label="Normal Axis",
            field_type=str,
            default="Z",
            options=(("X", "X-Axis"), ("Y", "Y-Axis"), ("Z", "Z-Axis")),
            tooltip="Normal vector orientation",
        ),
        ParameterField(
            key="color",
            label="Ring Color",
            field_type=str,
            default="#F1C40F",
            widget_type="color",
            tooltip="Ring color in Hex (e.g. #F1C40F)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


class PlaneComponentEditor(BaseComponentEditor):
    """Property editor for Plane surface primitive components."""

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
            tooltip="First planar dimension",
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
            tooltip="Second planar dimension",
        ),
        ParameterField(
            key="axis",
            label="Plane Orientation",
            field_type=str,
            default="XY",
            options=(
                ("XY", "XY Plane (Horizontal)"),
                ("XZ", "XZ Plane (Vertical Front)"),
                ("YZ", "YZ Plane (Vertical Side)"),
            ),
            tooltip="Principal Cartesian plane for the surface",
        ),
        ParameterField(
            key="color",
            label="Surface Color",
            field_type=str,
            default="#2ECC71",
            widget_type="color",
            tooltip="Surface color in Hex (e.g. #2ECC71)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


class LineComponentEditor(BaseComponentEditor):
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
            tooltip="Line length along orientation axis",
        ),
        ParameterField(
            key="axis",
            label="Alignment Axis",
            field_type=str,
            default="X",
            options=(("X", "X-Axis"), ("Y", "Y-Axis"), ("Z", "Z-Axis")),
            tooltip="Axis along which the line extends",
        ),
        ParameterField(
            key="color",
            label="Line Color",
            field_type=str,
            default="#E74C3C",
            widget_type="color",
            tooltip="Line color in Hex (e.g. #E74C3C)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


class TriangleComponentEditor(BaseComponentEditor):
    """Property editor for Triangle surface primitive components."""

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
            tooltip="Width of triangle base",
        ),
        ParameterField(
            key="height",
            label="Height",
            unit="mm",
            field_type=float,
            default=150.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Triangle height from base to apex",
        ),
        ParameterField(
            key="color",
            label="Surface Color",
            field_type=str,
            default="#9B59B6",
            widget_type="color",
            tooltip="Surface color in Hex (e.g. #9B59B6)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


class LoftComponentEditor(BaseComponentEditor):
    """Property editor for Loft primitive components."""

    FIELDS = (
        ParameterField(
            key="span",
            label="Span",
            unit="mm",
            field_type=float,
            default=400.0,
            min_value=10.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Total span length",
        ),
        ParameterField(
            key="root_chord",
            label="Root Chord",
            unit="mm",
            field_type=float,
            default=180.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Root airfoil chord length",
        ),
        ParameterField(
            key="tip_chord",
            label="Tip Chord",
            unit="mm",
            field_type=float,
            default=90.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Tip airfoil chord length",
        ),
        ParameterField(
            key="sweep",
            label="Leading-Edge Sweep",
            unit="°",
            field_type=float,
            default=5.0,
            min_value=-45.0,
            max_value=60.0,
            decimals=1,
            tooltip="Quarter-chord or LE sweep angle",
        ),
        ParameterField(
            key="dihedral",
            label="Dihedral Angle",
            unit="°",
            field_type=float,
            default=2.0,
            min_value=-30.0,
            max_value=45.0,
            decimals=1,
            tooltip="Dihedral angle above horizontal plane",
        ),
        ParameterField(
            key="color",
            label="Surface Color",
            field_type=str,
            default="#3498DB",
            widget_type="color",
            tooltip="Surface color in Hex (e.g. #3498DB)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


class PointComponentEditor(BaseComponentEditor):
    """Property editor for Point primitive components."""

    FIELDS = (
        ParameterField(
            key="count",
            label="Point Count",
            field_type=int,
            default=100,
            min_value=1,
            max_value=5000,
            tooltip="Total number of points",
        ),
        ParameterField(
            key="radius",
            label="Distribution Radius",
            unit="mm",
            field_type=float,
            default=150.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Spherical distribution radius",
        ),
        ParameterField(
            key="point_size",
            label="Point Size",
            unit="px",
            field_type=float,
            default=4.0,
            min_value=1.0,
            max_value=32.0,
            decimals=1,
            tooltip="Screen raster point diameter",
        ),
        ParameterField(
            key="color",
            label="Point Color",
            field_type=str,
            default="#E74C3C",
            widget_type="color",
            tooltip="Point color in Hex (e.g. #E74C3C)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


class ArrowComponentEditor(BaseComponentEditor):
    """Property editor for Arrow primitive components."""

    FIELDS = (
        ParameterField(
            key="length",
            label="Arrow Length",
            unit="mm",
            field_type=float,
            default=150.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Length of each arrow shaft",
        ),
        ParameterField(
            key="axis",
            label="Orientation",
            field_type=str,
            default="All",
            options=(
                ("All", "All Axes (XYZ)"),
                ("X", "X-Axis"),
                ("Y", "Y-Axis"),
                ("Z", "Z-Axis"),
            ),
            tooltip="Axis alignment for the arrows",
        ),
        ParameterField(
            key="color",
            label="Arrow Color",
            field_type=str,
            default="#1ABC9C",
            widget_type="color",
            tooltip="Arrow color in Hex (e.g. #1ABC9C)",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


# ----------------------------------------------------------------------
# Component Schema Factory Functions
# ----------------------------------------------------------------------


def create_box_component(comp_id: str, name: str) -> dict[str, Any]:
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_BOX,
        "parent": None,
        "mass": 100.0,
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


def create_cylinder_component(comp_id: str, name: str) -> dict[str, Any]:
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_CYLINDER,
        "parent": None,
        "mass": 80.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
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


def create_ring_component(comp_id: str, name: str) -> dict[str, Any]:
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_RING,
        "parent": None,
        "mass": 20.0,
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
            "inner_radius": 25.0,
            "axis": "Z",
            "color": "#F1C40F",
        },
    }


def create_plane_component(comp_id: str, name: str) -> dict[str, Any]:
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_PLANE,
        "parent": None,
        "mass": 10.0,
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


def create_line_component(comp_id: str, name: str) -> dict[str, Any]:
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
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 200.0, "y": 5.0, "z": 5.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "length": 200.0,
            "axis": "X",
            "color": "#E74C3C",
        },
    }


def create_triangle_component(comp_id: str, name: str) -> dict[str, Any]:
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_TRIANGLE,
        "parent": None,
        "mass": 5.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 150.0, "y": 5.0, "z": 150.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 75.0},
        },
        "parameters": {
            "base_width": 150.0,
            "height": 150.0,
            "color": "#9B59B6",
        },
    }


def create_loft_component(comp_id: str, name: str) -> dict[str, Any]:
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_LOFT,
        "parent": None,
        "mass": 150.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 200.0, "y": 400.0, "z": 40.0},
            "offset_mm": {"x": 50.0, "y": 200.0, "z": 10.0},
        },
        "parameters": {
            "span": 400.0,
            "root_chord": 180.0,
            "tip_chord": 90.0,
            "sweep": 5.0,
            "dihedral": 2.0,
            "color": "#3498DB",
        },
    }


def create_point_component(comp_id: str, name: str) -> dict[str, Any]:
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_POINT,
        "parent": None,
        "mass": 5.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 300.0, "y": 300.0, "z": 300.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "count": 100,
            "radius": 150.0,
            "point_size": 4.0,
            "color": "#E74C3C",
        },
    }


def create_arrow_component(comp_id: str, name: str) -> dict[str, Any]:
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_ARROW,
        "parent": None,
        "mass": 5.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 150.0, "y": 150.0, "z": 150.0},
            "offset_mm": {"x": 75.0, "y": 75.0, "z": 75.0},
        },
        "parameters": {
            "length": 150.0,
            "axis": "All",
            "color": "#1ABC9C",
        },
    }


# ----------------------------------------------------------------------
# Identity & Project Insertion Helpers
# ----------------------------------------------------------------------


def generate_unique_identity(api: StudioAPI, base_id: str, base_name: str) -> tuple[str, str]:
    """Generate a collision-free ID and human-friendly display name."""
    project = api.current_project
    if project is None or not isinstance(project.data.get("components"), list):
        return f"{base_id}-1", f"{base_name} 1"
    existing_ids = {str(c.get("id")) for c in project.data["components"] if isinstance(c, dict)}
    existing_names = {str(c.get("name")) for c in project.data["components"] if isinstance(c, dict)}
    idx = 1
    while f"{base_id}-{idx}" in existing_ids or f"{base_name} {idx}" in existing_names:
        idx += 1
    return f"{base_id}-{idx}", f"{base_name} {idx}"


def add_debug_component(
    api: StudioAPI,
    factory_fn: Callable[[str, str], dict[str, Any]],
    base_id: str,
    base_name: str,
) -> dict[str, Any] | None:
    """Create and append a debug component into the active project with undo support."""
    project = api.current_project
    if project is None:
        window = getattr(api, "_window", None) or getattr(api, "main_window", None)
        if window is not None and hasattr(window, "new_untitled_project"):
            window.new_untitled_project()
            project = api.current_project
    if project is None or project.read_only:
        api.show_status("Cannot add component to read-only project", "warning")
        return None

    comp_id, name = generate_unique_identity(api, base_id, base_name)
    comp = factory_fn(comp_id, name)

    def change() -> None:
        comps = project.data.setdefault("components", [])
        if isinstance(comps, list):
            comps.append(comp)

    api.edit_project(f"Add {name}", change)
    created = next(
        (
            item
            for item in project.data.get("components", [])
            if isinstance(item, dict) and item.get("id") == comp_id
        ),
        comp,
    )
    api.set_selection(created)
    api.show_status(f"Added {name}", "success", 3000)
    return created


def clear_debug_components(api: StudioAPI) -> None:
    """Remove all debug primitive components from the active project."""
    project = api.current_project
    if project is None or project.read_only:
        return
    comps = project.data.get("components", [])
    if not isinstance(comps, list):
        return
    debug_ids = {
        c.get("id")
        for c in comps
        if isinstance(c, dict) and str(c.get("type", "")).startswith("org.setuav.debug:")
    }
    if not debug_ids:
        api.show_status("No debug components to clear", "info", 2000)
        return

    def change() -> None:
        project.data["components"] = [
            c
            for c in comps
            if isinstance(c, dict) and not str(c.get("type", "")).startswith("org.setuav.debug:")
        ]

    count = len(debug_ids)
    api.edit_project("Clear Debug Primitives", change)
    api.set_selection(None)
    api.show_status(f"Removed {count} debug component(s)", "info", 3000)
