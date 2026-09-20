"""Debug primitive components package: definitions, editors, and 3D scene renderers."""

from __future__ import annotations

from .arrow import (
    TYPE_DEBUG_ARROW,
    ArrowComponentEditor,
    add_arrow_to_viewport,
    create_arrow_component,
    render_arrow,
)
from .box import (
    TYPE_DEBUG_BOX,
    BoxComponentEditor,
    add_box_to_viewport,
    create_box_component,
    render_box,
)
from .common import (
    DEBUG_LAYER,
    BaseDebugComponentEditor,
    add_debug_component,
    clear_debug_components,
    generate_unique_identity,
    parse_color_rgba,
    render_debug_component,
    resolve_world_transform,
    rotate_vector,
    sync_debug_components_to_viewport,
    update_component_in_viewport,
)
from .cylinder import (
    TYPE_DEBUG_CYLINDER,
    CylinderComponentEditor,
    add_cylinder_to_viewport,
    create_cylinder_component,
    render_cylinder,
)
from .line import (
    TYPE_DEBUG_LINE,
    LineComponentEditor,
    add_line_to_viewport,
    create_line_component,
    render_line,
)
from .loft import (
    TYPE_DEBUG_LOFT,
    LoftComponentEditor,
    add_loft_to_viewport,
    create_loft_component,
    naca_airfoil_loop,
    render_loft,
)
from .plane import (
    TYPE_DEBUG_PLANE,
    PlaneComponentEditor,
    add_plane_to_viewport,
    create_plane_component,
    render_plane,
)
from .point import (
    TYPE_DEBUG_POINT,
    PointComponentEditor,
    add_point_to_viewport,
    create_point_component,
    render_point,
)
from .ring import (
    TYPE_DEBUG_RING,
    RingComponentEditor,
    add_ring_to_viewport,
    create_ring_component,
    render_ring,
)
from .triangle import (
    TYPE_DEBUG_TRIANGLE,
    TriangleComponentEditor,
    add_triangle_to_viewport,
    create_triangle_component,
    render_triangle,
)

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

__all__ = [
    "ALL_DEBUG_TYPES",
    "DEBUG_LAYER",
    "TYPE_DEBUG_ARROW",
    "TYPE_DEBUG_BOX",
    "TYPE_DEBUG_CYLINDER",
    "TYPE_DEBUG_LINE",
    "TYPE_DEBUG_LOFT",
    "TYPE_DEBUG_PLANE",
    "TYPE_DEBUG_POINT",
    "TYPE_DEBUG_RING",
    "TYPE_DEBUG_TRIANGLE",
    "ArrowComponentEditor",
    "BaseDebugComponentEditor",
    "BoxComponentEditor",
    "CylinderComponentEditor",
    "LineComponentEditor",
    "LoftComponentEditor",
    "PlaneComponentEditor",
    "PointComponentEditor",
    "RingComponentEditor",
    "TriangleComponentEditor",
    "add_arrow_to_viewport",
    "add_box_to_viewport",
    "add_cylinder_to_viewport",
    "add_debug_component",
    "add_line_to_viewport",
    "add_loft_to_viewport",
    "add_plane_to_viewport",
    "add_point_to_viewport",
    "add_ring_to_viewport",
    "add_triangle_to_viewport",
    "clear_debug_components",
    "create_arrow_component",
    "create_box_component",
    "create_cylinder_component",
    "create_line_component",
    "create_loft_component",
    "create_plane_component",
    "create_point_component",
    "create_ring_component",
    "create_triangle_component",
    "generate_unique_identity",
    "naca_airfoil_loop",
    "parse_color_rgba",
    "render_arrow",
    "render_box",
    "render_cylinder",
    "render_debug_component",
    "render_line",
    "render_loft",
    "render_plane",
    "render_point",
    "render_ring",
    "render_triangle",
    "resolve_world_transform",
    "rotate_vector",
    "sync_debug_components_to_viewport",
    "update_component_in_viewport",
]
