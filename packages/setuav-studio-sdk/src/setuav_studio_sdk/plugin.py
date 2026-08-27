"""Lifecycle contract implemented by third-party plugins.

@defgroup lifecycle Plugin lifecycle
@brief Discovery and activation contract for plugin packages.

@details
Setuav Studio discovers installed plugins from the
``setuav_studio.plugins`` Python entry-point group. The entry-point value must
resolve to a plugin class or an already-created plugin object exposing a
stable ``id`` and an ``activate(api)`` method.

At startup the host loads bundled plugins and installed entry points, sorts
them by ascending ``priority`` and then by plugin ID, and activates them in
that order. A plugin should register all of its contributions and listeners in
``activate`` and release them in ``deactivate``.

Loading or activation failures are isolated. The host records a
``PluginLoadIssue`` and continues starting the remaining plugins. A duplicate
plugin ID is ignored after the first successful activation.
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
