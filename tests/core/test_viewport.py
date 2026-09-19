"""Unit tests for StudioViewport and SceneObject API."""

import unittest

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget

from setuav_studio.api import StudioAPI
from setuav_studio.ui.viewport import SceneObject, StudioViewport
from setuav_studio_sdk.primitives import (
    BoxPrimitive,
    CylinderPrimitive,
    LineSegmentsPrimitive,
    LoftPrimitive,
    PlanePrimitive,
    RingPrimitive,
    TrianglesPrimitive,
)


class MockRenderer(QWidget):
    """Mock OpenGL renderer to verify overlay synchronization and selection."""

    componentPicked = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.overlays: dict[str, list] = {}
        self.selected_component: str | None = None
        self.selected_section: tuple[str, int, int] | None = None
        self.selected_envelope: str | None = None

    def set_overlays(self, layer_id: str, primitives: list) -> None:
        self.overlays[layer_id] = list(primitives)

    def set_selected_component(self, component_id: str | None) -> None:
        self.selected_component = component_id

    def set_selected_section(
        self,
        component_id: str | None,
        segment_index: int | None = None,
        section_index: int | None = None,
    ) -> None:
        if component_id is not None and segment_index is not None and section_index is not None:
            self.selected_section = (component_id, segment_index, section_index)
        else:
            self.selected_section = None

    def set_selected_envelope(self, component_id: str | None) -> None:
        self.selected_envelope = component_id


class TestStudioViewport(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.viewport = StudioViewport()
        self.mock_renderer = MockRenderer()
        self.viewport.attach_renderer(self.mock_renderer)

    def test_initial_state(self) -> None:
        self.assertEqual(self.viewport.layers(), ["default", "geometry"])
        self.assertEqual(self.viewport.object_ids(), [])
        self.assertIs(self.viewport.renderer, self.mock_renderer)

    def test_add_box(self) -> None:
        obj = self.viewport.add_box(
            object_id="box-1",
            center=(0.0, 0.0, 0.0),
            size=(100.0, 50.0, 20.0),
            name="Test Box",
            layer="geometry",
        )
        self.assertIsInstance(obj, SceneObject)
        self.assertEqual(obj.object_id, "box-1")
        self.assertEqual(obj.layer, "geometry")
        self.assertEqual(obj.name, "Test Box")
        self.assertEqual(len(obj.primitives), 1)
        self.assertIsInstance(obj.primitives[0], BoxPrimitive)
        self.assertIn("geometry", self.viewport.layers())
        self.assertEqual(self.viewport.object_ids(), ["box-1"])
        self.assertIn("_viewport_api", self.mock_renderer.overlays)
        self.assertEqual(len(self.mock_renderer.overlays["_viewport_api"]), 1)

    def test_add_cylinder(self) -> None:
        obj = self.viewport.add_cylinder(
            object_id="cyl-1",
            start=(0.0, 0.0, 0.0),
            end=(0.0, 100.0, 0.0),
            radius=15.0,
            layer="propulsion",
        )
        self.assertEqual(obj.object_id, "cyl-1")
        self.assertIsInstance(obj.primitives[0], CylinderPrimitive)
        self.assertEqual(self.viewport.object_ids(layer="propulsion"), ["cyl-1"])

    def test_add_ring(self) -> None:
        obj = self.viewport.add_ring(
            object_id="ring-1",
            center=(10.0, 20.0, 30.0),
            radius=25.0,
        )
        self.assertEqual(obj.object_id, "ring-1")
        self.assertIsInstance(obj.primitives[0], RingPrimitive)

    def test_add_plane(self) -> None:
        obj = self.viewport.add_plane(
            object_id="plane-1",
            center=(0.0, 0.0, 0.0),
            width=50.0,
            height=50.0,
        )
        self.assertEqual(obj.object_id, "plane-1")
        self.assertIsInstance(obj.primitives[0], PlanePrimitive)

    def test_add_lines(self) -> None:
        obj = self.viewport.add_lines(
            object_id="lines-1",
            lines=[((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))],
        )
        self.assertEqual(obj.object_id, "lines-1")
        self.assertIsInstance(obj.primitives[0], LineSegmentsPrimitive)

    def test_add_triangles(self) -> None:
        obj = self.viewport.add_triangles(
            object_id="tri-1",
            triangles=[((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))],
        )
        self.assertEqual(obj.object_id, "tri-1")
        self.assertIsInstance(obj.primitives[0], TrianglesPrimitive)

    def test_add_points(self) -> None:
        obj = self.viewport.add_points(
            object_id="points-1",
            points=[(10.0, 20.0, 30.0), (40.0, 50.0, 60.0)],
        )
        self.assertEqual(obj.object_id, "points-1")
        prim = obj.primitives[0]
        self.assertIsInstance(prim, LineSegmentsPrimitive)
        assert isinstance(prim, LineSegmentsPrimitive)
        # Each point creates 3 crosshair segments (6 total for 2 points)
        self.assertEqual(len(prim.lines), 6)

    def test_add_arrows(self) -> None:
        obj = self.viewport.add_arrows(
            object_id="arrow-1",
            arrows=[((0.0, 0.0, 0.0), (0.0, 0.0, 50.0))],
        )
        self.assertEqual(obj.object_id, "arrow-1")
        self.assertIsInstance(obj.primitives[0], LineSegmentsPrimitive)

    def test_add_loft(self) -> None:
        section1 = ((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 5.0, 0.0))
        section2 = ((0.0, 50.0, 0.0), (8.0, 50.0, 0.0), (0.0, 54.0, 0.0))
        obj = self.viewport.add_loft(
            object_id="wing-loft",
            sections=[section1, section2],
            name="Main Wing Loft",
            layer="geometry",
        )
        self.assertEqual(obj.object_id, "wing-loft")
        self.assertEqual(obj.name, "Main Wing Loft")
        prim = obj.primitives[0]
        self.assertIsInstance(prim, LoftPrimitive)
        assert isinstance(prim, LoftPrimitive)
        self.assertEqual(len(prim.sections), 2)

    def test_layer_visibility(self) -> None:
        self.viewport.add_box("box-geom", (0, 0, 0), (10, 10, 10), layer="geometry")
        self.viewport.add_box("box-mfg", (10, 0, 0), (10, 10, 10), layer="manufacturing")

        # Both visible by default
        self.assertEqual(len(self.mock_renderer.overlays["_viewport_api"]), 2)
        self.assertTrue(self.viewport.is_layer_visible("manufacturing"))

        # Hide manufacturing layer
        self.viewport.set_layer_visible("manufacturing", False)
        self.assertFalse(self.viewport.is_layer_visible("manufacturing"))
        self.assertEqual(len(self.mock_renderer.overlays["_viewport_api"]), 1)

        # Re-enable
        self.viewport.set_layer_visible("manufacturing", True)
        self.assertEqual(len(self.mock_renderer.overlays["_viewport_api"]), 2)

    def test_remove_and_clear(self) -> None:
        self.viewport.add_box("b1", (0, 0, 0), (5, 5, 5), layer="l1")
        self.viewport.add_box("b2", (10, 0, 0), (5, 5, 5), layer="l1")
        self.viewport.add_box("b3", (20, 0, 0), (5, 5, 5), layer="l2")

        self.assertEqual(len(self.viewport.object_ids()), 3)

        # Remove single
        self.assertTrue(self.viewport.remove("b1"))
        self.assertFalse(self.viewport.remove("b1"))
        self.assertEqual(len(self.viewport.object_ids()), 2)

        # Clear layer
        self.viewport.clear_layer("l1")
        self.assertEqual(self.viewport.object_ids(), ["b3"])

        # Clear all
        self.viewport.clear()
        self.assertEqual(self.viewport.object_ids(), [])
        self.assertEqual(len(self.mock_renderer.overlays["_viewport_api"]), 0)

    def test_add_and_remove_layer(self) -> None:
        # Explicitly add layer
        layer = self.viewport.add_layer("analysis", name="CFD Analysis", visible=True)
        self.assertEqual(layer.layer_id, "analysis")
        self.assertEqual(layer.name, "CFD Analysis")
        self.assertTrue(self.viewport.has_layer("analysis"))
        self.assertIs(self.viewport.get_layer("analysis"), layer)
        self.assertIn("analysis", self.viewport.layers())

        # Add objects into this layer
        self.viewport.add_box("box-a1", (0, 0, 0), (1, 1, 1), layer="analysis")
        self.viewport.add_box("box-a2", (2, 0, 0), (1, 1, 1), layer="analysis")
        self.assertEqual(self.viewport.object_ids(layer="analysis"), ["box-a1", "box-a2"])

        # Remove layer (and all its objects)
        self.assertTrue(self.viewport.remove_layer("analysis"))
        self.assertFalse(self.viewport.has_layer("analysis"))
        self.assertNotIn("analysis", self.viewport.layers())
        self.assertNotIn("box-a1", self.viewport.object_ids())
        self.assertNotIn("box-a2", self.viewport.object_ids())

        # Remove non-existent layer returns False
        self.assertFalse(self.viewport.remove_layer("non_existent"))

    def test_selection_direct_api(self) -> None:
        changed_events: list[object] = []
        self.viewport.selection_changed.connect(changed_events.append)

        self.assertIsNone(self.viewport.selected_object_id())
        self.viewport.set_selected("box-1")
        self.assertEqual(self.viewport.selected_object_id(), "box-1")
        self.assertEqual(self.mock_renderer.selected_component, "box-1")
        self.assertEqual(changed_events, ["box-1"])

        # Deselect
        self.viewport.set_selected(None)
        self.assertIsNone(self.viewport.selected_object_id())
        self.assertIsNone(self.mock_renderer.selected_component)
        self.assertEqual(changed_events, ["box-1", None])

    def test_section_selection_direct_api(self) -> None:
        self.assertIsNone(self.viewport.selected_section())
        self.viewport.set_selected_section("main-wing", 0, 2)
        self.assertEqual(self.viewport.selected_section(), ("main-wing", 0, 2))
        self.assertEqual(self.mock_renderer.selected_section, ("main-wing", 0, 2))

        self.viewport.set_selected_section(None)
        self.assertIsNone(self.viewport.selected_section())
        self.assertIsNone(self.mock_renderer.selected_section)

    def test_renderer_pick_signal_forwards_to_viewport(self) -> None:
        picked_events: list[str] = []
        self.viewport.object_picked.connect(picked_events.append)

        self.mock_renderer.componentPicked.emit("fuselage")
        self.assertEqual(self.viewport.selected_object_id(), "fuselage")
        self.assertEqual(picked_events, ["fuselage"])

        # Emitting non-string or empty deselects
        self.mock_renderer.componentPicked.emit(None)
        self.assertIsNone(self.viewport.selected_object_id())
        self.assertEqual(picked_events, ["fuselage", ""])

    def test_bi_directional_sync_with_studio_api(self) -> None:
        import tempfile
        from pathlib import Path

        from setuav_studio.project import create_project

        api = StudioAPI()
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_path = Path(tmpdir) / "test.suav"
            project = create_project(proj_path)
            project.data["components"] = [
                {"id": "wing_1", "name": "Main Wing"},
                {"id": "fuse_1", "name": "Fuselage"},
            ]
            api.current_project = project

            viewport = StudioViewport(api=api)
            self.assertIs(api.viewport, viewport)

            # 1. API selection (e.g. Tree clicked) -> Viewport selects
            api.set_selection({"id": "wing_1", "name": "Main Wing"})
            self.assertEqual(viewport.selected_object_id(), "wing_1")

            # 2. Viewport pick (e.g. 3D clicked) -> API selection updates
            viewport.object_picked.emit("fuse_1")
            self.assertEqual(api.current_selection, {"id": "fuse_1", "name": "Fuselage"})

            # 3. Sub-part tag match (e.g. "wing_1:control_1") -> selects "wing_1"
            viewport.object_picked.emit("wing_1:control_1")
            self.assertEqual(api.current_selection, {"id": "wing_1", "name": "Main Wing"})

    def test_studio_api_viewport_property(self) -> None:
        api = StudioAPI()
        self.assertIsNone(api.viewport)
        api._viewport = self.viewport
        self.assertIs(api.viewport, self.viewport)
