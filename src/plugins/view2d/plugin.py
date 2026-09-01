"""Shared 2D projection and geometry-view plugin."""

from __future__ import annotations

from typing import ClassVar

from setuav_studio_sdk import StudioAPI


class View2DPlugin:
    """Provide the reusable 2D scene/canvas runtime to other plugins."""

    id = "org.setuav.studio.view2d"
    priority = 50
    provides: ClassVar[dict[str, str]] = {"org.setuav.studio.view2d": "1.0.0"}

    def activate(self, api: StudioAPI) -> None:
        self._api = api

    def deactivate(self, api: StudioAPI) -> None:
        self._api = None
