"""Unit tests for the exact envelopes stored on Debug plugin primitives."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

from plugins.debug import DebugPlugin
from plugins.debug.components import (
    TYPE_DEBUG_ARROW,
    TYPE_DEBUG_LINE,
    TYPE_DEBUG_PLANE,
    TYPE_DEBUG_POINT,
    TYPE_DEBUG_RING,
    TYPE_DEBUG_TRIANGLE,
    add_debug_component,
    create_box_component,
    create_cylinder_component,
    create_loft_component,
)
from plugins.debug.components.common import compute_debug_envelope, parse_color_rgba
from setuav_studio.api import StudioAPI
from setuav_studio.project import create_project
from setuav_studio.utilities.envelope import (
    is_geometry_envelope,
    resolve_component_aggregate_envelope,
)


class TestDebugPrimitiveEnvelopes(unittest.TestCase):
    def test_box_envelope_is_exact(self) -> None:
        box = create_box_component("box-1", "Box").raw_data
        box["parameters"].update({"length": 200.0, "width": 150.0, "height": 100.0})
        env = compute_debug_envelope(box)
        assert env is not None
        self.assertEqual(env["shape"], "box")
        self.assertEqual(env["size_mm"], {"x": 200.0, "y": 150.0, "z": 100.0})
        self.assertEqual(env["offset_mm"], {"x": 0.0, "y": 0.0, "z": 0.0})
        self.assertAlmostEqual(env["volume_mm3"], 200.0 * 150.0 * 100.0)
        self.assertAlmostEqual(env["unit_inertia"]["ixx"], (150.0**2 + 100.0**2) / 12.0 / 1e6)

    def test_cylinder_envelope_follows_alignment_axis(self) -> None:
        cyl = create_cylinder_component("cyl-1", "Cylinder").raw_data
        cyl["parameters"].update({"radius": 50.0, "length": 200.0, "axis": "Z"})
        env = compute_debug_envelope(cyl)
        assert env is not None
        self.assertEqual(env["shape"], "cylinder")
        self.assertEqual(env["size_mm"], {"x": 100.0, "y": 100.0, "z": 200.0})
        self.assertAlmostEqual(env["volume_mm3"], math.pi * 50.0**2 * 200.0, delta=0.1)
        axial = 50.0**2 / 2.0 / 1e6
        transverse = (200.0**2 / 12.0 + 50.0**2 / 4.0) / 1e6
        self.assertAlmostEqual(env["unit_inertia"]["izz"], axial)
        self.assertAlmostEqual(env["unit_inertia"]["ixx"], transverse)
        self.assertAlmostEqual(env["unit_inertia"]["iyy"], transverse)

    def test_colors_are_hex_strings(self) -> None:
        self.assertEqual(parse_color_rgba("#FF0080"), (1.0, 0.0, 128 / 255.0, 1.0))
        for invalid in ("", "rgb(255, 0, 0)", "#F08", "#GG0000"):
            with self.assertRaisesRegex(ValueError, "not a #RRGGBB hex color"):
                parse_color_rgba(invalid)

    def test_loft_envelope_is_integrated_from_its_stations(self) -> None:
        loft = create_loft_component("loft-1", "Loft").raw_data
        env = compute_debug_envelope(loft)
        assert env is not None
        self.assertTrue(is_geometry_envelope(env))
        self.assertGreater(env["volume_mm3"], 0.0)
        self.assertEqual(len(env["sections"]), 3)

    def test_primitives_without_volume_have_no_envelope(self) -> None:
        for ctype in (
            TYPE_DEBUG_ARROW,
            TYPE_DEBUG_LINE,
            TYPE_DEBUG_PLANE,
            TYPE_DEBUG_POINT,
            TYPE_DEBUG_RING,
            TYPE_DEBUG_TRIANGLE,
        ):
            with self.subTest(ctype):
                self.assertIsNone(compute_debug_envelope({"type": ctype, "parameters": {}}))


class TestDebugEnvelopeSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.api = StudioAPI()
        self.api._host.set_project(create_project(Path(self.temp_dir.name) / "envelope.suav"))
        self.plugin = DebugPlugin()
        self.plugin.activate(self.api)

    def tearDown(self) -> None:
        self.plugin.deactivate(self.api)
        self.temp_dir.cleanup()

    def _add(self, factory: Any, base_id: str, name: str) -> dict[str, Any]:
        created = add_debug_component(self.api, factory, base_id, name)
        assert isinstance(created, dict)
        return created

    def test_created_primitive_stores_its_envelope(self) -> None:
        box = self._add(create_box_component, "box", "Box")
        self.assertEqual(box["envelope"], compute_debug_envelope(box))

    def test_edited_primitive_envelope_follows_parameters_and_undo(self) -> None:
        box = self._add(create_box_component, "box", "Box")
        original = dict(box["envelope"]["size_mm"])

        def change() -> None:
            box["parameters"]["length"] = 500.0

        self.api.edit_component(box, "Set length", change)
        self.assertEqual(box["envelope"]["size_mm"]["x"], 500.0)

        self.api.undo()
        self.assertEqual(box["envelope"]["size_mm"], original)

    def test_debug_envelope_unites_a_component_with_its_subparts(self) -> None:
        box = self._add(create_box_component, "box", "Box")
        cyl = self._add(create_cylinder_component, "cylinder", "Cylinder")

        def change() -> None:
            cyl["attach_to"] = box["id"]
            cyl["transform"]["position"]["x"] = 1000.0

        self.api.edit_component(cyl, "Attach cylinder", change)

        aggregate = resolve_component_aggregate_envelope(box, self.api.project, {cyl["type"]})
        # The union reaches from the box's aft face to the cylinder 1 m away
        self.assertGreater(aggregate["size_mm"]["x"], 1000.0)
        self.assertAlmostEqual(
            aggregate["volume_mm3"],
            box["envelope"]["volume_mm3"] + cyl["envelope"]["volume_mm3"],
            delta=1.0,
        )


if __name__ == "__main__":
    unittest.main()
