"""The values formulas read from airframe components match what the editors show."""

from __future__ import annotations

import unittest

from plugins.geometry.engine.lifting_surface_layout import layout_planform
from plugins.geometry.plugin import AirframeDesignPlugin
from setuav_studio.api import StudioAPI
from setuav_studio.project import open_project
from setuav_studio.utilities.transform import get_local_transform
from tests._common import TEST_PROJECT_PATH, get_qapp


class AirframeFormulaScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        plugin = AirframeDesignPlugin()
        plugin.activate(self.api)
        self.addCleanup(plugin.deactivate, self.api)
        self.project = open_project(TEST_PROJECT_PATH)
        self.api._host.set_project(self.project)
        self.scope = self.project.get_scope(api=self.api)

    def test_lifting_surface_values_match_the_planform_table(self) -> None:
        wing = self.project.get_component("main-wing")
        assert wing is not None
        geometry = wing["parameters"]["geometry"]
        (_x, y_offset, _z), _rotation = get_local_transform(wing)
        table = layout_planform(geometry, symmetric=geometry["mirror"], y_offset=y_offset)

        model = self.scope["main_wing"]
        self.assertAlmostEqual(model.planform_area, table["area"])  # dm²
        self.assertAlmostEqual(model.average_chord, table["ave_chord"])
        self.assertAlmostEqual(model.mac, table["mac"])
        self.assertAlmostEqual(self.scope["main_wing_planform_area"], 32.0)

    def test_fuselage_section_size_comes_from_its_outline(self) -> None:
        fuselage = self.project.get_component("fuselage")
        assert fuselage is not None
        sections = fuselage["parameters"]["geometry"]["segments"][0]["sections"]
        sections[0]["profile"] = {"type": "circle", "diameter": 30.0}

        scope = self.project.get_scope(api=self.api)
        self.assertAlmostEqual(scope["fuselage_section_0_width"], 30.0, places=6)
        self.assertAlmostEqual(scope["fuselage_section_0_height"], 30.0, places=6)
        self.assertAlmostEqual(scope["fuselage_section_1_width"], 40.0, places=6)


if __name__ == "__main__":
    unittest.main()
