"""Core 3D viewport widget, OpenGL renderer, and public API for plugins."""

from __future__ import annotations

from setuav_studio.ui.viewport.constants import (
    FACE_COLORED,
    FACE_MONOCHROME,
    FACE_TRANSPARENT,
    VIEW_PRESETS,
    WIRE_FEATURE,
    WIRE_FULL,
)
from setuav_studio.ui.viewport.hud import StudioViewportHUD
from setuav_studio.ui.viewport.layer import Layer
from setuav_studio.ui.viewport.primitives import (
    BoxPrimitive,
    ColorRGB,
    ColorRGBA,
    CylinderPrimitive,
    LineSegmentsPrimitive,
    LoftPrimitive,
    PlanePrimitive,
    Point3D,
    RingPrimitive,
    TrianglesPrimitive,
    VisualPrimitive,
)
from setuav_studio.ui.viewport.scene_object import SceneObject
from setuav_studio.ui.viewport.types import (
    EnvelopeWireGeometry,
    GeometryData,
    LoftGeometry,
    Section,
)
from setuav_studio.ui.viewport.viewport import StudioViewport
from setuav_studio.ui.viewport.widget import OpenGLViewer

__all__ = [
    "FACE_COLORED",
    "FACE_MONOCHROME",
    "FACE_TRANSPARENT",
    "VIEW_PRESETS",
    "WIRE_FEATURE",
    "WIRE_FULL",
    "BoxPrimitive",
    "ColorRGB",
    "ColorRGBA",
    "CylinderPrimitive",
    "EnvelopeWireGeometry",
    "GeometryData",
    "Layer",
    "LineSegmentsPrimitive",
    "LoftGeometry",
    "LoftPrimitive",
    "OpenGLViewer",
    "PlanePrimitive",
    "Point3D",
    "RingPrimitive",
    "SceneObject",
    "Section",
    "StudioViewport",
    "StudioViewportHUD",
    "TrianglesPrimitive",
    "ViewportProtocol",
    "VisualPrimitive",
]

ViewportProtocol = StudioViewport
