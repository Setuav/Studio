"""3D OpenGL Geometry Viewport and Rendering package."""

from .mesh import (
    FACE_COLORED,
    FACE_MONOCHROME,
    FACE_TRANSPARENT,
    WIRE_FEATURE,
    WIRE_FULL,
    build_component_wire_vertices,
    build_loft_solid_vertices,
    build_loft_wire_vertices,
    build_section_ring_vertices,
    hit_test_loft,
)
from .palettes import (
    active_palette,
    control_surface_color,
    palette_names,
    segment_colors,
    set_active_palette,
    wing_color,
)
from .scene import GeometryProvider, build_project_geometry
from .widget import OpenGLViewer

__all__ = [
    "FACE_COLORED",
    "FACE_MONOCHROME",
    "FACE_TRANSPARENT",
    "WIRE_FEATURE",
    "WIRE_FULL",
    "GeometryProvider",
    "OpenGLViewer",
    "active_palette",
    "build_component_wire_vertices",
    "build_loft_solid_vertices",
    "build_loft_wire_vertices",
    "build_project_geometry",
    "build_section_ring_vertices",
    "control_surface_color",
    "hit_test_loft",
    "palette_names",
    "segment_colors",
    "set_active_palette",
    "wing_color",
]
