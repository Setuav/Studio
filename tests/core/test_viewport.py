"""Unit tests for StudioViewport and SceneObject API."""

import unittest

from PySide6.QtCore import QSettings, Signal
from PySide6.QtGui import QImage
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
        self.fit_view_called: bool = False
        self.view_angles: tuple[float, float] | None = None
        self.orthographic: bool = True
        self.show_solid: bool = True
        self.show_wireframe: bool = True
        self.wire_mode: str = "feature"
        self.show_grid: bool = True
        self.transparent: bool = False
        self.face_style: str = "colored"

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

    def fit_view(self) -> None:
        self.fit_view_called = True

    def set_view(self, azimuth: float, elevation: float) -> None:
        self.view_angles = (azimuth, elevation)

    def set_orthographic(self, enabled: bool) -> None:
        self.orthographic = enabled

    def set_show_solid(self, show: bool) -> None:
        self.show_solid = show

    def set_show_wireframe(self, show: bool) -> None:
        self.show_wireframe = show

    def set_wire_mode(self, mode: str) -> None:
        self.wire_mode = mode

    def set_show_grid(self, show: bool) -> None:
        self.show_grid = show

    def set_transparent(self, transparent: bool) -> None:
        self.transparent = transparent

    def set_face_style(self, style: str) -> None:
        self.face_style = style

    def capture_screenshot(
        self,
        width: int,
        height: int,
        transparent_background: bool = False,
    ) -> QImage:
        from PySide6.QtGui import QImage

        return QImage(width, height, QImage.Format.Format_ARGB32)


class TestStudioViewport(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    @staticmethod
    def _clear_viewport_settings() -> None:
        settings = QSettings()
        for key in (
            "studio_viewport_orthographic",
            "studio_viewport_show_solid",
            "studio_viewport_show_wireframe",
            "studio_viewport_wire_mode",
            "studio_viewport_show_grid",
            "studio_viewport_face_style",
        ):
            settings.remove(key)

    def setUp(self) -> None:
        self._clear_viewport_settings()
        self.viewport = StudioViewport()
        self.mock_renderer = MockRenderer()
        self.viewport.attach_renderer(self.mock_renderer)

    def tearDown(self) -> None:
        self._clear_viewport_settings()
        super().tearDown()

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

    def test_camera_controls(self) -> None:
        # fit_view
        self.assertFalse(self.mock_renderer.fit_view_called)
        self.viewport.fit_view()
        self.assertTrue(self.mock_renderer.fit_view_called)

        # set_view and view_angles
        self.viewport.set_view(45.0, 30.0)
        self.assertEqual(self.viewport.view_angles(), (45.0, 30.0))
        self.assertEqual(self.mock_renderer.view_angles, (45.0, 30.0))

        # set_view_preset ("top" clamps to 89.0 to avoid gimbal lock)
        self.viewport.set_view_preset("top")
        self.assertEqual(self.viewport.view_angles(), (0.0, 89.0))
        self.viewport.set_view_preset("iso")
        self.assertEqual(self.viewport.view_angles(), (210.0, 20.0))

        with self.assertRaises(ValueError):
            self.viewport.set_view_preset("invalid_preset")  # type: ignore[arg-type]

        # orthographic projection
        self.assertTrue(self.viewport.is_orthographic())
        self.viewport.set_orthographic(False)
        self.assertFalse(self.viewport.is_orthographic())
        self.assertFalse(self.mock_renderer.orthographic)

    def test_display_controls(self) -> None:
        # Solid surface
        self.assertTrue(self.viewport.is_show_solid())
        self.viewport.set_show_solid(False)
        self.assertFalse(self.viewport.is_show_solid())
        self.assertFalse(self.mock_renderer.show_solid)

        # Wireframe
        self.assertTrue(self.viewport.is_show_wireframe())
        self.viewport.set_show_wireframe(False)
        self.assertFalse(self.viewport.is_show_wireframe())
        self.assertFalse(self.mock_renderer.show_wireframe)

        # Wire mode
        self.assertEqual(self.viewport.wire_mode(), "feature")
        self.viewport.set_wire_mode("full")
        self.assertEqual(self.viewport.wire_mode(), "full")
        self.assertEqual(self.mock_renderer.wire_mode, "full")

        with self.assertRaises(ValueError):
            self.viewport.set_wire_mode("invalid")  # type: ignore[arg-type]

        # Grid
        self.assertTrue(self.viewport.is_show_grid())
        self.viewport.set_show_grid(False)
        self.assertFalse(self.viewport.is_show_grid())
        self.assertFalse(self.mock_renderer.show_grid)

        # Transparent
        self.assertFalse(self.viewport.is_transparent())
        self.viewport.set_transparent(True)
        self.assertTrue(self.viewport.is_transparent())
        self.assertTrue(self.mock_renderer.transparent)

        # Face style
        self.assertEqual(self.viewport.face_style(), "colored")
        self.viewport.set_face_style("monochrome")
        self.assertEqual(self.viewport.face_style(), "monochrome")
        self.assertEqual(self.mock_renderer.face_style, "monochrome")

        with self.assertRaises(ValueError):
            self.viewport.set_face_style("invalid")  # type: ignore[arg-type]

    def test_capture_screenshot(self) -> None:
        image = self.viewport.capture_screenshot(800, 600, transparent_background=True)
        self.assertIsNotNone(image)
        assert image is not None
        self.assertEqual(image.width(), 800)
        self.assertEqual(image.height(), 600)

    def test_key_press_fit_view(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        self.mock_renderer.fit_view_called = False
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_F, Qt.KeyboardModifier.NoModifier)
        self.viewport.keyPressEvent(event)
        self.assertTrue(self.mock_renderer.fit_view_called)

    def test_viewport_hud(self) -> None:
        hud = self.viewport.hud
        self.assertIsNotNone(hud)

        # Test solid button toggles viewport
        hud.solid_button.setChecked(False)
        self.assertFalse(self.viewport.is_show_solid())
        hud.solid_button.setChecked(True)
        self.assertTrue(self.viewport.is_show_solid())

        # Test transparency toggle
        hud.trans_button.setChecked(True)
        self.assertTrue(self.viewport.is_transparent())
        hud.trans_button.setChecked(False)
        self.assertFalse(self.viewport.is_transparent())

        # Test shading style buttons
        hud.mono_button.click()
        self.assertEqual(self.viewport.face_style(), "monochrome")
        hud.colored_button.click()
        self.assertEqual(self.viewport.face_style(), "colored")

        # Test fit button
        self.mock_renderer.fit_view_called = False
        hud.fit_button.click()
        self.assertTrue(self.mock_renderer.fit_view_called)

        # Test theme update
        self.viewport.update_theme_style()

    def test_viewport_hud_layers(self) -> None:
        hud = self.viewport.hud
        self.assertIsNotNone(hud.layers_button)
        self.assertIsNotNone(hud.layers_menu)

        # Initial layers should be 'default' and 'geometry'
        action_map = {action.data(): action for action in hud.layers_menu.actions()}
        self.assertIn("default", action_map)
        self.assertIn("geometry", action_map)
        self.assertTrue(action_map["default"].isCheckable())
        self.assertTrue(action_map["default"].isChecked())
        self.assertTrue(action_map["geometry"].isChecked())

        # Test clicking geometry action toggles layer visibility in viewport
        visibility_events: list[tuple[str, bool]] = []
        self.viewport.layer_visibility_changed.connect(
            lambda lid, vis: visibility_events.append((lid, vis))
        )

        action_map["geometry"].trigger()
        self.assertFalse(self.viewport.is_layer_visible("geometry"))
        self.assertEqual(visibility_events[-1], ("geometry", False))

        # Toggling back from viewport updates action state
        self.viewport.set_layer_visible("geometry", True)
        self.assertTrue(self.viewport.is_layer_visible("geometry"))
        self.assertTrue(action_map["geometry"].isChecked())
        self.assertEqual(visibility_events[-1], ("geometry", True))

        # Adding a layer dynamically updates the layers menu
        layers_changed_events: list[bool] = []
        self.viewport.layers_changed.connect(lambda: layers_changed_events.append(True))

        self.viewport.add_layer("aerodynamics", name="Aerodynamics")
        self.assertTrue(len(layers_changed_events) > 0)
        action_map = {action.data(): action for action in hud.layers_menu.actions()}
        self.assertIn("aerodynamics", action_map)
        self.assertEqual(action_map["aerodynamics"].text(), "Aerodynamics")
        self.assertTrue(action_map["aerodynamics"].isChecked())

        # Removing a layer updates the layers menu
        self.viewport.remove_layer("aerodynamics")
        action_map = {action.data(): action for action in hud.layers_menu.actions()}
        self.assertNotIn("aerodynamics", action_map)

    def test_studio_api_viewport_property(self) -> None:
        api = StudioAPI()
        self.assertIsNone(api.viewport)
        api._viewport = self.viewport
        self.assertIs(api.viewport, self.viewport)

    def test_viewport_settings_persistence(self) -> None:
        from PySide6.QtCore import QSettings

        settings = QSettings()
        self.viewport.set_orthographic(False)
        self.assertFalse(self.viewport.is_orthographic())
        self.assertEqual(settings.value("studio_viewport_orthographic"), False)

        self.viewport.set_show_grid(False)
        self.assertFalse(self.viewport.is_show_grid())
        self.assertEqual(settings.value("studio_viewport_show_grid"), False)

        self.viewport.set_show_solid(False)
        self.assertFalse(self.viewport.is_show_solid())
        self.assertEqual(settings.value("studio_viewport_show_solid"), False)

        self.viewport.set_wire_mode("full")
        self.assertEqual(self.viewport.wire_mode(), "full")
        self.assertEqual(settings.value("studio_viewport_wire_mode"), "full")

        self.viewport.set_face_style("monochrome")
        self.assertEqual(self.viewport.face_style(), "monochrome")
        self.assertEqual(settings.value("studio_viewport_face_style"), "monochrome")

        for key in (
            "studio_viewport_orthographic",
            "studio_viewport_show_grid",
            "studio_viewport_show_solid",
            "studio_viewport_wire_mode",
            "studio_viewport_face_style",
        ):
            settings.remove(key)
