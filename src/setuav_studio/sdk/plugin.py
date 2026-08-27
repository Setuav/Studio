"""Lifecycle contract implemented by third-party plugins.

@defgroup lifecycle Plugin lifecycle
@brief Discovery and activation contract for plugin packages.
"""

from typing import Protocol

from .api import StudioAPI

#: Python package entry-point group scanned by Setuav Studio.
PLUGIN_ENTRY_POINT_GROUP = "setuav_studio.plugins"

__all__ = ["PLUGIN_ENTRY_POINT_GROUP", "StudioPlugin"]


class StudioPlugin(Protocol):
    """Lifecycle contract implemented by every plugin.

    ``id`` must be a stable reverse-domain identifier. Lower ``priority``
    values activate first. Register contributions and listeners in
    ``activate`` and release them in ``deactivate``.

    @ingroup lifecycle
    """

    id: str
    priority: int

    def activate(self, api: StudioAPI) -> None:
        """Register the plugin's contributions and listeners."""
        ...

    def deactivate(self, api: StudioAPI) -> None:
        """Release contributions, listeners, and plugin-owned resources."""
        ...
