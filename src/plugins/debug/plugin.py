"""Debug Plugin for Setuav Studio."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

logger = logging.getLogger(__name__)


class DebugPlugin:
    """Plugin for debugging and end-to-end verification of Setuav Studio core features."""

    id = "org.setuav.studio.debug"
    name = "Debug"
    version = "0.1.0"
    priority = 100

    def __init__(self) -> None:
        self._api: StudioAPI | None = None

    def activate(self, api: StudioAPI) -> None:
        """Activate the debug plugin."""
        self._api = api
        logger.info("DebugPlugin activated")

    def deactivate(self, api: StudioAPI) -> None:
        """Deactivate the debug plugin."""
        logger.info("DebugPlugin deactivated")
        self._api = None
