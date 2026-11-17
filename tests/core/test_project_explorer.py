"""Tests for the layout of the project explorer tree."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QTreeWidgetItem

from setuav_studio.api import StudioAPI
from setuav_studio.project import open_project
from setuav_studio.ui.panels.project_explorer import ProjectExplorer
from setuav_studio.ui.panels.project_explorer.tree_builder import VEHICLE_SELECTION
from setuav_studio.ui.shell.native_registrations import register_native_component_types
from tests._common import TEST_PROJECT_PATH, get_qapp


def _child_texts(item: QTreeWidgetItem) -> list[str]:
    children = [item.child(index) for index in range(item.childCount())]
    return [child.text(0) for child in children if child is not None]


class ProjectExplorerLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        register_native_component_types(self.api)
        self.api._host.set_project(open_project(TEST_PROJECT_PATH))
        self.explorer = ProjectExplorer(self.api)
        self.addCleanup(self.explorer.deleteLater)

    def test_vehicle_and_groups_are_the_top_level(self) -> None:
        items = [
            self.explorer.topLevelItem(index) for index in range(self.explorer.topLevelItemCount())
        ]
        top_level = [item.text(0) for item in items if item is not None]
        self.assertEqual(top_level, ["Vehicle", "Constants"])

    def test_vehicle_lists_components_flat_with_subparts_nested(self) -> None:
        vehicle = self.explorer._item_map[VEHICLE_SELECTION["id"]]
        self.assertEqual(
            _child_texts(vehicle),
            [
                "Fuselage",
                "Main Wing",
                "V-Tail",
                "SunnySky X2814",
                "LiPo Battery",
                "Avionics Point Mass",
                "ESC",
            ],
        )
        wing = self.explorer._item_map["main-wing"]
        self.assertEqual(_child_texts(wing), ["Aileron", "Flap"])

    def test_selecting_the_vehicle_shows_its_summary(self) -> None:
        from setuav_studio.ui.editor import VehicleSummaryEditor
        from setuav_studio.ui.shell.native_registrations import register_native_kind_editors

        register_native_kind_editors(self.api)
        vehicle = self.explorer._item_map[VEHICLE_SELECTION["id"]]
        editor = self.api.create_component_editor(self.explorer._element_map[vehicle])
        self.assertIsInstance(editor, VehicleSummaryEditor)
        assert isinstance(editor, VehicleSummaryEditor)
        self.addCleanup(editor.deleteLater)
        self.assertEqual(editor._property_value(editor.summary_table, "components"), "10")


if __name__ == "__main__":
    unittest.main()
