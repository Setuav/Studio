"""Debug Plugin for Setuav Studio."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from setuav_studio_sdk import (
    ToolbarContribution,
    ToolbarMenuItemContribution,
)

from .primitives_demo import (
    add_debug_arrows,
    add_debug_box,
    add_debug_cylinder,
    add_debug_lines,
    add_debug_loft,
    add_debug_plane,
    add_debug_points,
    add_debug_ring,
    add_debug_scene,
    add_debug_triangles,
    clear_debug_objects,
)

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

logger = logging.getLogger(__name__)

TOOLBAR_ADD_PRIMITIVE_ID = "debug.toolbar.add_primitive"


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
        self._register_toolbar_tools(api)
        logger.info("DebugPlugin activated")

    def deactivate(self, api: StudioAPI) -> None:
        """Deactivate the debug plugin."""
        api.remove_toolbar_item(TOOLBAR_ADD_PRIMITIVE_ID)
        vp = self._get_viewport()
        if vp is not None:
            clear_debug_objects(vp)
        self._api = None
        logger.info("DebugPlugin deactivated")

    # ------------------------------------------------------------------
    # Viewport & Toolbar Helpers
    # ------------------------------------------------------------------

    def _get_viewport(self) -> Any | None:
        """Get the StudioViewport instance, showing the panel if necessary."""
        if self._api is None:
            return None
        vp = self._api.viewport
        if vp is None:
            self._api.show_panel("studio.viewer.opengl")
            vp = self._api.viewport
        return vp

    def _run_add_primitive(self, name: str, builder: Callable[[Any], None]) -> None:
        """Run a primitive builder on the active viewport."""
        vp = self._get_viewport()
        if vp is None:
            if self._api is not None:
                self._api.show_status("3D Viewport is not available", level="warning")
            return
        builder(vp)
        if self._api is not None:
            self._api.show_status(f"Added {name} to 3D Viewport", level="info")

    def _run_clear_primitives(self) -> None:
        """Clear all debug primitives from the active viewport."""
        vp = self._get_viewport()
        if vp is not None:
            clear_debug_objects(vp)
            if self._api is not None:
                self._api.show_status("Cleared debug primitives from 3D Viewport", level="info")

    def _register_toolbar_tools(self, api: StudioAPI) -> None:
        """Register debug tools to the toolbar."""
        menu_items = (
            ToolbarMenuItemContribution(
                title="Add Box",
                callback=lambda: self._run_add_primitive("Box", add_debug_box),
                icon="fa6s.cube",
            ),
            ToolbarMenuItemContribution(
                title="Add Cylinder",
                callback=lambda: self._run_add_primitive("Cylinder", add_debug_cylinder),
                icon="fa6s.database",
            ),
            ToolbarMenuItemContribution(
                title="Add Ring (Propeller Disk)",
                callback=lambda: self._run_add_primitive("Ring", add_debug_ring),
                icon="fa6s.circle-notch",
            ),
            ToolbarMenuItemContribution(
                title="Add Plane",
                callback=lambda: self._run_add_primitive("Plane", add_debug_plane),
                icon="fa6s.square",
            ),
            ToolbarMenuItemContribution(
                title="Add Lines (Coordinate Axes)",
                callback=lambda: self._run_add_primitive("Lines", add_debug_lines),
                icon="fa6s.arrows-up-down-left-right",
            ),
            ToolbarMenuItemContribution(
                title="Add Triangles (Pyramid)",
                callback=lambda: self._run_add_primitive("Triangles", add_debug_triangles),
                icon="fa6s.draw-polygon",
            ),
            ToolbarMenuItemContribution(
                title="Add Wing Loft",
                callback=lambda: self._run_add_primitive("Wing Loft", add_debug_loft),
                icon="fa6s.plane",
            ),
            ToolbarMenuItemContribution(
                title="Add Point Cloud",
                callback=lambda: self._run_add_primitive("Point Cloud", add_debug_points),
                icon="mdi6.dots-hexagon",
            ),
            ToolbarMenuItemContribution(
                title="Add Directional Arrows",
                callback=lambda: self._run_add_primitive("Arrows", add_debug_arrows),
                icon="fa6s.location-arrow",
            ),
            ToolbarMenuItemContribution(
                title="Add Complete Demo Scene",
                callback=lambda: self._run_add_primitive("Demo Scene", add_debug_scene),
                icon="fa6s.cubes",
            ),
            ToolbarMenuItemContribution(
                title="Clear Debug Primitives",
                callback=self._run_clear_primitives,
                icon="fa6s.trash-can",
            ),
        )

        contribution = ToolbarContribution(
            id=TOOLBAR_ADD_PRIMITIVE_ID,
            title="Add to Viewport",
            icon="fa6s.cube",
            menu_items=menu_items,
            group="debug",
            order=10,
        )
        api.add_toolbar_item(contribution)
