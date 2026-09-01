"""Geometry Plugin package."""

import sys

from . import editors, engine, viewport
from .plugin import GeometryPlugin
from .workspace import ViewerWorkspace

# Alias sub-modules for backwards-compatible imports
sys.modules["plugins.geometry.data"] = engine.data
sys.modules["plugins.geometry.airfoil"] = engine.airfoil
sys.modules["plugins.geometry.transforms"] = engine.transforms
sys.modules["plugins.geometry.fuselage_geometry"] = engine.fuselage_geometry
sys.modules["plugins.geometry.lifting_surface_geometry"] = (
    engine.lifting_surface_geometry
)
sys.modules["plugins.geometry.wing_driver_solver"] = engine.wing_driver_solver
sys.modules["plugins.geometry.wing_planform_engine"] = engine.wing_planform_engine
sys.modules["plugins.geometry.wing_sections_engine"] = engine.wing_sections_engine

sys.modules["plugins.geometry.widget"] = viewport.widget
sys.modules["plugins.geometry.scene"] = viewport.scene
sys.modules["plugins.geometry.mesh"] = viewport.mesh
sys.modules["plugins.geometry.palettes"] = viewport.palettes

sys.modules["plugins.geometry.lifting_surface"] = editors.lifting_surface
sys.modules["plugins.geometry.fuselage"] = editors.fuselage
sys.modules["plugins.geometry.fuselage_section_dialog"] = (
    editors.fuselage_section_dialog
)
sys.modules["plugins.geometry.airfoil_dialog"] = editors.airfoil_dialog
sys.modules["plugins.geometry.control_surface"] = editors.control_surface
sys.modules["plugins.geometry.wing_driver_table"] = editors.wing_driver_table

PLUGIN = GeometryPlugin()

__all__ = [
    "PLUGIN",
    "GeometryPlugin",
    "ViewerWorkspace",
    "editors",
    "engine",
    "viewport",
]
