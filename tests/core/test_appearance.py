"""Component colors: the model, the 3D surfaces, and the Transform tab."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from setuav_studio.api import StudioAPI
from setuav_studio.model.appearance import DEFAULT_COMPONENT_COLOR, component_color, hex_to_rgb
from setuav_studio.project import create_project
from setuav_studio.ui.viewport import FACE_COLORED, FACE_MONOCHROME
from setuav_studio.ui.viewport.primitives import BoxPrimitive, RingPrimitive
from setuav_studio.ui.viewport.primitives_mesh import build_primitive_solid_vertices
from tests._common import get_qapp
from tests.core.test_viewport import MockRenderer


class ComponentColorModelTests(unittest.TestCase):
    def test_default_and_own_component_colors(self) -> None:
        wing = {"id": "wing", "color": "#3366cc"}
        plain = {"id": "plain"}
        components = {"wing": wing, "plain": plain}

        self.assertEqual(component_color(plain, components), DEFAULT_COMPONENT_COLOR)
        self.assertEqual(component_color(wing, components), "#3366CC")
        with self.assertRaises(ValueError):
            component_color({"id": "bad", "color": "red"}, components)


class SurfaceColorTests(unittest.TestCase):
    def test_component_color_paints_surfaces_unless_monochrome(self) -> None:
        box = BoxPrimitive(center=(0, 0, 0), size=(1, 1, 1), color=(1.0, 0.0, 0.0, 1.0))
        ring = RingPrimitive(center=(0, 0, 0), normal=(1, 0, 0), radius=1.0)
        body = (0.2, 0.4, 0.6)

        colored = build_primitive_solid_vertices([box, ring], FACE_COLORED, body_color=body)
        mono = build_primitive_solid_vertices([box], FACE_MONOCHROME, body_color=body)

        # Each vertex is position (3), normal (3), color (3).
        self.assertEqual(tuple(round(v, 6) for v in colored[6:9]), body)
        self.assertNotEqual(tuple(round(v, 6) for v in mono[6:9]), body)

    def test_viewport_gives_the_renderer_every_component_color(self) -> None:
        get_qapp()
        from setuav_studio.ui.viewport import StudioViewport

        api = StudioAPI()
        with tempfile.TemporaryDirectory() as tmpdir:
            project = create_project(Path(tmpdir) / "plane.suav")
            project.data["components"] = [{"id": "wing"}, {"id": "fuse", "color": "#102030"}]
            api._host.set_project(project)
            renderer = MockRenderer()
            StudioViewport(api=api, renderer=renderer)

            self.assertEqual(
                renderer.component_colors,
                {"wing": hex_to_rgb(DEFAULT_COMPONENT_COLOR), "fuse": hex_to_rgb("#102030")},
            )
            api.set_component_color("wing", "#FF8800")
            self.assertEqual(renderer.component_colors["wing"], hex_to_rgb("#FF8800"))


class TransformTabColorTests(unittest.TestCase):
    def test_appearance_shows_the_color_and_resets_it(self) -> None:
        get_qapp()
        from setuav_studio.ui.editor import TransformEditor

        api = StudioAPI()
        with tempfile.TemporaryDirectory() as tmpdir:
            project = create_project(Path(tmpdir) / "plane.suav")
            project.data["components"] = [{"id": "wing", "name": "Wing"}]
            api._host.set_project(project)
            wing = project.get_component("wing")
            assert wing is not None
            editor = TransformEditor(api, wing)
            self.addCleanup(editor.deleteLater)

            self.assertEqual(editor.color_button.text(), DEFAULT_COMPONENT_COLOR)
            self.assertFalse(editor.default_color_button.isEnabled())

            api.set_component_color("wing", "#00AA55")
            self.assertEqual(editor.color_button.text(), "#00AA55")
            self.assertTrue(editor.default_color_button.isEnabled())

            editor.default_color_button.click()
            self.assertNotIn("color", wing)
            self.assertEqual(editor.color_button.text(), DEFAULT_COMPONENT_COLOR)


if __name__ == "__main__":
    unittest.main()
