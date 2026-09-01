"""Reusable 2D projection engine for geometry and analysis plugins."""

from .canvas import View2DCanvas
from .geometry import View2DGeometrySource
from .plugin import View2DPlugin
from .scene import View2DMarker, View2DPath, View2DScene

PLUGIN = View2DPlugin()

__all__ = [
    "PLUGIN",
    "View2DCanvas",
    "View2DGeometrySource",
    "View2DMarker",
    "View2DPath",
    "View2DPlugin",
    "View2DScene",
]
