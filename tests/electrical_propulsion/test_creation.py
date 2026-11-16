"""Tests for electrical propulsion component creation commands and fixed root component."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QDialog

from plugins.electrical_propulsion.creation import (
    _PROPULSION_ID,
    PropulsionCreationController,
)
from plugins.electrical_propulsion.database import get_motor_database, get_propeller_database
from plugins.electrical_propulsion.models import BatteryModel
from plugins.electrical_propulsion.models.battery import BATTERY_OVERRIDES, battery_pack
from setuav_studio.api import StudioAPI, ToolbarContribution, ToolbarMenuItemContribution
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


def _enabled(contribution: ToolbarContribution | ToolbarMenuItemContribution) -> bool:
    assert contribution.enabled_when is not None
    return contribution.enabled_when()


class _AcceptingCatalogDialog:
    """Catalog dialog stand-in that accepts the first catalog entry."""

    def __init__(self, component_type: str, *args: object, **kwargs: object) -> None:
        self.selected_motor = None
        self.selected_propeller = None
        if component_type == "motor":
            db = get_motor_database()
            self.selected_motor = db.get(db.list_motors()[0])
        else:
            db = get_propeller_database()
            self.selected_propeller = db.get(db.list_propellers()[0])

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted


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
            {"components": []},
        )
        self.api._host.set_project(self.project)
        self.controller = PropulsionCreationController(self.api)
        dialog_patch = patch(
            "plugins.electrical_propulsion.catalog_dialog.ComponentCatalogDialog",
            _AcceptingCatalogDialog,
        )
        dialog_patch.start()
        self.addCleanup(dialog_patch.stop)

    def test_propulsion_root_inserted_after_airframe(self) -> None:
        self.project.data["components"] = [{"id": "airframe", "type": "org.setuav.core:airframe"}]
        self.controller.add_propulsion_system()
        self.assertEqual(self.project.data["components"][0]["id"], "airframe")
        propulsion = self.project.data["components"][1]
        self.assertEqual(propulsion["id"], _PROPULSION_ID)
        self.assertIsNone(propulsion["parent"])
        self.assertFalse(propulsion["has_transform"])
        self.assertFalse(propulsion["has_mass"])

    def test_toolbar_contributions_dispatch_each_component_kind(self) -> None:
        contributions = self.controller.contributions()
        self.assertEqual(len(contributions), 2)
        system_action = contributions[0]
        component_action = contributions[1]

        self.assertEqual(
            (system_action.id, component_action.id),
            PropulsionCreationController.toolbar_ids,
        )
        # Initially (no propulsion component):
        self.assertTrue(_enabled(system_action))
        self.assertFalse(_enabled(component_action))
        for item in component_action.menu_items:
            self.assertFalse(_enabled(item))

        # Add propulsion system
        self.controller.add_propulsion_system()
        self.assertFalse(_enabled(system_action))
        self.assertTrue(_enabled(component_action))
        for item in component_action.menu_items:
            self.assertTrue(_enabled(item))

        with patch.object(self.controller, "add_component") as add_component:
            for item in component_action.menu_items:
                item.callback()
        self.assertEqual(
            [call.args[0] for call in add_component.call_args_list],
            ["battery", "esc", "motor", "propeller", "rotor"],
        )

    def test_cannot_add_component_without_propulsion_system(self) -> None:
        self.controller.add_component("motor")
        self.assertEqual(len(self.project.data["components"]), 0)
        self.assertIn("Please add Electrical Propulsion", self.statuses[-1][0])

    def test_cannot_add_multiple_propulsion_systems(self) -> None:
        self.controller.add_propulsion_system()
        self.assertEqual(len(self.project.data["components"]), 1)
        self.assertEqual(self.project.data["components"][0]["id"], _PROPULSION_ID)

        # Attempt to add second
        self.controller.add_propulsion_system()
        self.assertEqual(len(self.project.data["components"]), 1)
        self.assertIn("Electrical Propulsion already exists", self.statuses[-1][0])

    def test_add_component_creates_valid_child_and_supports_undo(self) -> None:
        self.controller.add_propulsion_system()
        self.controller.add_component("motor")

        components = self.project.data["components"]
        self.assertEqual(len(components), 2)  # propulsion root + motor
        self.assertEqual(components[0]["id"], _PROPULSION_ID)
        motor = components[1]
        self.assertEqual(motor["type"], "org.setuav.core:motor")
        self.assertEqual(motor["parent"], _PROPULSION_ID)
        self.assertIs(self.api.current_selection, motor)
        self.assertIn(f"Added {motor['name']} to Propulsion", self.statuses[-1][0])

        self.assertIn("mass", motor)
        self.assertGreater(motor["mass"], 0.0)
        self.assertIn("transform", motor)
        self.assertIn("position", motor["transform"])
        self.assertIn("envelope", motor)
        self.assertIn("size_mm", motor["envelope"])

        # Undo adding motor
        self.api.undo()
        self.assertEqual(len(self.project.data["components"]), 1)
        self.assertEqual(self.project.data["components"][0]["id"], _PROPULSION_ID)

        # Redo adding motor
        self.api.redo()
        self.assertEqual(len(self.project.data["components"]), 2)

    def test_created_components_have_mass_transform_envelope_and_parent(self) -> None:
        self.controller.add_propulsion_system()
        for kind in ("battery", "esc", "motor", "propeller", "rotor"):
            self.controller.add_component(kind)

        propulsion_comps = [c for c in self.project.data["components"] if c["id"] != _PROPULSION_ID]
        self.assertEqual(len(propulsion_comps), 5)

        motor_id = next(c["id"] for c in propulsion_comps if c["type"] == "org.setuav.core:motor")
        for comp in propulsion_comps:
            expected_parent = (
                motor_id
                if comp["type"]
                in {
                    "org.setuav.core:propeller",
                    "org.setuav.core:rotor",
                }
                else _PROPULSION_ID
            )
            self.assertEqual(comp["parent"], expected_parent)
            self.assertIn("mass", comp)
            self.assertIsInstance(comp["mass"], (int, float))
            self.assertGreater(comp["mass"], 0.0)

            self.assertIn("transform", comp)
            self.assertIsInstance(comp["transform"], dict)
            self.assertIn("position", comp["transform"])
            self.assertIn("rotation", comp["transform"])

            self.assertIn("envelope", comp)
            self.assertIsInstance(comp["envelope"], dict)
            self.assertIn(comp["envelope"]["shape"], {"box", "cylinder"})
            self.assertIn("size_mm", comp["envelope"])
            self.assertIn("offset_mm", comp["envelope"])

    def test_duplicate_component_gets_unique_ids_and_names(self) -> None:
        self.controller.add_propulsion_system()
        self.controller.add_component("motor")
        self.controller.add_component("motor")

        motors = [
            c for c in self.project.data["components"] if c.get("type") == "org.setuav.core:motor"
        ]
        name = motors[0]["name"]
        self.assertEqual(
            [(item["id"], item["name"]) for item in motors],
            [
                ("motor", name),
                ("motor-2", f"{name} 2"),
            ],
        )

    def test_propeller_is_child_of_its_motor(self) -> None:
        self.controller.add_propulsion_system()
        self.controller.add_component("motor")
        self.controller.add_component("propeller")

        propeller = self.controller._find_component("propeller")
        assert propeller is not None
        self.assertEqual(propeller["parent"], "motor")
        self.assertNotIn("attach_to", propeller)

    def test_propeller_requires_a_motor(self) -> None:
        self.controller.add_propulsion_system()
        self.controller.add_component("propeller")
        self.assertIsNone(self.controller._find_component("propeller"))
        self.assertIn("Add a motor", self.statuses[-1][0])

    def test_propeller_uses_selected_motor_when_several_exist(self) -> None:
        self.controller.add_propulsion_system()
        self.controller.add_component("motor")
        self.controller.add_component("motor")

        self.api.set_selection(self.project.data["components"][0])
        self.controller.add_component("propeller")
        self.assertIsNone(self.controller._find_component("propeller"))
        self.assertIn("Select the motor", self.statuses[-1][0])

        self.api.set_selection(self.controller._find_component("motor"))
        self.controller.add_component("propeller")
        propeller = self.controller._find_component("propeller")
        assert propeller is not None
        self.assertEqual(propeller["parent"], "motor")

    def test_editability_validation_reports_each_invalid_project_state(self) -> None:
        self.api._project = None
        self.assertFalse(self.controller._can_edit_project())
        self.assertFalse(self.controller._require_editable_project())
        self.assertIn("Open a project", self.statuses[-1][0])

        self.api._host.set_project(self.project)
        self.project.read_only = True
        self.assertFalse(self.controller._can_edit_project())
        self.assertFalse(self.controller._require_editable_project())
        self.assertEqual(self.statuses[-1][0], "The project is read-only")

        self.project.read_only = False
        self.project.data["components"] = "invalid"
        self.assertFalse(self.controller._require_editable_project())
        self.assertEqual(self.statuses[-1][1], "error")

    def test_defaults_identity_and_lookup_helpers(self) -> None:
        defaults = {
            kind: self.controller._new_component(kind, kind)
            for kind in ("battery", "esc", "motor", "propeller", "rotor")
        }
        self.assertEqual(defaults["battery"]["parameters"]["cell_count"], 6)
        self.assertEqual(defaults["esc"]["parameters"]["continuous_current"], 50.0)
        self.assertEqual(defaults["motor"]["parameters"]["kv"], 900.0)
        self.assertEqual(defaults["propeller"]["name"], "Propeller")

        self.api._project = None
        self.assertEqual(self.controller._unique_identity("id", "Name"), ("id", "Name"))
        self.assertIsNone(self.controller._find_component("missing"))
        self.api._host.set_project(self.project)
        self.project.data = {
            "components": ["invalid", {"id": "id"}, {"id": "id-2", "name": "Name 2"}],
        }
        self.assertEqual(self.controller._unique_identity("fresh", "Fresh"), ("fresh", "Fresh"))
        self.assertEqual(self.controller._unique_identity("id", "Name"), ("id-3", "Name 3"))
        self.assertIsNone(self.controller._find_component("missing"))
        found = self.controller._find_component("id")
        assert found is not None
        self.assertEqual(found["id"], "id")

    def test_new_battery_is_a_lipo_pack_with_derived_cell_properties(self) -> None:
        battery = self.controller._new_component("battery", "battery")
        params = battery["parameters"]

        self.assertEqual(set(params), {f.key for f in BatteryModel.get_fields()})
        self.assertEqual(params["chemistry"], "LiPo")
        self.assertTrue(all(params[key] is None for key in BATTERY_OVERRIDES))
        pack = battery_pack(params)
        self.assertEqual(battery["mass"], pack.mass_g)
        self.assertEqual(
            pack.series * pack.parallel, params["cell_count"] * params["parallel_count"]
        )


if __name__ == "__main__":
    unittest.main()
