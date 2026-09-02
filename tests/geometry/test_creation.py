"""Tests for geometry creation toolbar commands."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from plugins.geometry.creation import (
    _CONTROL_SURFACE_TYPE,
    _FUSELAGE_TYPE,
    _LIFTING_SURFACE_TYPE,
    GeometryCreationController,
)
from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class GeometryCreationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.statuses: list[tuple[str, str, int]] = []
        self.api._host.bind_status_handler(
            lambda message, level, timeout: self.statuses.append((message, level, timeout))
        )
        self.project = ProjectDocument(
            Path("geometry-creation.json"),
            "json",
            {"components": []},
        )
        self.api._host.set_project(self.project)
        self.controller = GeometryCreationController(self.api)

    def test_toolbar_contributions_dispatch_all_presets(self) -> None:
        (
            struct_action,
            fuselage_action,
            lifting_action,
            control_action,
        ) = self.controller.contributions()

        self.assertEqual(
            (
                struct_action.id,
                fuselage_action.id,
                lifting_action.id,
                control_action.id,
            ),
            GeometryCreationController.toolbar_ids,
        )
        self.assertTrue(struct_action.enabled_when())
        self.assertTrue(fuselage_action.enabled_when())
        self.assertFalse(control_action.enabled_when())
        with patch.object(self.controller, "add_lifting_surface") as add_lifting_surface:
            for item in lifting_action.menu_items:
                item.callback()
        self.assertEqual(
            [call.args[0] for call in add_lifting_surface.call_args_list],
            ["main-wing", "horizontal-tail", "vertical-tail", "generic"],
        )
        with patch.object(self.controller, "add_control_surface") as add_control_surface:
            for item in control_action.menu_items:
                item.callback()
        self.assertEqual(
            [call.args[0] for call in add_control_surface.call_args_list],
            ["aileron", "elevator", "rudder", "flap"],
        )

    def test_add_structural_system_creates_assembly_and_starter_airframe(self) -> None:
        self.controller.add_structural_system()

        assemblies = self.project.data.get("assemblies", [])
        self.assertEqual(len(assemblies), 1)
        system = assemblies[0]
        self.assertEqual(system["type"], "org.setuav.core:structural-system")
        self.assertIn("fuselage", system["members"])
        self.assertIn("wings", system["members"])

        # Components were auto-created
        components = self.project.data.get("components", [])
        self.assertEqual(len(components), 2)
        c_types = {c["type"] for c in components}
        self.assertEqual(c_types, {_FUSELAGE_TYPE, _LIFTING_SURFACE_TYPE})

    def test_add_fuselage_creates_default_loft_and_is_undoable(self) -> None:
        self.controller.add_fuselage()

        fuselage = self.project.data["components"][0]
        sections = fuselage["parameters"]["geometry"]["segments"][0]["sections"]
        self.assertEqual(fuselage["type"], _FUSELAGE_TYPE)
        self.assertEqual(
            [section["position"]["x"] for section in sections],
            [0.0, 140.0, 600.0],
        )
        self.assertEqual(
            [section["profile"]["diameter"] for section in sections],
            [25.0, 120.0, 35.0],
        )
        self.assertIs(self.api.current_selection, fuselage)
        self.assertEqual(self.statuses[-1], ("Created Fuselage", "success", 3000))
        self.api.undo()
        self.assertEqual(self.project.data["components"], [])
        self.api.redo()
        self.assertEqual(len(self.project.data["components"]), 1)

    def test_lifting_surface_presets_create_expected_geometry(self) -> None:
        self.controller.add_fuselage()
        expected = {
            "main-wing": ("Main Wing", True, 0.0, 0.0, "2412"),
            "horizontal-tail": ("Horizontal Tail", True, 500.0, 0.0, "0012"),
            "vertical-tail": ("Vertical Tail", False, 500.0, 90.0, "0012"),
            "generic": ("Lifting Surface", False, 0.0, 0.0, "0012"),
            "unknown": ("Lifting Surface 2", False, 500.0, 0.0, "0012"),
        }

        for preset, values in expected.items():
            self.controller.add_lifting_surface(preset)
            surface = self.api.current_selection
            assert isinstance(surface, dict)
            name, mirrored, x_position, roll, airfoil = values
            geometry = surface["parameters"]["geometry"]
            self.assertEqual(surface["name"], name)
            self.assertEqual(surface["attach_to"], "fuselage")
            self.assertEqual(surface["transform"]["position"]["x"], x_position)
            self.assertEqual(surface["transform"]["rotation"]["roll"], roll)
            self.assertEqual(geometry["mirror"], mirrored)
            self.assertEqual(geometry["profiles"][0]["airfoil"], airfoil)

    def test_control_surface_requires_selected_lifting_surface(self) -> None:
        self.controller.add_control_surface("aileron")

        self.assertEqual(self.project.data["components"], [])
        self.assertEqual(
            self.statuses[-1],
            ("Select a lifting surface before adding a control surface", "warning", 4000),
        )

    def test_control_surface_types_use_parent_dimensions(self) -> None:
        self.controller.add_lifting_surface("main-wing")
        parent = self.api.current_selection
        assert isinstance(parent, dict)

        for surface_type, label in (
            ("aileron", "Aileron"),
            ("elevator", "Elevator"),
            ("rudder", "Rudder"),
            ("flap", "Flap"),
            ("spoiler", "Control Surface"),
        ):
            self.api.set_selection(parent)
            self.controller.add_control_surface(surface_type)
            control = self.api.current_selection
            assert isinstance(control, dict)
            geometry = control["parameters"]["geometry"]
            self.assertEqual(control["type"], _CONTROL_SURFACE_TYPE)
            self.assertEqual(control["parent"], "main-wing")
            self.assertEqual(control["name"], label)
            self.assertEqual(geometry["span_start"], 200.0)
            self.assertEqual(geometry["span_end"], 425.0)
            self.assertEqual(geometry["chord"], 55.0)

    def test_editability_validation_handles_invalid_projects(self) -> None:
        self.api.current_project = None
        self.assertFalse(self.controller._can_edit_project())
        self.assertFalse(self.controller._can_add_control_surface())
        self.assertFalse(self.controller._require_editable_project())
        self.assertIn("Open a project", self.statuses[-1][0])
        self.controller.add_fuselage()
        self.controller.add_lifting_surface("main-wing")
        self.controller.add_control_surface("aileron")

        self.api.current_project = self.project
        self.project.read_only = True
        self.assertFalse(self.controller._can_edit_project())
        self.assertFalse(self.controller._require_editable_project())
        self.assertEqual(self.statuses[-1][0], "The project is read-only")

        self.project.read_only = False
        self.project.data["components"] = "invalid"
        self.assertFalse(self.controller._require_editable_project())
        self.assertEqual(self.statuses[-1], ("Project components are invalid", "error", 5000))
        self.assertEqual(self.controller._components(), [])

    def test_unique_identity_skips_existing_ids_and_names(self) -> None:
        self.project.data["components"] = [
            "invalid",
            {"id": "wing", "name": "Wing"},
            {"id": "wing-2", "name": "Wing 2"},
        ]

        self.assertEqual(self.controller._unique_identity("fresh", "Fresh"), ("fresh", "Fresh"))
        self.assertEqual(self.controller._unique_identity("wing", "Wing"), ("wing-3", "Wing 3"))
        self.assertEqual(self.controller._components(), self.project.data["components"][1:])

    def test_component_lookup_and_selection_require_valid_ids(self) -> None:
        invalid_id = {"id": 42, "type": _FUSELAGE_TYPE}
        empty_id = {"id": "", "type": _FUSELAGE_TYPE}
        wing = {"id": "wing", "type": _LIFTING_SURFACE_TYPE}
        self.project.data["components"] = [invalid_id, empty_id, wing]

        self.assertIsNone(self.controller._first_component_id(_FUSELAGE_TYPE))
        self.assertEqual(self.controller._first_component_id(_LIFTING_SURFACE_TYPE), "wing")
        self.api.current_selection = "invalid"
        self.assertIsNone(self.controller._selected_lifting_surface())
        self.api.current_selection = {"id": "wing", "type": _FUSELAGE_TYPE}
        self.assertIsNone(self.controller._selected_lifting_surface())
        self.api.current_selection = {"id": "missing", "type": _LIFTING_SURFACE_TYPE}
        self.assertIsNone(self.controller._selected_lifting_surface())
        self.api.current_selection = {"id": "wing", "type": _LIFTING_SURFACE_TYPE}
        self.assertIs(self.controller._selected_lifting_surface(), wing)

    def test_lifting_surface_size_handles_defaults_and_malformed_profiles(self) -> None:
        self.assertEqual(self.controller._lifting_surface_size({}), (500.0, 100.0))
        self.assertEqual(
            self.controller._lifting_surface_size({"parameters": "invalid"}),
            (500.0, 100.0),
        )
        component = {
            "parameters": {
                "geometry": {
                    "profiles": [
                        "invalid",
                        {"position": "invalid", "chord": 0},
                        {"position": {"y": -5}, "chord": 40},
                        {"position": {"y": -5}, "chord": 80},
                    ]
                }
            }
        }
        self.assertEqual(self.controller._lifting_surface_size(component), (1.0, 100.0))
        self.assertEqual(
            self.controller._wing_profile(20.0, 50.0, "0012")["position"]["y"],
            20.0,
        )

    def test_append_and_public_commands_safely_ignore_unavailable_projects(self) -> None:
        component = {"id": "test", "name": "Test"}
        self.api.current_project = None
        self.controller._append_component(component, "Add test")
        with patch.object(self.controller, "_require_editable_project", return_value=True):
            self.controller.add_fuselage()

        self.api._host.set_project(self.project)
        self.project.data["components"] = "invalid"
        with patch.object(self.api, "edit_project", side_effect=lambda _text, change: change()):
            self.controller._append_component(component, "Add test")
        self.assertIsNone(self.api.current_selection)


if __name__ == "__main__":
    unittest.main()
