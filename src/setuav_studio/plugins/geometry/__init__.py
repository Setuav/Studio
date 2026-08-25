"""Geometry Plugin package."""

import sys

from . import editors, engine, viewport
from .plugin import GeometryPlugin
from .workspace import ViewerWorkspace

# Alias sub-modules for backwards-compatible imports
sys.modules["setuav_studio.plugins.geometry.data"] = engine.data
sys.modules["setuav_studio.plugins.geometry.airfoil"] = engine.airfoil
sys.modules["setuav_studio.plugins.geometry.transforms"] = engine.transforms
sys.modules["setuav_studio.plugins.geometry.fuselage_geometry"] = engine.fuselage_geometry
sys.modules["setuav_studio.plugins.geometry.lifting_surface_geometry"] = (
    engine.lifting_surface_geometry
)
sys.modules["setuav_studio.plugins.geometry.wing_driver_solver"] = engine.wing_driver_solver
sys.modules["setuav_studio.plugins.geometry.wing_planform_engine"] = engine.wing_planform_engine
sys.modules["setuav_studio.plugins.geometry.wing_sections_engine"] = engine.wing_sections_engine

sys.modules["setuav_studio.plugins.geometry.widget"] = viewport.widget
sys.modules["setuav_studio.plugins.geometry.scene"] = viewport.scene
sys.modules["setuav_studio.plugins.geometry.mesh"] = viewport.mesh
sys.modules["setuav_studio.plugins.geometry.palettes"] = viewport.palettes

sys.modules["setuav_studio.plugins.geometry.lifting_surface"] = editors.lifting_surface
sys.modules["setuav_studio.plugins.geometry.fuselage"] = editors.fuselage
sys.modules["setuav_studio.plugins.geometry.fuselage_section_dialog"] = (
    editors.fuselage_section_dialog
)
sys.modules["setuav_studio.plugins.geometry.airfoil_dialog"] = editors.airfoil_dialog
sys.modules["setuav_studio.plugins.geometry.control_surface"] = editors.control_surface
sys.modules["setuav_studio.plugins.geometry.wing_driver_table"] = editors.wing_driver_table

PLUGIN = GeometryPlugin()

__all__ = [
    "GeometryPlugin",
    "PLUGIN",
    "ViewerWorkspace",
    "editors",
    "engine",
    "viewport",
]
