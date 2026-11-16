"""Tests for the commands that add propulsors and battery packs."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PySide6.QtWidgets import QDialog

from plugins.electrical_propulsion.creation import PropulsionCreationController
from plugins.electrical_propulsion.database import get_motor_database, get_propeller_database
from plugins.electrical_propulsion.models import BatteryModel, PropulsorModel
from plugins.electrical_propulsion.models.battery import BATTERY_OVERRIDES, battery_pack
from plugins.electrical_propulsion.models.propulsor import PROPULSOR_TYPE, propulsor_mass
from setuav_studio.api import StudioAPI, ToolbarContribution, ToolbarMenuItemContribution
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


def _enabled(contribution: ToolbarContribution | ToolbarMenuItemContribution) -> bool:
    assert contribution.enabled_when is not None
    return contribution.enabled_when()


class _CatalogDialog:
    """Catalog dialog stand-in that accepts the first entry unless told to cancel."""

    cancel: str | None = None

    def __init__(self, component_type: str, *args: object, **kwargs: object) -> None:
        self.component_type = component_type
        self.selected_motor: Any = None
        self.selected_propeller: Any = None
        if component_type == "motor":
            db = get_motor_database()
            self.selected_motor = db.get(db.list_motors()[0])
        else:
            db = get_propeller_database()
            self.selected_propeller = db.get(db.list_propellers()[0])

    def exec(self) -> QDialog.DialogCode:
        if self.component_type == self.cancel:
            return QDialog.DialogCode.Rejected
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
        _CatalogDialog.cancel = None
        dialog_patch = patch(
            "plugins.electrical_propulsion.catalog_dialog.ComponentCatalogDialog",
            _CatalogDialog,
        )
        dialog_patch.start()
        self.addCleanup(dialog_patch.stop)

    def test_toolbar_menu_adds_propulsors_and_batteries(self) -> None:
        (contribution,) = self.controller.contributions()
        self.assertEqual(contribution.id, PropulsionCreationController.toolbar_id)
        self.assertEqual(
            [item.title for item in contribution.menu_items], ["Add Propulsor", "Add Battery"]
        )
        self.assertTrue(_enabled(contribution))
        for item in contribution.menu_items:
            self.assertTrue(_enabled(item))
            item.callback()
        self.assertEqual(
            [c["type"] for c in self.project.data["components"]],
            [PROPULSOR_TYPE, "org.setuav.core:battery"],
        )

        self.project.read_only = True
        self.assertFalse(_enabled(contribution))

    def test_propulsor_takes_its_motor_and_propeller_from_the_catalogs(self) -> None:
        self.controller.add_propulsor()

        (propulsor,) = self.project.data["components"]
        motor_db = get_motor_database()
        motor = motor_db.get(motor_db.list_motors()[0])
        propeller_db = get_propeller_database()
        propeller = propeller_db.get(propeller_db.list_propellers()[0])
        assert motor is not None and propeller is not None
        params = propulsor["parameters"]
        self.assertEqual(set(params), {f.key for f in PropulsorModel.get_scalar_fields()})
        self.assertEqual(propulsor["type"], PROPULSOR_TYPE)
        self.assertEqual(propulsor["model"], motor.name)
        self.assertEqual(params["motor_kv"], float(motor.kv))
        self.assertEqual(params["motor_resistance"], float(motor.resistance))
        self.assertEqual(params["propeller_catalog_id"], propeller.metadata.id)
        self.assertEqual(params["propeller_diameter"], round(propeller.diameter_m * 1000.0, 1))
        self.assertEqual(propulsor["mass"], propulsor_mass(params))
        self.assertIs(self.api.current_selection, propulsor)
        self.assertEqual(self.statuses[-1][:2], (f"Added {propulsor['name']}", "success"))

        self.api.undo()
        self.assertEqual(self.project.data["components"], [])
        self.api.redo()
        self.assertEqual(len(self.project.data["components"]), 1)

    def test_cancelling_either_catalog_adds_nothing(self) -> None:
        for kind in ("motor", "propeller"):
            with self.subTest(cancel=kind):
                _CatalogDialog.cancel = kind
                self.controller.add_propulsor()
                self.assertEqual(self.project.data["components"], [])

    def test_added_components_get_unique_ids_and_names(self) -> None:
        for _ in range(2):
            self.controller.add_propulsor()
            self.controller.add_battery()

        identities = [(c["id"], c["name"]) for c in self.project.data["components"]]
        name = identities[0][1]
        self.assertEqual(
            identities,
            [
                ("propulsor", name),
                ("battery", "Battery"),
                ("propulsor-2", f"{name} 2"),
                ("battery-2", "Battery 2"),
            ],
        )
        for component in self.project.data["components"]:
            self.assertEqual(set(component["transform"]), {"position", "rotation"}, component["id"])
            self.assertIn(component["envelope"]["shape"], {"box", "cylinder"})

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
