"""Unit tests for BaseComponentEditor and ParameterField in core SDK."""

from __future__ import annotations

import unittest
from pathlib import Path

from setuav_studio.api import (
    ParameterField,
    StudioAPI,
    TableParameterField,
)
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.editor import BaseComponentEditor
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
        item_gen = editor.general_table.item(0, 1)
        assert item_gen is not None
        item_gen.setText("Updated Motor Name")
        self.assertEqual(comp["name"], "Updated Motor Name")

        # Edit a parameter in parameters table (row 0 = kv)
        item_param = editor.parameters_table.item(0, 1)
        assert item_param is not None
        item_param.setText("450.0")
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
        raw_comp = doc.get_component("wing-1")
        assert raw_comp is not None
        detached = copy.deepcopy(raw_comp)

        def mutate() -> None:
            detached["parameters"]["span"] = 3.2

        api.edit_component(detached, "Resize span", mutate)

        # Live project must be updated to 3.2
        live = doc.get_component("wing-1")
        assert live is not None
        self.assertEqual(live["parameters"]["span"], 3.2)
        self.assertEqual(detached["parameters"]["span"], 3.2)

        # Undo must restore live and detached
        api.undo()
        live_undone = doc.get_component("wing-1")
        assert live_undone is not None
        self.assertEqual(live_undone["parameters"]["span"], 1.5)

    def test_properties_panel_refreshes_on_project_content_change(self) -> None:
        import copy

        from PySide6.QtWidgets import QTabWidget

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
        comp = doc.get_component("wing-1")
        assert comp is not None
        api.set_selection(comp)

        self.assertIsNotNone(panel._current_widget)
        widget = panel._current_widget
        assert isinstance(widget, QTabWidget)
        editor = widget.widget(0)
        assert isinstance(editor, BaseComponentEditor)
        self.assertEqual(editor._component["parameters"]["span"], 1.5)

        # Deepcopy project components simulating config switch or edit_project
        doc.data["components"] = copy.deepcopy(doc.data["components"])
        comp_to_edit = doc.get_component("wing-1")
        assert comp_to_edit is not None
        comp_to_edit["parameters"]["span"] = 4.0
        api.notify_project_content_changed()

        # Panel must have refreshed and point to the live component
        self.assertIsNotNone(panel._current_widget)
        widget2 = panel._current_widget
        assert isinstance(widget2, QTabWidget)
        editor2 = widget2.widget(0)
        assert isinstance(editor2, BaseComponentEditor)
        self.assertEqual(editor2._component["parameters"]["span"], 4.0)

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

    def test_expression_write_order_and_atomic_undo(self) -> None:
        from setuav_studio.model.expression import get_expression

        statuses: list[tuple[str, str, int]] = []
        api = StudioAPI()
        api._host.bind_status_handler(lambda msg, lvl, ms: statuses.append((msg, lvl, ms)))
        doc = ProjectDocument(
            path=Path("/tmp/test-order.json"),
            kind="json",
            data={
                "parameters": {"base_mass": 50.0, "base_len": 100.0},
                "components": [
                    {
                        "id": "box-1",
                        "type": "test:box",
                        "name": "Box 1",
                        "mass": 100.0,
                        "parameters": {"length": 200.0},
                    }
                ],
            },
        )
        api._host.set_project(doc)
        comp = doc.data["components"][0]
        fields = [ParameterField(key="length", label="Length", unit="mm", default=100.0)]
        editor = BaseComponentEditor(api, comp, parameter_fields=fields)
        self.addCleanup(editor.deleteLater)

        # Invalid expressions mark cells erroneous and persist nothing.
        editor._on_mass_changed("=missing_var")
        editor._on_expression_cell_changed("length", "=missing_var")

        mass_cell = editor._property_cell(editor.general_table, "mass")
        len_cell = editor._property_cell(editor.parameters_table, "length")
        assert isinstance(mass_cell, ExpressionPropertyCell)
        assert isinstance(len_cell, ExpressionPropertyCell)
        self.assertTrue(mass_cell._has_error)
        self.assertTrue(len_cell._has_error)
        self.assertGreaterEqual(sum(1 for _, lvl, _ in statuses if lvl == "error"), 2)
        self.assertEqual(comp["mass"], 100.0)
        self.assertEqual(comp["parameters"]["length"], 200.0)
        self.assertIsNone(get_expression(comp, "mass"))
        self.assertIsNone(get_expression(comp["parameters"], "length"))
        self.assertFalse(api._host.undo_stack.canUndo())

        # Valid expressions store value + formula together and undo atomically.
        editor._on_mass_changed("=base_mass * 3")
        editor._on_expression_cell_changed("length", "=base_len * 2.5")
        self.assertEqual(comp["mass"], 150.0)
        self.assertEqual(get_expression(comp, "mass"), "=base_mass * 3")
        self.assertEqual(comp["parameters"]["length"], 250.0)
        self.assertEqual(get_expression(comp["parameters"], "length"), "=base_len * 2.5")

        api.undo()
        self.assertEqual(comp["parameters"]["length"], 200.0)
        self.assertIsNone(get_expression(comp["parameters"], "length"))
        self.assertEqual(comp["mass"], 150.0)

        api.undo()
        self.assertEqual(comp["mass"], 100.0)
        self.assertIsNone(get_expression(comp, "mass"))

        # Test ExpressionPropertyCell callback commit
        cell = editor.parameters_table.cellWidget(0, 1)
        self.assertIsInstance(cell, ExpressionPropertyCell)
        assert isinstance(cell, ExpressionPropertyCell)
        cell.line_edit.setText("300.0")
        cell._on_return_pressed()
        self.assertEqual(comp["parameters"]["length"], 300.0)

    def test_table_parameter_field_in_editor(self) -> None:
        api = StudioAPI()
        doc = ProjectDocument(
            path=Path("/tmp/test_table.json"),
            kind="json",
            data={
                "components": [
                    {
                        "id": "loft-1",
                        "type": "test:loft",
                        "name": "Loft Wing",
                        "parameters": {
                            "color": "#4A90E2",
                            "sections": [
                                {"offset": 0.0, "chord": 200.0, "twist": 0.0},
                                {"offset": 300.0, "chord": 100.0, "twist": 2.0},
                            ],
                        },
                    }
                ]
            },
        )
        api._host.set_project(doc)
        comp = doc.data["components"][0]

        fields = [
            ParameterField(key="color", label="Color", default="#4A90E2"),
            TableParameterField(
                key="sections",
                label="Wing Stations",
                columns=(
                    ParameterField(
                        key="offset", label="Offset", unit="mm", field_type=float, default=0.0
                    ),
                    ParameterField(
                        key="chord", label="Chord", unit="mm", field_type=float, default=150.0
                    ),
                    ParameterField(
                        key="twist", label="Twist", unit="°", field_type=float, default=0.0
                    ),
                ),
                min_rows=2,
            ),
        ]

        editor = BaseComponentEditor(api, comp, parameter_fields=fields)
        self.addCleanup(editor.deleteLater)

        self.assertIn("sections", editor._table_widgets)
        table = editor._table_widgets["sections"]
        self.assertEqual(table.rowCount(), 3)  # 1 unit row + 2 data rows
        # Row 0 is Unit row
        for r, c, val in [
            (0, 0, "Unit"),
            (0, 1, "[mm]"),
            (0, 2, "[mm]"),
            (0, 3, "[°]"),
            (1, 0, "1"),
            (1, 2, "200.00"),
            (2, 2, "100.00"),
        ]:
            it = table.item(r, c)
            assert it is not None
            self.assertEqual(it.text(), val)

        # Edit a cell: change chord of second station to 120.0
        it_edit = table.item(2, 2)
        assert it_edit is not None
        it_edit.setText("120.0")
        self.assertEqual(comp["parameters"]["sections"][1]["chord"], 120.0)

        # Test Undo cell edit
        api.undo()
        self.assertEqual(comp["parameters"]["sections"][1]["chord"], 100.0)

        # Test Redo cell edit
        api.redo()
        self.assertEqual(comp["parameters"]["sections"][1]["chord"], 120.0)

        # Test Formula support in table cell
        it_formula = table.item(2, 2)
        assert it_formula is not None
        it_formula.setText("=SPAN / 2")
        self.assertEqual(comp["parameters"]["sections"][1]["chord"], "=SPAN / 2")

        # Test Add Row
        editor._on_add_table_row("sections")
        self.assertEqual(len(comp["parameters"]["sections"]), 3)
        self.assertEqual(table.rowCount(), 4)  # 1 unit row + 3 data rows
        self.assertEqual(comp["parameters"]["sections"][2]["offset"], 600.0)

        # Test Remove Row
        editor._on_remove_table_row("sections")
        self.assertEqual(len(comp["parameters"]["sections"]), 2)
        self.assertEqual(table.rowCount(), 3)  # 1 unit row + 2 data rows

        # Respect min_rows: cannot remove below min_rows (2)
        editor._on_remove_table_row("sections")
        self.assertEqual(len(comp["parameters"]["sections"]), 2)


if __name__ == "__main__":
    unittest.main()
