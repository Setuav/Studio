"""Unit tests for BaseComponentEditor and ParameterField in core SDK."""

from __future__ import annotations

from pathlib import Path
import unittest
from PySide6.QtWidgets import QApplication

from setuav_studio.plugin_system import (
    BaseComponentEditor,
    ParameterField,
    StudioAPI,
)
from setuav_studio.project import ProjectDocument


class TestComponentEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_base_component_editor_and_undo_redo(self) -> None:
        api = StudioAPI()
        doc = ProjectDocument(
            path=Path("/tmp/test.json"),
            kind="json",
            data={
                "components": [
                    {
                        "id": "motor-1",
                        "type": "test:motor",
                        "name": "Brushless Motor",
                        "manufacturer": "T-Motor",
                        "model": "MN4014",
                        "mass": 150.0,
                        "parameters": {
                            "kv": 400.0,
                            "resistance": 0.045,
                        },
                    }
                ]
            },
        )
        api.set_project(doc)
        comp = doc.data["components"][0]

        fields = [
            ParameterField(key="kv", label="KV Rating", unit="RPM/V", default=400.0),
            ParameterField(key="resistance", label="Resistance", unit="Ω", decimals=4, default=0.05),
        ]

        editor = BaseComponentEditor(api, comp, parameter_fields=fields)

        # Check loaded values in general_table and parameters_table
        self.assertEqual(editor._property_text(editor.general_table, 0), "Brushless Motor")
        self.assertEqual(editor._property_text(editor.general_table, 3), "T-Motor")
        self.assertEqual(editor._property_text(editor.general_table, 2), "150.0")
        self.assertEqual(editor._property_text(editor.parameters_table, 0), "400.00")

        # Edit a field in general table (row 0 = name)
        editor.general_table.item(0, 1).setText("Updated Motor Name")
        self.assertEqual(comp["name"], "Updated Motor Name")

        # Edit a parameter in parameters table (row 0 = kv)
        editor.parameters_table.item(0, 1).setText("450.0")
        self.assertEqual(comp["parameters"]["kv"], 450.0)

        # Test Undo
        api.undo()
        self.assertEqual(comp["parameters"]["kv"], 400.0)

        # Test Redo
        api.redo()
        self.assertEqual(comp["parameters"]["kv"], 450.0)


if __name__ == "__main__":
    unittest.main()
