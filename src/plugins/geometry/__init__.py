"""Airframe Design Plugin package."""

from . import editors, engine
from .plugin import AirframeDesignPlugin
from .scene_controller import AirframeSceneController

PLUGIN = AirframeDesignPlugin()


def get_geometry(project: object = None) -> object:
    """Return geometry data for *project*, or the current project if omitted.

    Returns an empty GeometryData when the geometry plugin is inactive or no
    project is open.  Safe to call from other plugins via an optional import::

        try:
            from plugins.geometry import get_geometry
        except ImportError:
            get_geometry = None
    """
    return PLUGIN.get_geometry(project)


__all__ = [
    "PLUGIN",
    "AirframeDesignPlugin",
    "AirframeSceneController",
    "editors",
    "engine",
    "get_geometry",
]
