"""Tests for the transform tab: what a component attaches to and where it sits."""

from __future__ import annotations

import unittest
from typing import Any

from PySide6.QtWidgets import QComboBox

from setuav_studio.api import StudioAPI
from setuav_studio.project import open_project
from setuav_studio.ui.editor import TransformEditor
from setuav_studio.utilities.transform import components_by_id, resolve_world_transform
from tests._common import TEST_PROJECT_PATH, get_qapp, register_fixture_component_types


class TransformEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        register_fixture_component_types(self.api)
        self.project = open_project(TEST_PROJECT_PATH)
        self.api._host.set_project(self.project)

    def _editor(self, component_id: str) -> tuple[dict[str, Any], TransformEditor]:
        component = self.project.get_component(component_id)
        assert component is not None
        editor = TransformEditor(self.api, component)
        self.addCleanup(editor.deleteLater)
        return component, editor

    def _attach_combo(self, editor: TransformEditor) -> QComboBox:
        row = next(
            r
            for r in range(editor.reference_table.rowCount())
            if editor._property_key(editor.reference_table, r) == "attach_to"
        )
        combo = editor.reference_table.cellWidget(row, 1)
        assert isinstance(combo, QComboBox)
        return combo

    def _world_position(self, component_id: str) -> tuple[float, float, float]:
        return resolve_world_transform(component_id, components_by_id(self.project))[0]

    def test_attaching_elsewhere_keeps_the_component_in_place(self) -> None:
        propulsor, editor = self._editor("propulsor-cruise")
        combo = self._attach_combo(editor)
        self.assertEqual(combo.currentData(), "fuselage")
        before = self._world_position("propulsor-cruise")

        combo.setCurrentIndex(combo.findData("main-wing"))

        self.assertEqual(propulsor["attach_to"], "main-wing")
        for expected, actual in zip(before, self._world_position("propulsor-cruise"), strict=True):
            self.assertAlmostEqual(actual, expected, places=3)
        self.api.undo()
        self.assertEqual(propulsor["attach_to"], "fuselage")
        self.assertEqual(propulsor["transform"]["position"]["x"], 850.0)

    def test_editor_follows_undo(self) -> None:
        propulsor, editor = self._editor("propulsor-cruise")
        editor.position_spins["x"].setValue(900.0)
        self.assertEqual(propulsor["transform"]["position"]["x"], 900.0)

        self.api.undo()
        self.assertEqual(propulsor["transform"]["position"]["x"], 850.0)
        self.assertEqual(editor.position_spins["x"].line_edit.text(), "850.0")

    def test_targets_exclude_the_component_its_dependents_and_subparts(self) -> None:
        _wing, editor = self._editor("main-wing")
        combo = self._attach_combo(editor)
        targets = {combo.itemData(index) for index in range(combo.count())}

        self.assertIn("", targets)
        self.assertIn("fuselage", targets)
        self.assertIn("v-tail", targets)
        for excluded in ("main-wing", "aileron", "main-wing-flap", "ruddervator"):
            self.assertNotIn(excluded, targets)

    def test_a_subpart_shows_its_component_without_a_selector(self) -> None:
        _aileron, editor = self._editor("aileron")
        self.assertEqual(editor._property_value(editor.reference_table, "attach_to"), "Main Wing")
        row = next(
            r
            for r in range(editor.reference_table.rowCount())
            if editor._property_key(editor.reference_table, r) == "attach_to"
        )
        self.assertNotIsInstance(editor.reference_table.cellWidget(row, 1), QComboBox)

    def test_attach_reloads_once_and_non_numeric_values_coerce_and_follow_live_component(
        self,
    ) -> None:
        propulsor, editor = self._editor("propulsor-cruise")
        load_calls = 0
        orig_load = editor._load_component

        def counting_load(component: dict[str, Any]) -> None:
            nonlocal load_calls
            load_calls += 1
            orig_load(component)

        editor._load_component = counting_load  # type: ignore[method-assign]
        combo = self._attach_combo(editor)
        combo.setCurrentIndex(combo.findData("main-wing"))
        self.assertEqual(load_calls, 1)

        # Replacing the component dictionary in project data updates the editor from live data.
        idx = next(
            i
            for i, c in enumerate(self.project.data["components"])
            if c["id"] == "propulsor-cruise"
        )
        self.project.data["components"][idx] = {
            **propulsor,
            "transform": {
                "position": {"x": "15.0", "z": 12.5},
                "rotation": {"pitch": 0.0, "yaw": "5.0"},
            },
        }
        self.api.notify_project_content_changed()
        self.assertEqual(editor.position_spins["x"].value(), 15.0)
        self.assertEqual(editor.position_spins["y"].value(), 0.0)
        self.assertEqual(editor.position_spins["z"].value(), 12.5)
        self.assertEqual(editor.rotation_spins["roll"].value(), 0.0)
        self.assertEqual(editor.rotation_spins["yaw"].value(), 5.0)

        # Direct load coerces None and non-numeric strings via _number without error.
        editor._load_component(
            {
                **propulsor,
                "transform": {
                    "position": {"x": None, "y": "bad", "z": 2.0},
                    "rotation": {"roll": None, "pitch": 0.0, "yaw": 0.0},
                },
            }
        )
        self.assertEqual(editor.position_spins["x"].value(), 0.0)
        self.assertFalse(editor.position_spins["x"]._has_error)
        self.assertEqual(editor.position_spins["y"].value(), 0.0)
        self.assertFalse(editor.position_spins["y"]._has_error)
        self.assertEqual(editor.rotation_spins["roll"].value(), 0.0)


if __name__ == "__main__":
    unittest.main()
