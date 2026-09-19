"""Tests for DebugPlugin registration, lifecycle, and viewport toolbar tools."""

from __future__ import annotations

import unittest

from plugins.debug import PLUGIN, DebugPlugin
from plugins.debug.plugin import TOOLBAR_ADD_PRIMITIVE_ID
from plugins.debug.primitives_demo import DEBUG_LAYER
from setuav_studio.api import PluginManager, StudioAPI
from setuav_studio.ui.viewport import StudioViewport
from tests._common import get_qapp


class DebugPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.manager = PluginManager(self.api)

    def test_debug_plugin_attributes(self) -> None:
        plugin = DebugPlugin()
        self.assertEqual(plugin.id, "org.setuav.studio.debug")
        self.assertEqual(plugin.name, "Debug")
        self.assertEqual(plugin.version, "0.1.0")
        self.assertTrue(callable(plugin.activate))
        self.assertTrue(callable(plugin.deactivate))

    def test_debug_plugin_package_exports_plugin_instance(self) -> None:
        self.assertIsInstance(PLUGIN, DebugPlugin)
        self.assertEqual(PLUGIN.id, "org.setuav.studio.debug")

    def test_debug_plugin_activation_and_deactivation(self) -> None:
        plugin = DebugPlugin()
        self.manager.activate(plugin)
        self.assertTrue(self.manager.is_active("org.setuav.studio.debug"))
        self.assertIn(plugin, self.manager.active_plugins)

        # Check toolbar item was registered
        pending_ids = [item.id for item in self.api._pending_toolbar_items]
        self.assertIn(TOOLBAR_ADD_PRIMITIVE_ID, pending_ids)

        contribution = next(
            item for item in self.api._pending_toolbar_items if item.id == TOOLBAR_ADD_PRIMITIVE_ID
        )
        self.assertEqual(contribution.group, "debug")
        self.assertEqual(contribution.title, "Add to Viewport")
        self.assertGreater(len(contribution.menu_items), 0)

        # Deactivate
        self.manager.deactivate("org.setuav.studio.debug")
        self.assertFalse(self.manager.is_active("org.setuav.studio.debug"))
        self.assertNotIn(plugin, self.manager.active_plugins)
        pending_ids_after = [item.id for item in self.api._pending_toolbar_items]
        self.assertNotIn(TOOLBAR_ADD_PRIMITIVE_ID, pending_ids_after)

    def test_debug_toolbar_menu_items_populate_viewport(self) -> None:
        viewport = StudioViewport(api=self.api)
        self.assertIs(self.api.viewport, viewport)

        plugin = DebugPlugin()
        self.manager.activate(plugin)

        contribution = next(
            item for item in self.api._pending_toolbar_items if item.id == TOOLBAR_ADD_PRIMITIVE_ID
        )
        menu_items_by_title = {item.title: item for item in contribution.menu_items}

        expected_titles = [
            "Add Box",
            "Add Cylinder",
            "Add Ring (Propeller Disk)",
            "Add Plane",
            "Add Lines (Coordinate Axes)",
            "Add Triangles (Pyramid)",
            "Add Wing Loft",
            "Add Point Cloud",
            "Add Directional Arrows",
            "Add Complete Demo Scene",
            "Clear Debug Primitives",
        ]
        for title in expected_titles:
            self.assertIn(title, menu_items_by_title)

        # Execute each primitive creation callback
        menu_items_by_title["Add Box"].callback()
        self.assertIn("debug.box", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Cylinder"].callback()
        self.assertIn("debug.cylinder", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Ring (Propeller Disk)"].callback()
        self.assertIn("debug.ring", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Plane"].callback()
        self.assertIn("debug.plane", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Lines (Coordinate Axes)"].callback()
        self.assertIn("debug.lines", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Triangles (Pyramid)"].callback()
        self.assertIn("debug.triangles", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Wing Loft"].callback()
        self.assertIn("debug.loft", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Point Cloud"].callback()
        self.assertIn("debug.points", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Directional Arrows"].callback()
        self.assertIn("debug.arrows", viewport.object_ids(layer=DEBUG_LAYER))

        menu_items_by_title["Add Complete Demo Scene"].callback()
        self.assertIn("debug.scene.fuselage", viewport.object_ids(layer=DEBUG_LAYER))
        self.assertIn("debug.scene.wing_right", viewport.object_ids(layer=DEBUG_LAYER))

        # Clear primitives
        menu_items_by_title["Clear Debug Primitives"].callback()
        self.assertEqual(viewport.object_ids(layer=DEBUG_LAYER), [])

        # Deactivate cleans up
        self.manager.deactivate("org.setuav.studio.debug")
