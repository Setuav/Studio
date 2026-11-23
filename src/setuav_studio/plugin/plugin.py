"""Lifecycle contract implemented by third-party plugins.

@defgroup lifecycle Plugin lifecycle
@brief Discovery and activation contract for plugin packages.

@details
Setuav Studio discovers installed plugins from the
``setuav_studio.plugins`` Python entry-point group. The entry-point value must
resolve to a plugin class or an already-created plugin object exposing a
stable ``id`` and an ``activate(api)`` method.

At startup the host loads bundled plugins and installed entry points, activates
them in topological dependency order based on ``requires`` (alphabetical by
plugin ID when independent), and isolates failures. A plugin should register
all of its contributions and listeners in ``activate`` and release them in
``deactivate``.

Loading or activation failures are isolated. The host records a
``PluginLoadIssue`` and continues starting the remaining plugins. A duplicate
plugin ID is ignored after the first successful activation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

#: Python package entry-point group scanned by Setuav Studio.
PLUGIN_ENTRY_POINT_GROUP = "setuav_studio.plugins"

__all__ = ["PLUGIN_ENTRY_POINT_GROUP", "StudioPlugin"]


class StudioPlugin(Protocol):
    """Lifecycle contract implemented by every plugin.

    ``id`` must be a stable reverse-domain identifier. An optional ``requires``
    tuple may list plugin IDs that must be active before this plugin activates
    (and cannot be deactivated while this plugin is active). Register
    contributions and listeners in ``activate`` and release them in
    ``deactivate``.

    @ingroup lifecycle
    """

    id: str

    def activate(self, api: StudioAPI) -> None:
        """Register the plugin's contributions and listeners."""
        ...

    def deactivate(self, api: StudioAPI) -> None:
        """Release contributions, listeners, and plugin-owned resources."""
        ...
