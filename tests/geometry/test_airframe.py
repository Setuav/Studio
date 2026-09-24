"""Unit tests for the fixed Airframe root component and editor."""

from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import Qt

from plugins.geometry.creation import ensure_airframe_component
from plugins.geometry.editors.airframe import AirframeEditor
from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.panels.project_explorer.operations import ProjectExplorerOperations
from setuav_studio.ui.panels.project_explorer.tree import ProjectExplorer
from setuav_studio.ui.panels.project_explorer.tree_builder import ProjectTreeBuilder
from tests._common import get_qapp


class AirframeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.project_data = {
            "name": "Test UAV",
            "components": [
                {
                    "id": "fuse-1",
                    "name": "Main Fuselage",
                    "type": "org.setuav.core:fuselage",
                    "mass": 350.0,
                    "parent": None,
                    "envelope": {"size_mm": {"x": 800.0, "y": 100.0, "z": 100.0}},
                    "parameters": {},
                },
                {
                    "id": "wing-1",
                    "name": "Main Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "mass": 250.0,
                    "parent": None,
                    "attach_to": "fuse-1",
                    "parameters": {
                        "geometry": {
                            "mirror": True,
                            "profiles": [
                                {"position": {"y": 0.0}, "chord": 200.0},
                                {"position": {"y": 600.0}, "chord": 120.0},
                            ],
                        }
                    },
                },
                {
                    "id": "aileron-1",
                    "name": "Aileron",
                    "type": "org.setuav.core:control-surface",
                    "mass": 25.0,
                    "parent": "wing-1",
                    "attach_to": "wing-1",
                    "parameters": {},
                },
            ],
            "assemblies": [
                {
                    "id": "old-struct",
                    "name": "Old Structure",
                    "type": "org.setuav.core:structural-system",
                    "members": {"fuselage": "fuse-1", "wings": ["wing-1"]},
                }
            ],
        }
        self.project = ProjectDocument(
            Path("test_airframe.json"),
            "json",
            self.project_data,
        )
        self.api._host.set_project(self.project)

    def test_ensure_airframe_component_creates_and_reparents(self) -> None:
        airframe = ensure_airframe_component(self.project)
        self.assertEqual(airframe["id"], "airframe")
        self.assertEqual(airframe["name"], "Airframe")
        self.assertEqual(airframe["type"], "org.setuav.core:airframe")
        self.assertIsNone(airframe["parent"])

        # Check that airframe is at index 0
        components = self.project.data["components"]
        self.assertIs(components[0], airframe)

        # Fuselage and wing should now have parent="airframe"
        fuse = next(c for c in components if c["id"] == "fuse-1")
        self.assertEqual(fuse["parent"], "airframe")

        wing = next(c for c in components if c["id"] == "wing-1")
        self.assertEqual(wing["parent"], "airframe")
        # attach_to must be preserved
        self.assertEqual(wing["attach_to"], "fuse-1")

        # Control surface parent must remain wing-1
        aileron = next(c for c in components if c["id"] == "aileron-1")
        self.assertEqual(aileron["parent"], "wing-1")

        # Obsolete structural system assembly should be purged
        assemblies = self.project.data.get("assemblies", [])
        self.assertEqual(len(assemblies), 0)

    def test_airframe_editor_metrics_and_hierarchy(self) -> None:
        ensure_airframe_component(self.project)
        airframe = self.project.data["components"][0]
        editor = AirframeEditor(self.api, airframe)

        # General table
        self.assertEqual(editor._property_text(editor.general_table, 0), "Airframe")
        self.assertEqual(
            editor._property_text(editor.general_table, 1),
            "org.setuav.core:airframe",
        )
        self.assertEqual(
            editor._property_text(editor.general_table, 2),
            "Fixed Root Component (Read-Only)",
        )

        # Hierarchy table
        self.assertIn("1 (Main Fuselage)", editor._property_text(editor.structure_table, 0))
        self.assertIn("1 (Main Wing)", editor._property_text(editor.structure_table, 1))
        self.assertIn("1 (Aileron)", editor._property_text(editor.structure_table, 2))

        # Metrics table
        # Max span = 600 * 2 = 1200 mm -> 1.200 m
        self.assertEqual(editor._property_text(editor.metrics_table, 0), "1.200 m")
        # Fuselage length = 800 mm -> 0.800 m
        self.assertEqual(editor._property_text(editor.metrics_table, 1), "0.800 m")

    def test_airframe_has_no_transform_or_mass_tree_nodes(self) -> None:
        from setuav_studio.ui.shell.native_registrations import register_native_contributions

        register_native_contributions(self.api)
        ensure_airframe_component(self.project)
        airframe = self.project.data["components"][0]
        nodes = list(self.api.component_tree_nodes(airframe))
        self.assertEqual(len(nodes), 0)

    def test_airframe_deletion_and_rename_protection(self) -> None:
        ensure_airframe_component(self.project)
        tree = ProjectExplorer(self.api)
        ops = ProjectExplorerOperations(tree, self.api)
        builder = ProjectTreeBuilder(tree, self.api)
        builder.rebuild_project(self.project)

        airframe_comp = self.project.data["components"][0]

        # 1. Attempt to delete airframe via operations
        ops.delete_component_item(airframe_comp)
        self.assertIn(airframe_comp, self.project.data["components"])

        # 2. Attempt to rename airframe via operations
        item = tree._item_map.get("airframe")
        self.assertIsNotNone(item)
        assert item is not None
        item.setText(0, "Renamed Airframe")
        ops.rename_item(item, 0)
        self.assertEqual(airframe_comp["name"], "Airframe")

        # 3. Tree item must not have ItemIsEditable flag
        self.assertFalse(bool(item.flags() & Qt.ItemFlag.ItemIsEditable))


if __name__ == "__main__":
    unittest.main()
