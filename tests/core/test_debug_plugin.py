"""Tests for DebugPlugin registration and lifecycle."""

from __future__ import annotations

import unittest

from plugins.debug import PLUGIN, DebugPlugin
from setuav_studio.api import PluginManager, StudioAPI
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

        self.manager.deactivate("org.setuav.studio.debug")
        self.assertFalse(self.manager.is_active("org.setuav.studio.debug"))
        self.assertNotIn(plugin, self.manager.active_plugins)
