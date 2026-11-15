"""Unit tests for Debug Plugin Loft component and TableParameterField integration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from plugins.debug import DebugPlugin
from plugins.debug.components.loft import (
    LoftComponent,
    LoftComponentEditor,
    add_loft_to_viewport,
    create_loft_component,
)
from setuav_studio.api import StudioAPI, TableParameterField
from setuav_studio.project import create_project
from setuav_studio.ui.viewport import StudioViewport


class TestDebugLoft(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_debug_loft.suav"
        self.api = StudioAPI()
        self.api._host.set_project(create_project(self.project_path))
        self.plugin = DebugPlugin()
        self.plugin.activate(self.api)

    def tearDown(self) -> None:
        self.plugin.deactivate(self.api)
        self.temp_dir.cleanup()

    def test_loft_component_model_and_table_parameter_field(self) -> None:
        loft = create_loft_component("loft-1", "My Loft")
        self.assertEqual(loft.id, "loft-1")
        self.assertEqual(loft.name, "My Loft")

        # TableParameterField descriptors
        table_fields = LoftComponent.get_table_fields()
        self.assertEqual(len(table_fields), 1)
        self.assertIsInstance(table_fields[0], TableParameterField)
        self.assertEqual(table_fields[0].key, "sections")

        # Initial default sections (3 stations)
        self.assertEqual(len(loft.sections), 3)
        self.assertEqual(loft.sections[0].offset, 0.0)
        self.assertEqual(loft.sections[0].chord, 180.0)
        self.assertEqual(loft.sections[1].offset, 200.0)
        self.assertEqual(loft.sections[1].chord, 135.0)
        self.assertEqual(loft.sections[2].offset, 400.0)
        self.assertEqual(loft.sections[2].chord, 90.0)

    def test_loft_component_editor_table_rendering(self) -> None:
        loft = create_loft_component("loft-test", "Test Wing")
        comp_dict = loft.raw_data
        assert self.api.project is not None
        self.api.project.data["components"].append(comp_dict)

        editor = LoftComponentEditor(self.api, comp_dict)
        self.addCleanup(editor.deleteLater)

        self.assertIn("sections", editor._table_widgets)
        table = editor._table_widgets["sections"]
        self.assertEqual(table.rowCount(), 4)  # 1 unit row + 3 stations
        # Check column headers: #, Offset, Chord, Twist
        self.assertIn("Offset", table.horizontalHeaderItem(1).text())
        self.assertIn("Chord", table.horizontalHeaderItem(2).text())
        self.assertIn("Twist", table.horizontalHeaderItem(3).text())
        # Check Row 0 is Unit row
        self.assertEqual(table.item(0, 0).text(), "Unit")
        self.assertEqual(table.item(0, 1).text(), "[mm]")
        self.assertEqual(table.item(0, 2).text(), "[mm]")
        self.assertEqual(table.item(0, 3).text(), "[°]")

        # Edit station 1 chord to 160.0 (table row 2)
        table.item(2, 2).setText("160.0")
        self.assertEqual(comp_dict["parameters"]["sections"][1]["chord"], 160.0)

        # Test Undo
        self.api.undo()
        self.assertEqual(comp_dict["parameters"]["sections"][1]["chord"], 135.0)

        # Test Redo
        self.api.redo()
        self.assertEqual(comp_dict["parameters"]["sections"][1]["chord"], 160.0)

        # Add Row
        editor._on_add_table_row("sections")
        self.assertEqual(len(comp_dict["parameters"]["sections"]), 4)
        self.assertEqual(table.rowCount(), 5)  # 1 unit row + 4 stations

        # Remove Row
        editor._on_remove_table_row("sections")
        self.assertEqual(len(comp_dict["parameters"]["sections"]), 3)
        self.assertEqual(table.rowCount(), 4)

    def test_loft_viewport_rendering_with_stations(self) -> None:
        viewport = StudioViewport()
        self.addCleanup(viewport.deleteLater)

        loft = create_loft_component("loft-render", "Render Wing")
        add_loft_to_viewport(
            viewport,
            "loft-render",
            "Render Wing",
            loft,
            px=0.0,
            py=0.0,
            pz=0.0,
        )

        obj = viewport.get_object("loft-render")
        self.assertIsNotNone(obj)
        self.assertEqual(obj.layer, "debug")


if __name__ == "__main__":
    unittest.main()
