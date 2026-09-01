"""Tests for electrical propulsion component creation commands."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from plugins.electrical_propulsion.creation import (
    _ASSEMBLY_TYPE,
    PropulsionCreationController,
)
from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class PropulsionCreationTests(unittest.TestCase):
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
            Path("propulsion-creation.json"),
            "json",
            {"components": [], "assemblies": []},
        )
        self.api._host.set_project(self.project)
        self.controller = PropulsionCreationController(self.api)

    def test_toolbar_contributions_dispatch_each_component_kind(self) -> None:
        assembly_action, component_action = self.controller.contributions()

        self.assertEqual(
            (assembly_action.id, component_action.id),
            PropulsionCreationController.toolbar_ids,
        )
        self.assertTrue(assembly_action.enabled_when())
        self.assertFalse(component_action.menu_items[0].enabled_when())
        with patch.object(self.controller, "add_component") as add_component:
            for item in component_action.menu_items:
                item.callback()
        self.assertEqual(
            [call.args[0] for call in add_component.call_args_list],
            ["battery", "esc", "motor", "propeller", "rotor"],
        )

    def test_add_assembly_creates_valid_members_and_supports_undo(self) -> None:
        self.project.data.pop("assemblies")
        self.controller.add_assembly()

        components = self.project.data["components"]
        assembly = self.project.data["assemblies"][0]
        self.assertEqual(len(components), 4)
        self.assertEqual(assembly["type"], _ASSEMBLY_TYPE)
        self.assertEqual(
            assembly["members"],
            {
                "battery": "propulsion-system-battery",
                "controllers": ["propulsion-system-esc"],
                "motors": ["propulsion-system-motor"],
                "propulsors": ["propulsion-system-propeller"],
            },
        )
        propeller = components[-1]
        self.assertEqual(propeller["attach_to"], "propulsion-system-motor")
        self.assertIs(self.api.current_selection, assembly)
        self.assertEqual(self.statuses[-1], ("Created Propulsion System", "success", 3000))

        self.api.undo()
        self.assertEqual(self.project.data["components"], [])
        self.assertNotIn("assemblies", self.project.data)
        self.api.redo()
        self.assertEqual(len(self.project.data["components"]), 4)

    def test_duplicate_assembly_gets_unique_ids_and_names(self) -> None:
        self.controller.add_assembly()
        self.controller.add_assembly()

        assemblies = self.project.data["assemblies"]
        self.assertEqual(
            [(item["id"], item["name"]) for item in assemblies],
            [
                ("propulsion-system", "Propulsion System"),
                ("propulsion-system-2", "Propulsion System 2"),
            ],
        )
        ids = [component["id"] for component in self.project.data["components"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_add_component_updates_each_member_role(self) -> None:
        self.controller.add_assembly()
        assembly = self.project.data["assemblies"][0]
        self.api.set_selection(assembly)

        self.controller.add_component("battery")
        self.controller.add_component("motor")
        self.controller.add_component("rotor")
        assembly = self.controller._find_assembly("propulsion-system")
        assert assembly is not None
        members = assembly["members"]
        self.assertEqual(members["battery"], "propulsion-system-battery-2")
        self.assertEqual(members["motors"][-1], "propulsion-system-motor-2")
        self.assertEqual(members["propulsors"][-1], "propulsion-system-rotor")

        rotor = self.controller._find_component("propulsion-system-rotor")
        assert rotor is not None
        self.assertEqual(rotor["attach_to"], "propulsion-system-motor-2")
        self.assertEqual(rotor["parameters"]["collective_pitch"], 0.0)
        self.assertIs(self.api.current_selection, rotor)
        self.assertIn("Added Rotor", self.statuses[-1][0])

    def test_add_component_repairs_non_list_member_role(self) -> None:
        self.controller.add_assembly()
        assembly = self.controller._find_assembly("propulsion-system")
        assert assembly is not None
        assembly["members"]["controllers"] = "invalid"
        self.api.set_selection(assembly)

        self.controller.add_component("esc")

        assembly = self.controller._find_assembly("propulsion-system")
        assert assembly is not None
        self.assertEqual(assembly["members"]["controllers"], ["propulsion-system-esc-2"])

    def test_target_selection_handles_members_and_multiple_assemblies(self) -> None:
        self.assertIsNone(self.controller._choose_target_assembly())
        self.assertEqual(self.statuses[-1][1], "warning")

        first = self._assembly("first", "First")
        second = self._assembly("second", "Second")
        first_members = first["members"]
        assert isinstance(first_members, dict)
        first_members["motors"] = ["motor-1"]
        self.project.data["assemblies"] = ["invalid", first, second]

        self.api.set_selection({"id": "motor-2", "kind": "component"})
        self.assertIs(self.controller._choose_target_assembly(), second)

        self.api.set_selection(None)
        with patch(
            "plugins.electrical_propulsion.creation.QInputDialog.getItem",
            return_value=("Second (second)", True),
        ):
            self.assertIs(self.controller._choose_target_assembly(), second)
        with patch(
            "plugins.electrical_propulsion.creation.QInputDialog.getItem",
            return_value=("", False),
        ):
            self.assertIsNone(self.controller._choose_target_assembly())

        self.project.data["assemblies"] = [first]
        self.assertIs(self.controller._choose_target_assembly(), first)

    def test_selected_assembly_handles_all_selection_shapes(self) -> None:
        first = self._assembly("first", "First")
        malformed = self._assembly("bad", "Bad")
        malformed["members"] = "invalid"
        assemblies = [malformed, first]

        self.api.current_selection = "invalid"
        self.assertIsNone(self.controller._selected_assembly(assemblies))
        self.api.current_selection = {"type": _ASSEMBLY_TYPE, "id": "first"}
        self.assertIs(self.controller._selected_assembly(assemblies), first)
        self.api.current_selection = {"type": _ASSEMBLY_TYPE, "id": "missing"}
        self.assertIsNone(self.controller._selected_assembly(assemblies))
        self.api.current_selection = {"id": ""}
        self.assertIsNone(self.controller._selected_assembly(assemblies))
        self.api.current_selection = {"id": "battery-1"}
        self.assertIs(self.controller._selected_assembly(assemblies), first)
        self.api.current_selection = {"id": "motor-2"}
        self.assertIs(self.controller._selected_assembly(assemblies), first)
        self.api.current_selection = {"id": "unknown"}
        self.assertIsNone(self.controller._selected_assembly(assemblies))

    def test_editability_validation_reports_each_invalid_project_state(self) -> None:
        self.api.current_project = None
        self.assertFalse(self.controller._can_edit_project())
        self.assertFalse(self.controller._can_add_component())
        self.assertFalse(self.controller._require_editable_project())
        self.assertIn("Open a project", self.statuses[-1][0])

        self.api.current_project = self.project
        self.project.read_only = True
        self.assertFalse(self.controller._can_edit_project())
        self.assertFalse(self.controller._require_editable_project())
        self.assertEqual(self.statuses[-1][0], "The project is read-only")

        self.project.read_only = False
        self.project.data["components"] = "invalid"
        self.assertFalse(self.controller._require_editable_project())
        self.assertEqual(self.statuses[-1][1], "error")

        self.project.data["components"] = []
        self.project.data["assemblies"] = "invalid"
        self.assertFalse(self.controller._require_editable_project())
        self.assertEqual(self.statuses[-1][0], "Project assemblies are invalid")

    def test_defaults_identity_and_lookup_helpers(self) -> None:
        defaults = {
            kind: self.controller._new_component(kind, kind)
            for kind in ("battery", "esc", "motor", "propeller", "rotor")
        }
        self.assertEqual(defaults["battery"]["parameters"]["cell_count"], 6)
        self.assertEqual(defaults["esc"]["parameters"]["max_current"], 60.0)
        self.assertEqual(defaults["motor"]["parameters"]["kv"], 900.0)
        self.assertEqual(defaults["propeller"]["name"], "Propeller")
        self.assertNotIn("attach_to", defaults["propeller"])

        self.api.current_project = None
        self.assertEqual(self.controller._unique_identity("id", "Name"), ("id", "Name"))
        self.assertIsNone(self.controller._find_component("missing"))
        self.api.current_project = self.project
        self.project.data = {
            "components": ["invalid", {"id": "id"}, {"id": "id-2", "name": "Name 2"}],
            "assemblies": "invalid",
        }
        self.assertEqual(self.controller._unique_identity("fresh", "Fresh"), ("fresh", "Fresh"))
        self.assertEqual(self.controller._unique_identity("id", "Name"), ("id-3", "Name 3"))
        self.assertIsNone(self.controller._find_component("missing"))
        self.assertEqual(self.controller._find_component("id")["id"], "id")
        self.assertEqual(self.controller._propulsion_assemblies(), [])

    def test_public_commands_ignore_invalid_or_unavailable_targets(self) -> None:
        self.controller.add_component("unknown")
        self.assertEqual(self.project.data["components"], [])

        self.controller.add_component("motor")
        self.assertEqual(self.project.data["components"], [])

        self.project.read_only = True
        self.controller.add_assembly()
        self.controller.add_component("motor")
        self.assertEqual(self.project.data["components"], [])

    def test_commands_handle_project_changes_during_edit(self) -> None:
        self.api.current_project = None
        with patch.object(self.controller, "_require_editable_project", return_value=True):
            self.controller.add_assembly()
        with (
            patch.object(self.controller, "_require_editable_project", return_value=True),
            patch.object(self.controller, "_choose_target_assembly", return_value={"id": "x"}),
        ):
            self.controller.add_component("motor")

        self.api._host.set_project(self.project)

        def invalidate_components(_description: str, change: object) -> None:
            self.project.data["components"] = "invalid"
            assert callable(change)
            change()

        with patch.object(self.api, "edit_project", side_effect=invalidate_components):
            self.controller.add_assembly()
        self.assertEqual(self.project.data["assemblies"], [])

        self.project.data = {
            "components": [],
            "assemblies": [self._assembly("only", "Only")],
        }
        with patch.object(self.api, "edit_project", side_effect=invalidate_components):
            self.controller.add_component("motor")

    def test_propulsor_without_motor_is_created_unattached(self) -> None:
        assembly = self._assembly("only", "Only")
        members = assembly["members"]
        assert isinstance(members, dict)
        members["motors"] = []
        self.project.data["assemblies"] = [assembly]

        self.controller.add_component("propeller")

        propeller = self.controller._find_component("only-propeller")
        assert propeller is not None
        self.assertNotIn("attach_to", propeller)

    @staticmethod
    def _assembly(identifier: str, name: str) -> dict[str, object]:
        return {
            "id": identifier,
            "name": name,
            "type": _ASSEMBLY_TYPE,
            "members": {
                "battery": "battery-1",
                "controllers": ["esc-1"],
                "motors": ["motor-1", "motor-2"],
                "propulsors": [],
            },
        }


if __name__ == "__main__":
    unittest.main()
