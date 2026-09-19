"""Tests for DebugPlugin registration, component creation, editors, icons, and viewport sync."""

from __future__ import annotations

import unittest
from pathlib import Path

from plugins.debug import PLUGIN, DebugPlugin
from plugins.debug.components import (
    TYPE_DEBUG_BOX,
    TYPE_DEBUG_CYLINDER,
    BoxComponentEditor,
)
from plugins.debug.plugin import TOOLBAR_ADD_PRIMITIVE_ID
from plugins.debug.scene_sync import DEBUG_LAYER
from setuav_studio.api import PluginManager, StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.viewport import StudioViewport
from tests._common import get_qapp
from tests.core.test_viewport import MockRenderer


class DebugPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.manager = PluginManager(self.api)
        self.project = ProjectDocument(
            path=Path("test_project.suav"),
            kind="archive",
            data={
                "name": "Test Project",
                "plugins": [],
                "components": [],
                "assemblies": [],
                "parameters": {},
                "extensions": {},
            },
        )
        self.api._host.set_project(self.project)

    def tearDown(self) -> None:
        self._app.processEvents()

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
        self.assertEqual(contribution.title, "Primitives")
        self.assertGreater(len(contribution.menu_items), 0)

        # Check component editor registration
        sample_box = {
            "kind": "component",
            "id": "box-1",
            "name": "Box 1",
            "type": TYPE_DEBUG_BOX,
            "parameters": {"length": 200.0, "width": 150.0, "height": 100.0, "color": "#4A90E2"},
        }
        editor = self.api.create_component_editor(sample_box)
        self.assertIsInstance(editor, BoxComponentEditor)
        if editor is not None:
            editor.deleteLater()

        # Check component icon registration
        icon = self.api.get_component_icon(sample_box)
        self.assertFalse(icon.isNull())

        # Deactivate cleans up
        self.manager.deactivate("org.setuav.studio.debug")
        self.assertFalse(self.manager.is_active("org.setuav.studio.debug"))
        self.assertNotIn(plugin, self.manager.active_plugins)
        pending_ids_after = [item.id for item in self.api._pending_toolbar_items]
        self.assertNotIn(TOOLBAR_ADD_PRIMITIVE_ID, pending_ids_after)
        self.assertIsNone(self.api.create_component_editor(sample_box))
        self._app.processEvents()

    def test_debug_toolbar_creates_project_components_and_syncs_viewport(self) -> None:
        viewport = StudioViewport(api=self.api, renderer=MockRenderer())
        self.assertIs(self.api.viewport, viewport)

        plugin = DebugPlugin()
        self.manager.activate(plugin)

        contribution = next(
            item for item in self.api._pending_toolbar_items if item.id == TOOLBAR_ADD_PRIMITIVE_ID
        )
        menu_items_by_title = {item.title: item for item in contribution.menu_items}

        expected_titles = [
            "Box",
            "Cylinder",
            "Ring",
            "Plane",
            "Line",
            "Triangle",
            "Loft",
            "Point",
            "Arrow",
            "Clear All",
        ]
        for title in expected_titles:
            self.assertIn(title, menu_items_by_title)

        # 1. Add Box
        menu_items_by_title["Box"].callback()
        self.assertEqual(len(self.project.data["components"]), 1)
        box_comp = self.project.data["components"][0]
        self.assertEqual(box_comp["type"], TYPE_DEBUG_BOX)
        self.assertEqual(box_comp["id"], "box-1")
        self.assertEqual(box_comp["name"], "Box 1")
        self.assertEqual(self.api.current_selection, box_comp)
        self.assertIn("box-1", viewport.object_ids(layer=DEBUG_LAYER))

        # 2. Add Cylinder
        menu_items_by_title["Cylinder"].callback()
        self.assertEqual(len(self.project.data["components"]), 2)
        cyl_comp = self.project.data["components"][1]
        self.assertEqual(cyl_comp["type"], TYPE_DEBUG_CYLINDER)
        self.assertEqual(cyl_comp["id"], "cylinder-1")
        self.assertEqual(self.api.current_selection, cyl_comp)
        self.assertIn("cylinder-1", viewport.object_ids(layer=DEBUG_LAYER))

        # 3. Add Ring
        menu_items_by_title["Ring"].callback()
        self.assertIn("ring-1", viewport.object_ids(layer=DEBUG_LAYER))

        # 4. Add Plane
        menu_items_by_title["Plane"].callback()
        self.assertIn("plane-1", viewport.object_ids(layer=DEBUG_LAYER))

        # 5. Add Line
        menu_items_by_title["Line"].callback()
        self.assertIn("line-1", viewport.object_ids(layer=DEBUG_LAYER))

        # 6. Add Triangle
        menu_items_by_title["Triangle"].callback()
        self.assertIn("triangle-1", viewport.object_ids(layer=DEBUG_LAYER))

        # 7. Add Loft
        menu_items_by_title["Loft"].callback()
        self.assertIn("loft-1", viewport.object_ids(layer=DEBUG_LAYER))

        # 8. Add Point
        menu_items_by_title["Point"].callback()
        self.assertIn("point-1", viewport.object_ids(layer=DEBUG_LAYER))

        # 9. Add Arrow
        menu_items_by_title["Arrow"].callback()
        self.assertIn("arrow-1", viewport.object_ids(layer=DEBUG_LAYER))

        self.assertEqual(len(self.project.data["components"]), 9)

        # 10. Verify property editor instantiation for all debug components
        for comp in self.project.data["components"]:
            editor = self.api.create_component_editor(comp)
            self.assertIsNotNone(editor)
            icon = self.api.get_component_icon(comp)
            self.assertFalse(icon.isNull())
            if editor is not None:
                editor.deleteLater()
        self._app.processEvents()

        # 11. Update component parameters and verify viewport sync
        def update_box_length() -> None:
            box_comp["parameters"]["length"] = 500.0

        self.api.edit_component(box_comp, "Change length", update_box_length)
        box_obj = viewport.get_object("box-1")
        self.assertIsNotNone(box_obj)
        self.assertEqual(box_obj.primitives[0].size[0], 500.0)

        # 12. Clear debug components
        menu_items_by_title["Clear All"].callback()
        self.assertEqual(self.project.data["components"], [])
        self.assertEqual(viewport.object_ids(layer=DEBUG_LAYER), [])

        # Deactivate
        self.manager.deactivate("org.setuav.studio.debug")
        viewport.deleteLater()
        self._app.processEvents()

    def test_debug_component_in_tree_and_properties_panel(self) -> None:
        from setuav_studio.ui.panels.project_explorer.tree import ProjectExplorer
        from setuav_studio.ui.panels.properties.properties_panel import PropertiesPanel

        tree = ProjectExplorer(self.api)
        props = PropertiesPanel(self.api)
        viewport = StudioViewport(api=self.api, renderer=MockRenderer())

        tree.set_project(self.project)

        plugin = DebugPlugin()
        self.manager.activate(plugin)

        contribution = next(
            item for item in self.api._pending_toolbar_items if item.id == TOOLBAR_ADD_PRIMITIVE_ID
        )
        menu_items_by_title = {item.title: item for item in contribution.menu_items}

        # Add Box
        menu_items_by_title["Box"].callback()

        # Tree should contain box-1
        self.assertIn("box-1", tree._item_map)
        item = tree._item_map["box-1"]
        self.assertEqual(item.text(0), "Box 1")

        # Properties panel should show BoxComponentEditor
        self.assertIsInstance(props._current_widget, BoxComponentEditor)
        self.assertIsNotNone(props._current_widget.general_table)
        self.assertIsNotNone(props._current_widget.parameters_table)

        # Viewport should contain box-1
        self.assertIn("box-1", viewport.object_ids(layer=DEBUG_LAYER))

        # Properties panel parameters table should contain ColorPickerWidget
        from setuav_studio.ui.widget.color_picker import ColorPickerWidget

        color_picker = props._current_widget.parameters_table.cellWidget(3, 1)
        self.assertIsInstance(color_picker, ColorPickerWidget)
        assert isinstance(color_picker, ColorPickerWidget)
        self.assertEqual(color_picker.text(), "74, 144, 226")

        self.manager.deactivate("org.setuav.studio.debug")
        props.deleteLater()
        tree.deleteLater()
        viewport.deleteLater()
        self._app.processEvents()
