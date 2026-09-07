"""Unit tests for airframe concept geometry generator."""

from __future__ import annotations

import unittest
from pathlib import Path

from plugins.geometry import PLUGIN as geom_plugin
from plugins.geometry.concepts import (
    CONCEPT_PRESETS,
    CONVENTIONAL_TRACTOR,
    FLYING_WING,
    TALON_PUSHER,
    TWIN_BOOM_PUSHER,
)
from plugins.geometry.concepts.generator import (
    build_fuselage_component,
    build_main_wing_component,
    build_tail_components,
    generate_airframe_components,
)
from setuav_studio.project.document import ProjectDocument


class ConceptGeneratorTests(unittest.TestCase):
    def test_talon_pusher_geometry_generation(self) -> None:
        cfg = TALON_PUSHER.to_dict()
        bundle = generate_airframe_components(cfg)

        comps = bundle["components"]
        comp_ids = [c["id"] for c in comps]
        self.assertIn("fuselage", comp_ids)
        self.assertIn("main-wing", comp_ids)
        self.assertIn("v-tail", comp_ids)

        asms = bundle["assemblies"]
        self.assertEqual(len(asms), 1)
        self.assertEqual(asms[0]["type"], "org.setuav.core:structural-system")
        self.assertEqual(set(asms[0]["members"]), set(comp_ids))

        doc = ProjectDocument(
            path=Path("/tmp/test_talon.setuav"),
            kind="json",
            data={"components": comps, "assemblies": asms, "parameters": bundle["parameters"]},
        )
        geom_data = geom_plugin.get_geometry(doc)
        self.assertGreater(len(geom_data.lofts), 0)

    def test_conventional_tractor_geometry_generation(self) -> None:
        cfg = CONVENTIONAL_TRACTOR.to_dict()
        bundle = generate_airframe_components(cfg)

        comp_ids = [c["id"] for c in bundle["components"]]
        self.assertIn("fuselage", comp_ids)
        self.assertIn("main-wing", comp_ids)
        self.assertIn("horizontal-tail", comp_ids)
        self.assertIn("vertical-tail", comp_ids)

        doc = ProjectDocument(
            path=Path("/tmp/test_conv.setuav"),
            kind="json",
            data={"components": bundle["components"], "assemblies": bundle["assemblies"], "parameters": bundle["parameters"]},
        )
        geom_data = geom_plugin.get_geometry(doc)
        self.assertGreater(len(geom_data.lofts), 0)

    def test_twin_boom_pusher_geometry_generation(self) -> None:
        cfg = TWIN_BOOM_PUSHER.to_dict()
        bundle = generate_airframe_components(cfg)

        comp_ids = [c["id"] for c in bundle["components"]]
        self.assertIn("fuselage", comp_ids)
        self.assertIn("main-wing", comp_ids)
        self.assertIn("boom-right", comp_ids)
        self.assertIn("boom-left", comp_ids)
        self.assertIn("horizontal-tail", comp_ids)
        self.assertIn("fin-right", comp_ids)
        self.assertIn("fin-left", comp_ids)

        doc = ProjectDocument(
            path=Path("/tmp/test_twin.setuav"),
            kind="json",
            data={"components": bundle["components"], "assemblies": bundle["assemblies"], "parameters": bundle["parameters"]},
        )
        geom_data = geom_plugin.get_geometry(doc)
        self.assertGreater(len(geom_data.lofts), 0)

    def test_flying_wing_geometry_generation(self) -> None:
        cfg = FLYING_WING.to_dict()
        bundle = generate_airframe_components(cfg)

        comp_ids = [c["id"] for c in bundle["components"]]
        self.assertIn("fuselage", comp_ids)
        self.assertIn("main-wing", comp_ids)
        self.assertIn("winglet-right", comp_ids)
        self.assertIn("winglet-left", comp_ids)

        doc = ProjectDocument(
            path=Path("/tmp/test_fw.setuav"),
            kind="json",
            data={"components": bundle["components"], "assemblies": bundle["assemblies"], "parameters": bundle["parameters"]},
        )
        geom_data = geom_plugin.get_geometry(doc)
        self.assertGreater(len(geom_data.lofts), 0)


if __name__ == "__main__":
    unittest.main()
