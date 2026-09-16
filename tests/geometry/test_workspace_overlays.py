"""Tests for ViewerWorkspace overlay layer workspace filtering."""

from __future__ import annotations

import unittest

from plugins.geometry.workspace import ViewerWorkspace
from setuav_studio.api import StudioAPI
from setuav_studio_sdk.primitives import LineSegmentsPrimitive
from tests._common import get_qapp


class TestWorkspaceOverlays(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.api.current_workspace_id = "studio.workspace.design"
        self.workspace = ViewerWorkspace(self.api)
        self.addCleanup(self.workspace.deleteLater)

    def test_manufacturing_overlay_only_visible_in_manufacturing_workspace(self) -> None:
        dummy_prim = LineSegmentsPrimitive(lines=[((0, 0, 0), (1, 1, 1))], color=(1, 0, 0, 1))

        # 1. In Design workspace, manufacturing overlay should NOT appear in viewer
        self.api.publish(
            "studio.viewer.set_overlays",
            {
                "layer": "manufacturing",
                "primitives": [dummy_prim],
            },
        )
        self.assertNotIn("manufacturing", self.workspace.viewer._overlay_layers)

        # 2. Switch to Manufacturing workspace -> overlay should appear
        self.api.switch_workspace("com.setuav.manufacturing.workspace")
        self.assertIn("manufacturing", self.workspace.viewer._overlay_layers)
        self.assertEqual(len(self.workspace.viewer._overlay_layers["manufacturing"]), 1)

        # 3. Switch back to Design workspace -> overlay should be removed
        self.api.switch_workspace("studio.workspace.design")
        self.assertNotIn("manufacturing", self.workspace.viewer._overlay_layers)

    def test_custom_workspace_scoped_overlay(self) -> None:
        dummy_prim = LineSegmentsPrimitive(lines=[((0, 0, 0), (2, 2, 2))], color=(0, 1, 0, 1))

        self.api.publish(
            "studio.viewer.set_overlays",
            {
                "layer": "aero_lines",
                "workspace": "aerodynamics.workspace",
                "primitives": [dummy_prim],
            },
        )
        # Not in aerodynamics workspace
        self.assertNotIn("aero_lines", self.workspace.viewer._overlay_layers)

        # Switch to aerodynamics workspace
        self.api.switch_workspace("aerodynamics.workspace")
        self.assertIn("aero_lines", self.workspace.viewer._overlay_layers)

        # Switch away
        self.api.switch_workspace("studio.workspace.design")
        self.assertNotIn("aero_lines", self.workspace.viewer._overlay_layers)

    def test_unscoped_overlay_visible_in_all_workspaces(self) -> None:
        dummy_prim = LineSegmentsPrimitive(lines=[((0, 0, 0), (3, 3, 3))], color=(0, 0, 1, 1))

        self.api.publish(
            "studio.viewer.set_overlays",
            {
                "layer": "global_helpers",
                "primitives": [dummy_prim],
            },
        )
        self.assertIn("global_helpers", self.workspace.viewer._overlay_layers)

        self.api.switch_workspace("com.setuav.manufacturing.workspace")
        self.assertIn("global_helpers", self.workspace.viewer._overlay_layers)

        self.api.switch_workspace("studio.workspace.design")
        self.assertIn("global_helpers", self.workspace.viewer._overlay_layers)

    def test_clear_overlays(self) -> None:
        dummy_prim = LineSegmentsPrimitive(lines=[((0, 0, 0), (1, 1, 1))], color=(1, 1, 0, 1))

        self.api.switch_workspace("com.setuav.manufacturing.workspace")
        self.api.publish(
            "studio.viewer.set_overlays",
            {
                "layer": "manufacturing",
                "primitives": [dummy_prim],
            },
        )
        self.assertIn("manufacturing", self.workspace.viewer._overlay_layers)

        # Clear specific layer
        self.api.publish("studio.viewer.clear_overlays", {"layer": "manufacturing"})
        self.assertNotIn("manufacturing", self.workspace.viewer._overlay_layers)


if __name__ == "__main__":
    unittest.main()
