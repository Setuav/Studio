"""Viewport mesh, tessellation, and spatial query facade.

This module re-exports mesh builders, raycasting hit-tests, and envelope utilities
from their modular implementations (raycast, primitives_mesh, loft_mesh, envelope_mesh).
"""

from __future__ import annotations

from .constants import (
    FACE_COLORED,
    FACE_MONOCHROME,
    FACE_TRANSPARENT,
    WIRE_FEATURE,
    WIRE_FULL,
)
from .envelope_mesh import (
    ENVELOPE_HIGHLIGHT,
    build_envelope_wire_vertices,
)
from .loft_mesh import (
    AIRFOIL_CHORD_HIGHLIGHT,
    AIRFOIL_HIGHLIGHT,
    CS_HIGHLIGHT,
    FEATURE_EDGE_COLOR,
    HOVERED_WIRE,
    SECTION_RING,
    SELECTED_WIRE,
    build_component_wire_vertices,
    build_loft_solid_vertices,
    build_loft_wire_vertices,
    build_section_ring_vertices,
)
from .primitives_mesh import (
    build_primitive_annotation_vertices,
    build_primitive_highlight_vertices,
    build_primitive_solid_vertices,
    build_primitive_wire_vertices,
)
from .raycast import (
    hit_test_loft,
    hit_test_scene,
)

__all__ = [
    "AIRFOIL_CHORD_HIGHLIGHT",
    "AIRFOIL_HIGHLIGHT",
    "CS_HIGHLIGHT",
    "ENVELOPE_HIGHLIGHT",
    "FACE_COLORED",
    "FACE_MONOCHROME",
    "FACE_TRANSPARENT",
    "FEATURE_EDGE_COLOR",
    "HOVERED_WIRE",
    "SECTION_RING",
    "SELECTED_WIRE",
    "WIRE_FEATURE",
    "WIRE_FULL",
    "build_component_wire_vertices",
    "build_envelope_wire_vertices",
    "build_loft_solid_vertices",
    "build_loft_wire_vertices",
    "build_primitive_annotation_vertices",
    "build_primitive_highlight_vertices",
    "build_primitive_solid_vertices",
    "build_primitive_wire_vertices",
    "build_section_ring_vertices",
    "hit_test_loft",
    "hit_test_scene",
]
