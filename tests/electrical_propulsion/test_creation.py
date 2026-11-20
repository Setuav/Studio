"""Tests for the commands that add propulsors and battery packs."""

from __future__ import annotations

import unittest
from pathlib import Path

from plugins.electrical_propulsion.creation import PropulsionCreationController
from plugins.electrical_propulsion.models import BatteryModel, PropulsorModel
from plugins.electrical_propulsion.models.battery import BATTERY_OVERRIDES, battery_pack
from plugins.electrical_propulsion.models.propulsor import PROPULSOR_TYPE
from setuav_studio.api import StudioAPI, ToolbarContribution
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


def _enabled(contribution: ToolbarContribution) -> bool:
    assert contribution.enabled_when is not None
    return contribution.enabled_when()


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

    def test_toolbar_buttons_add_propulsors_and_batteries(self) -> None:
        contributions = self.controller.contributions()
        self.assertEqual(
            tuple(c.id for c in contributions), PropulsionCreationController.toolbar_ids
        )
        self.assertEqual([c.title for c in contributions], ["Add Propulsor", "Add Battery"])
        for contribution in contributions:
            self.assertTrue(_enabled(contribution))
            assert contribution.callback is not None
            contribution.callback()
        self.assertEqual(
            [c["type"] for c in self.project.data["components"]],
            [PROPULSOR_TYPE, "org.setuav.core:battery"],
        )

        self.project.read_only = True
        self.assertFalse(any(_enabled(c) for c in contributions))

    def test_new_propulsor_waits_for_its_motor_and_propeller(self) -> None:
        self.controller.add_propulsor()

        (propulsor,) = self.project.data["components"]
        params = propulsor["parameters"]
        self.assertEqual(set(params), {f.key for f in PropulsorModel.get_scalar_fields()})
        self.assertEqual(propulsor["type"], PROPULSOR_TYPE)
        self.assertEqual(propulsor["name"], "Propulsor")
        self.assertTrue(all(value is None for value in params.values()))
        self.assertEqual(propulsor["mass"], 0.0)
        self.assertIs(self.api.current_selection, propulsor)
        self.assertEqual(self.statuses[-1][:2], ("Added Propulsor", "success"))

        self.api.undo()
        self.assertEqual(self.project.data["components"], [])
        self.api.redo()
        self.assertEqual(len(self.project.data["components"]), 1)

    def test_added_components_get_unique_ids_and_names(self) -> None:
        for _ in range(2):
            self.controller.add_propulsor()
            self.controller.add_battery()

        identities = [(c["id"], c["name"]) for c in self.project.data["components"]]
        self.assertEqual(
            identities,
            [
                ("propulsor", "Propulsor"),
                ("battery", "Battery"),
                ("propulsor-2", "Propulsor 2"),
                ("battery-2", "Battery 2"),
            ],
        )
        for component in self.project.data["components"]:
            self.assertEqual(set(component["transform"]), {"position", "rotation"}, component["id"])

    def test_new_battery_is_a_lipo_pack_with_derived_cell_properties(self) -> None:
        self.controller.add_battery()
        (battery,) = self.project.data["components"]
        params = battery["parameters"]

        self.assertEqual(set(params), {f.key for f in BatteryModel.get_fields()})
        self.assertEqual(params["chemistry"], "LiPo")
        self.assertTrue(all(params[key] is None for key in BATTERY_OVERRIDES))
        pack = battery_pack(params)
        self.assertEqual(battery["mass"], pack.mass_g)
        self.assertEqual(
            pack.series * pack.parallel, params["cell_count"] * params["parallel_count"]
        )

    def test_editability_validation_reports_each_invalid_project_state(self) -> None:
        self.api._project = None
        self.assertFalse(self.controller._can_edit_project())
        self.controller.add_battery()
        self.assertIn("Open a project", self.statuses[-1][0])

        self.api._host.set_project(self.project)
        self.project.read_only = True
        self.controller.add_propulsor()
        self.assertEqual(self.statuses[-1][0], "The project is read-only")
        self.assertEqual(self.project.data["components"], [])


if __name__ == "__main__":
    unittest.main()
