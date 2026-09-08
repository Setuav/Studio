"""Tests for geometry component creation commands."""

from __future__ import annotations

import unittest
from pathlib import Path

from plugins.geometry.creation import GeometryCreationController
from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class GeometryCreationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.project = ProjectDocument(
            Path("geometry-creation.json"),
            "json",
            {"components": [], "assemblies": []},
        )
        self.api._host.set_project(self.project)
        self.controller = GeometryCreationController(self.api)

    def test_add_starter_airframe_populates_mass_transform_envelope(self) -> None:
        self.controller.add_structural_system()
        components = self.project.data.get("components", [])
        self.assertEqual(len(components), 2)

        for comp in components:
            self._assert_valid_physical_contract(comp)

    def test_add_fuselage_populates_mass_transform_envelope(self) -> None:
        self.controller.add_fuselage()
        components = self.project.data.get("components", [])
        self.assertEqual(len(components), 1)
        comp = components[0]
        self._assert_valid_physical_contract(comp)
        self.assertEqual(comp["envelope"]["shape"], "trapezoid")
        self.assertEqual(comp["mass"], 350.0)

    def test_add_lifting_surface_presets_populate_mass_transform_envelope(self) -> None:
        for preset in ("main-wing", "horizontal-tail", "vertical-tail", "generic"):
            self.controller.add_lifting_surface(preset)

        components = self.project.data.get("components", [])
        self.assertEqual(len(components), 4)

        for comp in components:
            self._assert_valid_physical_contract(comp)
            self.assertEqual(comp["envelope"]["shape"], "box")

    def test_add_control_surface_populates_mass_transform_envelope(self) -> None:
        self.controller.add_lifting_surface("main-wing")
        wing = self.project.data["components"][0]
        self.api.set_selection(wing)

        self.controller.add_control_surface("aileron")
        components = self.project.data.get("components", [])
        self.assertEqual(len(components), 2)
        cs = components[1]
        self._assert_valid_physical_contract(cs)
        self.assertEqual(cs["mass"], 25.0)
        self.assertEqual(cs["envelope"]["shape"], "box")

    def test_editor_add_control_surface_populates_mass_transform_envelope(self) -> None:
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor

        self.controller.add_lifting_surface("main-wing")
        wing = self.project.data["components"][0]
        editor = LiftingSurfaceEditor(self.api, wing)
        editor._add_control_surface()
        components = self.project.data.get("components", [])
        self.assertEqual(len(components), 2)
        cs = components[1]
        self._assert_valid_physical_contract(cs)
        self.assertEqual(cs["mass"], 25.0)
        self.assertEqual(cs["envelope"]["shape"], "box")

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
