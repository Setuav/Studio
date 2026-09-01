"""Focused tests for the core component-instance editor."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QComboBox

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.editors.instance import InstanceEditor
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class InstanceEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.source = {
            "id": "wing-left",
            "kind": "component",
            "name": "Left Wing",
        }
        self.parent = {
            "id": "fuselage",
            "kind": "component",
            "name": "Fuselage",
        }
        self.instance: dict[str, Any] = {
            "id": "wing-right",
            "kind": "instance",
            "name": "Right Wing",
            "source": "wing-left",
            "attach_to": "fuselage",
            "derivation": {"type": "mirror", "plane": "YZ", "offset": 12.5},
            "transform": {
                "position": {"x": 10, "y": 20, "z": 30},
                "rotation": {"roll": 1, "pitch": 2, "yaw": 3},
            },
        }
        self.api = StudioAPI()
        self.project = ProjectDocument(
            path=Path("instance-test.json"),
            kind="json",
            data={"components": [self.source, self.parent, self.instance]},
        )
        self.api._host.set_project(self.project)
        self.editor = InstanceEditor(self.api, self.instance)
        self.addCleanup(self.editor.deleteLater)

    def _row(self, key: str) -> int:
        for row in range(self.editor.properties_table.rowCount()):
            if self.editor._key(row) == key:
                return row
        self.fail(f"Property row not found: {key}")

    def _combo(self, key: str) -> QComboBox:
        widget = self.editor.properties_table.cellWidget(self._row(key), 1)
        self.assertIsInstance(widget, QComboBox)
        return widget

    def test_renders_mirror_properties_and_transform(self) -> None:
        table = self.editor.properties_table

        self.assertEqual(table.rowCount(), 7)
        self.assertEqual(table.item(self._row("source"), 1).text(), "Left Wing")
        self.assertEqual(table.item(self._row("parent"), 1).text(), "Fuselage")
        self.assertEqual(self._combo("derivation_type").currentData(), "mirror")
        self.assertEqual(self._combo("plane").currentData(), "YZ")
        self.assertEqual(table.item(self._row("offset"), 1).text(), "12.5")
        self.assertEqual(
            [self.editor.transform_table.item(0, column).text() for column in range(3)],
            ["10", "20", "30"],
        )
        self.assertEqual(
            [self.editor.transform_table.item(1, column).text() for column in range(3)],
            ["1", "2", "3"],
        )

    def test_copy_defaults_and_missing_component_names_are_safe(self) -> None:
        copy_instance: dict[str, Any] = {
            "id": "copy",
            "kind": "instance",
            "source": "missing",
            "parent": "also-missing",
        }
        editor = InstanceEditor(self.api, copy_instance)
        self.addCleanup(editor.deleteLater)

        self.assertEqual(editor.properties_table.rowCount(), 5)
        self.assertEqual(editor._property_value("source", {}), "missing")
        self.assertEqual(editor._property_value("parent", {}), "also-missing")
        self.assertEqual(editor._property_value("derivation_type", {}), "copy")
        self.assertEqual(editor._property_value("plane", {}), "XZ")
        self.assertEqual(editor._property_value("offset", {}), "0")
        self.assertEqual(editor._property_value("name", {}), "")
        self.assertEqual(editor.transform_table.item(0, 0).text(), "0")

        copy_instance.pop("parent")
        self.assertEqual(editor._property_value("parent", {}), "—")

    def test_name_edit_is_undoable_and_blank_name_is_rejected(self) -> None:
        name_item = self.editor.properties_table.item(self._row("name"), 1)
        name_item.setText("Renamed Wing")

        self.assertEqual(self.instance["name"], "Renamed Wing")
        self.assertEqual(self.api._host.undo_stack.undoText(), "Rename component instance")
        self.api.undo()
        self.assertEqual(self.instance["name"], "Right Wing")
        self.api.redo()
        self.assertEqual(self.instance["name"], "Renamed Wing")

        command_count = self.api._host.undo_stack.count()
        self.editor.properties_table.item(self._row("name"), 1).setText("   ")
        self.assertEqual(self.instance["name"], "Renamed Wing")
        self.assertEqual(self.api._host.undo_stack.count(), command_count)
        self.assertEqual(
            self.editor.properties_table.item(self._row("name"), 1).text(),
            "Renamed Wing",
        )

        self.editor._update_property(self._row("name"), 0)
        self.editor._loading = True
        self.editor._update_property(self._row("name"), 1)
        self.editor._loading = False

    def test_mirror_offset_accepts_numbers_and_rejects_invalid_text(self) -> None:
        offset_item = self.editor.properties_table.item(self._row("offset"), 1)
        offset_item.setText("25.75")

        self.assertEqual(self.instance["derivation"]["offset"], 25.75)
        self.assertEqual(self.api._host.undo_stack.undoText(), "Edit mirror offset")

        command_count = self.api._host.undo_stack.count()
        self.editor.properties_table.item(self._row("offset"), 1).setText("invalid")
        self.assertEqual(self.instance["derivation"]["offset"], 25.75)
        self.assertEqual(self.api._host.undo_stack.count(), command_count)

    def test_derivation_and_plane_combos_update_the_instance(self) -> None:
        derivation_combo = self._combo("derivation_type")
        derivation_combo.setCurrentIndex(derivation_combo.findData("copy"))

        self.assertEqual(self.instance["derivation"], {"type": "copy"})
        self.assertEqual(self.editor.properties_table.rowCount(), 5)

        self.editor._change_derivation("mirror")
        self.assertEqual(
            self.instance["derivation"],
            {"type": "mirror", "plane": "XZ", "offset": 0.0},
        )
        plane_combo = self._combo("plane")
        plane_combo.setCurrentIndex(plane_combo.findData("XY"))
        self.assertEqual(self.instance["derivation"]["plane"], "XY")

        command_count = self.api._host.undo_stack.count()
        self.editor._change_derivation("invalid")
        self.editor._change_plane("invalid")
        self.editor._loading = True
        self.editor._change_derivation("copy")
        self.editor._change_plane("YZ")
        self.editor._loading = False
        self.assertEqual(self.api._host.undo_stack.count(), command_count)

    def test_transform_edit_is_atomic_and_invalid_values_are_rejected(self) -> None:
        values = ((100.5, -20.0, 3.0), (4.0, 5.5, -6.0))
        self.editor._loading = True
        for row, row_values in enumerate(values):
            for column, value in enumerate(row_values):
                self.editor.transform_table.item(row, column).setText(str(value))
        self.editor._loading = False
        self.editor._update_transform(0, 0)

        self.assertEqual(
            self.instance["transform"],
            {
                "position": {"x": 100.5, "y": -20.0, "z": 3.0},
                "rotation": {"roll": 4.0, "pitch": 5.5, "yaw": -6.0},
            },
        )
        self.assertEqual(self.api._host.undo_stack.undoText(), "Edit instance transform")

        command_count = self.api._host.undo_stack.count()
        with QSignalBlocker(self.editor.transform_table):
            self.editor.transform_table.item(0, 0).setText("not-a-number")
        self.editor._update_transform(0, 0)
        self.assertEqual(self.api._host.undo_stack.count(), command_count)
        self.assertEqual(self.editor.transform_table.item(0, 0).text(), "100.5")

        with QSignalBlocker(self.editor.transform_table):
            self.editor.transform_table.takeItem(1, 2)
        self.editor._update_transform(1, 2)
        self.assertEqual(self.api._host.undo_stack.count(), command_count)

    def test_component_lookup_and_mapping_helpers_handle_malformed_data(self) -> None:
        self.project.data["components"] = ["invalid", {"id": "unnamed"}]
        self.assertEqual(self.editor._component_name("unnamed"), "unnamed")
        self.assertEqual(self.editor._component_name("unknown"), "unknown")

        self.project.data["components"] = {"id": "not-a-list"}
        self.assertEqual(self.editor._component_name("unknown"), "unknown")
        self.api.current_project = None
        self.assertEqual(self.editor._component_name(None), "")

        owner: dict[str, Any] = {"nested": "invalid"}
        self.assertEqual(InstanceEditor._mapping(owner, "nested"), {})
        nested = InstanceEditor._object(owner, "nested")
        self.assertEqual(nested, {})
        self.assertIs(owner["nested"], nested)
        self.assertIs(InstanceEditor._object(owner, "nested"), nested)

    def test_widget_helpers_tolerate_missing_rows_and_optional_icons(self) -> None:
        header = InstanceEditor._header("Plain header")
        self.addCleanup(header.deleteLater)

        self.assertEqual(self.editor._key(-1), "")
        self.editor._update_property(self._row("id"), 1)
        self.editor._set_combo("missing", "x", [("x", "X")], lambda _value: None)

        source_row = self._row("source")
        self.editor.properties_table.takeItem(source_row, 1)
        self.editor._set_combo("source", "x", [("x", "X")], lambda _value: None)


if __name__ == "__main__":
    unittest.main()
