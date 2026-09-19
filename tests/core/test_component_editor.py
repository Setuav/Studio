"""Unit tests for BaseComponentEditor and ParameterField in core SDK."""

from __future__ import annotations

import unittest
from pathlib import Path

from setuav_studio.api import (
    BaseComponentEditor,
    ParameterField,
    StudioAPI,
)
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.widget.table import ExpressionPropertyCell
from tests._common import get_qapp


class TestComponentEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

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
        api._host.set_project(doc)
        comp = doc.data["components"][0]

        fields = [
            ParameterField(key="kv", label="KV Rating", unit="RPM/V", default=400.0),
            ParameterField(
                key="resistance", label="Resistance", unit="Ω", decimals=4, default=0.05
            ),
        ]

        editor = BaseComponentEditor(api, comp, parameter_fields=fields)
        self.addCleanup(editor.deleteLater)

        # Check loaded values in general_table and parameters_table
        self.assertEqual(editor.general_table.rowCount(), 3)
        self.assertEqual(editor._property_text(editor.general_table, 0), "Brushless Motor")
        self.assertEqual(editor._property_text(editor.general_table, 2), "150.0")
        self.assertEqual(editor._property_numeric(editor.parameters_table, 0), 400.0)

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

    def test_edit_component_on_detached_dict_updates_live_project(self) -> None:
        import copy

        api = StudioAPI()
        doc = ProjectDocument(
            path=Path("/tmp/test.json"),
            kind="json",
            data={
                "components": [
                    {
                        "id": "wing-1",
                        "type": "org.setuav.core:lifting-surface",
                        "name": "Main Wing",
                        "parameters": {"span": 1.5},
                    }
                ]
            },
        )
        api._host.set_project(doc)

        # Detached copy of the component
        detached = copy.deepcopy(doc.get_component("wing-1"))

        def mutate() -> None:
            detached["parameters"]["span"] = 3.2

        api.edit_component(detached, "Resize span", mutate)

        # Live project must be updated to 3.2
        live = doc.get_component("wing-1")
        self.assertEqual(live["parameters"]["span"], 3.2)
        self.assertEqual(detached["parameters"]["span"], 3.2)

        # Undo must restore live and detached
        api.undo()
        self.assertEqual(live["parameters"]["span"], 1.5)

    def test_properties_panel_refreshes_on_project_content_change(self) -> None:
        import copy

        from setuav_studio.ui.editor import BaseComponentEditor
        from setuav_studio.ui.panels.properties import PropertiesPanel

        api = StudioAPI()
        doc = ProjectDocument(
            path=Path("/tmp/test.json"),
            kind="json",
            data={
                "components": [
                    {
                        "id": "wing-1",
                        "type": "test:comp",
                        "name": "Main Wing",
                        "parameters": {"span": 1.5},
                    }
                ]
            },
        )
        api._host.set_project(doc)
        api.register_component_editor("test:comp", lambda c: BaseComponentEditor(api, c))

        panel = PropertiesPanel(api)
        self.addCleanup(panel.deleteLater)
        api.set_selection(doc.get_component("wing-1"))

        self.assertIsNotNone(panel._current_widget)
        self.assertEqual(panel._current_widget._component["parameters"]["span"], 1.5)

        # Deepcopy project components simulating config switch or edit_project
        doc.data["components"] = copy.deepcopy(doc.data["components"])
        doc.get_component("wing-1")["parameters"]["span"] = 4.0
        api.notify_project_content_changed()

        # Panel must have refreshed and point to the live component
        self.assertIsNotNone(panel._current_widget)
        self.assertEqual(panel._current_widget._component["parameters"]["span"], 4.0)

    def test_on_expression_cell_changed_with_float_and_spinbox_callback(self) -> None:
        api = StudioAPI()
        doc = ProjectDocument(
            path=Path("/tmp/test.json"),
            kind="json",
            data={
                "components": [
                    {
                        "id": "box-1",
                        "type": "test:box",
                        "name": "Box 1",
                        "mass": 100.0,
                        "parameters": {"length": 200.0},
                    }
                ]
            },
        )
        api._host.set_project(doc)
        comp = doc.data["components"][0]
        fields = [ParameterField(key="length", label="Length", unit="mm", default=100.0)]
        editor = BaseComponentEditor(api, comp, parameter_fields=fields)
        self.addCleanup(editor.deleteLater)

        # Passing float or int should not raise AttributeError
        editor._on_expression_cell_changed("length", 250.0)
        self.assertEqual(comp["parameters"]["length"], 250.0)

        editor._on_mass_changed(120.0)
        self.assertEqual(comp["mass"], 120.0)

        # Test ExpressionPropertyCell callback commit
        cell = editor.parameters_table.cellWidget(0, 1)
        self.assertIsInstance(cell, ExpressionPropertyCell)
        assert isinstance(cell, ExpressionPropertyCell)
        cell.line_edit.setText("300.0")
        cell._on_return_pressed()
        self.assertEqual(comp["parameters"]["length"], 300.0)


if __name__ == "__main__":
    unittest.main()
