"""Tests for the layout of the project explorer tree."""

from __future__ import annotations

import unittest
from typing import Any

from PySide6.QtWidgets import QMenu, QTreeWidgetItem

from setuav_studio.api import ComponentMenuItemContribution, StudioAPI
from setuav_studio.project import open_project
from setuav_studio.ui.panels.project_explorer import ProjectExplorer
from setuav_studio.ui.panels.project_explorer.tree_builder import VEHICLE_SELECTION
from tests._common import TEST_PROJECT_PATH, get_qapp, register_fixture_component_types


def _child_texts(item: QTreeWidgetItem) -> list[str]:
    children = [item.child(index) for index in range(item.childCount())]
    return [child.text(0) for child in children if child is not None]


class ProjectExplorerLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        register_fixture_component_types(self.api)
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


class ProjectExplorerComponentMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        register_fixture_component_types(self.api)
        self.api._host.set_project(open_project(TEST_PROJECT_PATH))
        self.explorer = ProjectExplorer(self.api)
        self.addCleanup(self.explorer.deleteLater)
        self.chosen: list[str] = []
        self.api.register_component_menu_provider("org.test.menu", self._menu_items)

    def _menu_items(self, component: dict[str, Any]) -> tuple[ComponentMenuItemContribution, ...]:
        if component["id"] != "main-wing":
            return ()
        return (
            ComponentMenuItemContribution(
                title="Add Feature",
                children=(
                    ComponentMenuItemContribution(
                        title="Spar", callback=lambda: self.chosen.append("spar")
                    ),
                    ComponentMenuItemContribution(
                        title="Joint", callback=lambda: None, enabled=False
                    ),
                ),
            ),
        )

    def _menu(self, component_id: str) -> QMenu:
        item = self.explorer._item_map[component_id]
        menu = self.explorer._context_menu.default_context_menu(item, can_edit=True)
        self.addCleanup(menu.deleteLater)
        return menu

    def test_contributed_commands_precede_rename_and_delete(self) -> None:
        menu = self._menu("main-wing")
        actions = menu.actions()
        self.assertEqual(
            [action.text() for action in actions], ["Add Feature", "", "Rename", "Delete"]
        )
        submenu = actions[0].menu()
        assert isinstance(submenu, QMenu)
        spar, joint = submenu.actions()
        self.assertEqual((spar.text(), joint.text()), ("Spar", "Joint"))
        self.assertTrue(spar.isEnabled())
        self.assertFalse(joint.isEnabled())
        spar.trigger()
        self.assertEqual(self.chosen, ["spar"])

    def test_components_without_contributions_show_only_rename_and_delete(self) -> None:
        menu = self._menu("fuselage")
        self.assertEqual([action.text() for action in menu.actions()], ["Rename", "Delete"])

    def test_delete_removes_the_component_with_its_subparts_in_one_edit(self) -> None:
        removed: list[frozenset[str]] = []
        self.api.register_component_removal_handler(
            "org.test.removal", lambda _data, ids: removed.append(ids)
        )
        self.explorer._ops.confirm_delete = lambda *_args, **_kwargs: True
        delete = self._menu("main-wing").actions()[-1]
        delete.trigger()

        self.assertEqual(removed, [frozenset({"main-wing", "aileron", "main-wing-flap"})])
        project = self.api.project
        assert project is not None
        self.assertIsNone(project.get_component("main-wing"))
        self.assertEqual(self.api.undo_count, 1)
        self.api.undo()
        self.assertIsNotNone(project.get_component("main-wing"))
        self.assertIsNotNone(project.get_component("aileron"))


if __name__ == "__main__":
    unittest.main()


def test_component_type_label_comes_from_the_type_contribution() -> None:
    from setuav_studio.api import ComponentTypeContribution
    from setuav_studio.ui.panels.project_explorer.style import format_component_type

    api = StudioAPI()
    api.register_component_type(
        ComponentTypeContribution(
            id="org.test:surface",
            name="Surface",
            describe=lambda component: f"Surface ({component['parameters']['kind']})",
        )
    )
    api.register_component_type(ComponentTypeContribution(id="org.test:box", name="Box"))
    surface = {"id": "s", "type": "org.test:surface", "parameters": {"kind": "flap"}}
    box = {"id": "b", "type": "org.test:box", "parameters": {}}

    assert format_component_type(surface, [surface, box], api) == "Surface (flap)"
    assert format_component_type(box, [surface, box], api) == "Box"
