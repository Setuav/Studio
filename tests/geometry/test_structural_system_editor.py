"""Unit tests for StructuralSystemEditor."""

from __future__ import annotations

import unittest
from pathlib import Path

from plugins.geometry.editors.structural_system import StructuralSystemEditor
from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class StructuralSystemEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.project_data = {
            "name": "Test UAV",
            "components": [
                {
                    "id": "fuse-1",
                    "name": "Main Fuselage",
                    "type": "org.setuav.core:fuselage",
                    "mass": 1.2,
                    "parameters": {
                        "sections": [
                            {"x": 0.0, "profile": {"diameter": 30.0}},
                            {"x": 800.0, "profile": {"diameter": 20.0}},
                        ]
                    },
                },
                {
                    "id": "wing-1",
                    "name": "Main Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "mass": 0.8,
                    "transform": {"translation": [200.0, 0.0, 50.0]},
                    "parameters": {
                        "wingspan": 1600.0,
                        "root_chord": 220.0,
                        "tip_chord": 160.0,
                    },
                },
                {
                    "id": "htail-1",
                    "name": "Horizontal Tail",
                    "type": "org.setuav.core:lifting-surface",
                    "mass": 0.2,
                    "transform": {"translation": [700.0, 0.0, 50.0]},
                    "parameters": {
                        "wingspan": 500.0,
                        "root_chord": 120.0,
                        "tip_chord": 80.0,
                    },
                },
            ],
            "assemblies": [
                {
                    "id": "airframe-1",
                    "name": "Main Airframe",
                    "type": "org.setuav.core:structural-system",
                    "members": {
                        "fuselage": "fuse-1",
                        "main_wing": "wing-1",
                        "horizontal_tail": "htail-1",
                    },
                }
            ],
        }
        self.project = ProjectDocument(
            Path("test_struct.json"),
            "json",
            self.project_data,
        )
        self.api._host.set_project(self.project)
        self.assembly = self.project_data["assemblies"][0]

    def test_editor_loads_and_displays_members_and_metrics(self) -> None:
        editor = StructuralSystemEditor(self.api, self.assembly)

        # Check General Table
        self.assertEqual(editor._property_text(editor.general_table, 0), "Main Airframe")
        self.assertEqual(
            editor._property_text(editor.general_table, 1),
            "org.setuav.core:structural-system",
        )

        # Check Metrics Table
        span_str = editor._property_text(editor.metrics_table, 0)
        self.assertEqual(span_str, "1.600 m")

        fuse_len_str = editor._property_text(editor.metrics_table, 4)
        self.assertEqual(fuse_len_str, "0.800 m")

        mass_str = editor._property_text(editor.metrics_table, 7)
        self.assertEqual(mass_str, "2.200 kg")

        # Tail volume ratio should be computed
        vh_str = editor._property_text(editor.metrics_table, 5)
        self.assertNotEqual(vh_str, "-")

    def test_member_assignment_change_triggers_project_edit(self) -> None:
        editor = StructuralSystemEditor(self.api, self.assembly)
        editor._on_member_changed("fuselage", "")

        self.assertNotIn("fuselage", self.assembly["members"])


if __name__ == "__main__":
    unittest.main()
