"""Tests for GeometryPlugin lifecycle (activate / deactivate)."""

from __future__ import annotations

import unittest

from plugins.geometry import GeometryPlugin
from setuav_studio.api import StudioAPI
from tests._common import get_qapp


class GeometryPluginLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_activate_and_deactivate_lifecycle(self) -> None:
        api = StudioAPI()
        plugin = GeometryPlugin()

        # 1. Activate
        plugin.activate(api)

        # Check toolbar items registered (pending since no host bound yet)
        self.assertEqual(len(api._pending_toolbar_items), 3)
        toolbar_ids = [item.id for item in api._pending_toolbar_items]
        self.assertIn("geometry.create-fuselage", toolbar_ids)
        self.assertIn("geometry.create-lifting-surface", toolbar_ids)
        self.assertIn("geometry.create-control-surface", toolbar_ids)

        # Check component models registered
        self.assertIn("org.setuav.core:lifting-surface", api._component_models)
        self.assertIn("org.setuav.core:fuselage", api._component_models)
        self.assertIn("org.setuav.core:control-surface", api._component_models)

        # Check component editors registered
        self.assertIn("org.setuav.core:lifting-surface", api._component_editors)
        self.assertIn("org.setuav.core:fuselage", api._component_editors)
        self.assertIn("org.setuav.core:control-surface", api._component_editors)
        self.assertIn("org.setuav.core:airframe", api._component_editors)

        # Check component icons registered
        self.assertIn("org.setuav.core:lifting-surface", api._component_icons)
        self.assertIn("org.setuav.core:fuselage", api._component_icons)
        self.assertIn("org.setuav.core:control-surface", api._component_icons)
        self.assertIn("org.setuav.core:airframe", api._component_icons)

        # Check settings page registered
        self.assertIn("geometry.settings.editor", api._settings_pages)

        # 2. Deactivate
        plugin.deactivate(api)

        # Verify all contributions cleaned up
        self.assertEqual(len(api._pending_toolbar_items), 0)
        self.assertNotIn("org.setuav.core:lifting-surface", api._component_models)
        self.assertNotIn("org.setuav.core:fuselage", api._component_models)
        self.assertNotIn("org.setuav.core:control-surface", api._component_models)

        self.assertNotIn("org.setuav.core:lifting-surface", api._component_editors)
        self.assertNotIn("org.setuav.core:fuselage", api._component_editors)
        self.assertNotIn("org.setuav.core:control-surface", api._component_editors)
        self.assertNotIn("org.setuav.core:airframe", api._component_editors)

        self.assertNotIn("org.setuav.core:lifting-surface", api._component_icons)
        self.assertNotIn("org.setuav.core:fuselage", api._component_icons)
        self.assertNotIn("org.setuav.core:control-surface", api._component_icons)
        self.assertNotIn("org.setuav.core:airframe", api._component_icons)

        self.assertNotIn("geometry.settings.editor", api._settings_pages)

    def test_plugin_manager_toggle_geometry_plugin(self) -> None:
        from setuav_studio.plugin.manager import PluginManager

        api = StudioAPI()
        manager = PluginManager(api)
        plugin = GeometryPlugin()

        # Toggle on (this is what Plugin Manager UI does)
        manager.activate(plugin)
        self.assertTrue(manager.is_active(plugin.id))

        # Toggle off
        manager.deactivate(plugin.id)
        self.assertFalse(manager.is_active(plugin.id))

    def test_on_project_opened_syncs_airframe_via_edit_project(self) -> None:
        from pathlib import Path

        from setuav_studio.project import ProjectDocument

        api = StudioAPI()
        plugin = GeometryPlugin()
        plugin.activate(api)

        doc = ProjectDocument(Path("/tmp/test_proj.json"), "json", {"components": []})
        api.current_project = doc

        plugin._on_project_opened()
        # Verify airframe was inserted
        self.assertTrue(any(c.get("id") == "airframe" for c in doc.data["components"]))

        plugin.deactivate(api)

    def test_activate_after_native_registrations(self) -> None:
        from setuav_studio.ui.shell.native_registrations import register_native_contributions

        api = StudioAPI()
        register_native_contributions(api)

        plugin = GeometryPlugin()
        plugin.activate(api)

        # Fuselage model and editor should now be registered
        self.assertIn("org.setuav.core:fuselage", api._component_models)
        self.assertIn("org.setuav.core:fuselage", api._component_editors)

        plugin.deactivate(api)


if __name__ == "__main__":
    unittest.main()
