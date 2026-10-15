"""Tests for geometry component creation commands."""

from __future__ import annotations

import unittest
from pathlib import Path

from plugins.geometry.creation import AirframeCreationController
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
            {"components": [], "assemblies": []},
        )
        self.api._host.set_project(self.project)
        self.controller = AirframeCreationController(self.api)

    def test_toolbar_contributions_dispatch_and_predicates(self) -> None:
        contributions = self.controller.contributions()
        self.assertEqual(len(contributions), 4)
        airframe_act, fuse_act, wing_act, cs_act = contributions

        self.assertEqual(
            tuple(c.id for c in contributions),
            AirframeCreationController.toolbar_ids,
        )

        # Before airframe:
        self.assertTrue(airframe_act.enabled_when())
        self.assertFalse(fuse_act.enabled_when())
        self.assertFalse(wing_act.enabled_when())
        self.assertFalse(cs_act.enabled_when())
        for item in wing_act.menu_items:
            self.assertFalse(item.enabled_when())

        # Add airframe
        self.controller.add_airframe()
        self.assertFalse(airframe_act.enabled_when())
        self.assertTrue(fuse_act.enabled_when())
        self.assertTrue(wing_act.enabled_when())
        for item in wing_act.menu_items:
            self.assertTrue(item.enabled_when())
        # Control surface still false until wing is selected
        self.assertFalse(cs_act.enabled_when())

    def test_cannot_add_geometry_without_airframe(self) -> None:
        self.controller.add_fuselage()
        self.assertEqual(len(self.project.data["components"]), 0)
        self.assertIn("Please add an Airframe before adding geometry", self.statuses[-1][0])

        self.controller.add_lifting_surface("main-wing")
        self.assertEqual(len(self.project.data["components"]), 0)
        self.assertIn("Please add an Airframe before adding geometry", self.statuses[-1][0])

    def test_cannot_add_multiple_airframes(self) -> None:
        self.controller.add_airframe()
        self.assertEqual(len(self.project.data["components"]), 1)
        self.assertEqual(self.project.data["components"][0]["id"], "airframe")

        self.controller.add_airframe()
        self.assertEqual(len(self.project.data["components"]), 1)
        self.assertIn("Airframe already exists", self.statuses[-1][0])

    def test_add_fuselage_allows_adding_sections_and_updates_table(self) -> None:
        from plugins.geometry.editors.fuselage import FuselageEditor

        self.controller.add_airframe()
        self.controller.add_fuselage()
        fuse = next(
            c
            for c in self.project.data["components"]
            if c.get("type") == "org.setuav.core:fuselage"
        )
        self.assertEqual(fuse["parent"], "airframe")
        editor = FuselageEditor(self.api, fuse)
        self.assertEqual(editor.sections_table.rowCount(), 3)
        self.assertEqual(editor.segments_table.item(0, 1).text(), "3")

        editor._add_section()
        self.assertEqual(editor.sections_table.rowCount(), 4)
        self.assertEqual(len(editor._sections()), 4)
        self.assertEqual(editor.segments_table.item(0, 1).text(), "4")

    def test_add_fuselage_populates_mass_transform_envelope(self) -> None:
        self.controller.add_airframe()
        self.controller.add_fuselage()
        fuse = next(
            c
            for c in self.project.data["components"]
            if c.get("type") == "org.setuav.core:fuselage"
        )
        self._assert_valid_physical_contract(fuse)
        self.assertEqual(fuse["envelope"]["shape"], "trapezoid")
        self.assertEqual(fuse["mass"], 350.0)
        self.assertEqual(fuse["parent"], "airframe")

    def test_add_lifting_surface_presets_populate_mass_transform_envelope(self) -> None:
        self.controller.add_airframe()
        for preset in ("main-wing", "horizontal-tail", "vertical-tail", "generic"):
            self.controller.add_lifting_surface(preset)

        wings = [
            c
            for c in self.project.data["components"]
            if c.get("type") == "org.setuav.core:lifting-surface"
        ]
        self.assertEqual(len(wings), 4)

        for comp in wings:
            self._assert_valid_physical_contract(comp)
            self.assertEqual(comp["envelope"]["shape"], "box")
            self.assertEqual(comp["parent"], "airframe")

    def test_add_control_surface_populates_mass_transform_envelope(self) -> None:
        self.controller.add_airframe()
        self.controller.add_lifting_surface("main-wing")
        wing = next(
            c
            for c in self.project.data["components"]
            if c.get("type") == "org.setuav.core:lifting-surface"
        )
        self.api.set_selection(wing)

        self.controller.add_control_surface("aileron")
        cs = next(
            c
            for c in self.project.data["components"]
            if c.get("type") == "org.setuav.core:control-surface"
        )
        self._assert_valid_physical_contract(cs)
        self.assertEqual(cs["mass"], 25.0)
        self.assertEqual(cs["envelope"]["shape"], "box")
        self.assertEqual(cs["parent"], wing["id"])
        self.assertNotIn("attach_to", cs)

    def test_editor_add_control_surface_populates_mass_transform_envelope(self) -> None:
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor

        self.controller.add_airframe()
        self.controller.add_lifting_surface("main-wing")
        wing = next(
            c
            for c in self.project.data["components"]
            if c.get("type") == "org.setuav.core:lifting-surface"
        )
        editor = LiftingSurfaceEditor(self.api, wing)
        editor._add_control_surface()
        cs = next(
            c
            for c in self.project.data["components"]
            if c.get("type") == "org.setuav.core:control-surface"
        )
        self._assert_valid_physical_contract(cs)
        self.assertEqual(cs["mass"], 25.0)
        self.assertEqual(cs["envelope"]["shape"], "box")
        self.assertEqual(cs["parent"], wing["id"])

    def _assert_valid_physical_contract(self, comp: dict) -> None:
        self.assertIn("mass", comp)
        self.assertIsInstance(comp["mass"], (int, float))
        self.assertGreater(comp["mass"], 0.0)

        self.assertIn("transform", comp)
        self.assertIsInstance(comp["transform"], dict)
        self.assertIn("position", comp["transform"])
        self.assertIn("rotation", comp["transform"])

        self.assertIn("envelope", comp)
        self.assertIsInstance(comp["envelope"], dict)
        self.assertIn(comp["envelope"]["shape"], {"box", "trapezoid", "cylinder"})
        self.assertIn("size_mm", comp["envelope"])
        self.assertIn("offset_mm", comp["envelope"])


if __name__ == "__main__":
    unittest.main()
