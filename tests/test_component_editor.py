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

        # Check loaded values
        self.assertEqual(editor._name_edit.text(), "Brushless Motor")
        self.assertEqual(editor._manufacturer_edit.text(), "T-Motor")
        self.assertEqual(editor._mass_spin.value(), 150.0)
        self.assertEqual(editor._param_widgets["kv"].value(), 400.0)

        # Edit a field
        editor._name_edit.setText("Updated Motor Name")
        self.assertEqual(comp["name"], "Updated Motor Name")

        # Edit a parameter
        editor._param_widgets["kv"].setValue(450.0)
        self.assertEqual(comp["parameters"]["kv"], 450.0)

        # Test Undo
        api.undo()
        self.assertEqual(comp["parameters"]["kv"], 400.0)

        # Test Redo
        api.redo()
        self.assertEqual(comp["parameters"]["kv"], 450.0)


if __name__ == "__main__":
    unittest.main()
