"""Plugin lifecycle contracts exposed to third-party packages."""

from setuav_studio.plugin_system import StudioPlugin

#: Python package entry-point group scanned by Setuav Studio.
PLUGIN_ENTRY_POINT_GROUP = "setuav_studio.plugins"

__all__ = ["PLUGIN_ENTRY_POINT_GROUP", "StudioPlugin"]
