"""Unit and integration tests for 3D scene building, meshes, widgets, and palettes."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

from PySide6.QtCore import Qt

from plugins.geometry.engine.data import LoftGeometry
from plugins.geometry.engine.lifting_surface_geometry import (
    build_lifting_surface_geometry,
)
from plugins.geometry.engine.scene import GeometryProvider, build_project_geometry
from setuav_studio.project import open_project
from setuav_studio.ui.viewport import LoftPrimitive
from setuav_studio.ui.viewport.mesh import build_primitive_solid_vertices
from tests._common import TEST_PROJECT_PATH, get_qapp


class GeometrySceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_palettes_are_complete(self) -> None:
        from plugins.geometry.engine.palettes import (
            lifting_surface_color,
            palette_names,
            segment_colors,
        )

        self.assertEqual(len(palette_names()), 3)
        for name in palette_names():
            with self.subTest(palette=name):
                self.assertEqual(len(segment_colors(name)), 5)
                self.assertEqual(len(lifting_surface_color(name)), 3)
                for color in (*segment_colors(name), lifting_surface_color(name)):
                    self.assertTrue(all(0.0 <= channel <= 1.0 for channel in color))

    def test_solid_mesh_contains_triangle_vertices(self) -> None:
        loft = LoftPrimitive(
            sections=(
                ((0, 0, 0), (0, 1, 0), (0, 0, 1)),
                ((1, 0, 0), (1, 1, 0), (1, 0, 1)),
            ),
            station_spacing=0.0,
        )
        vertices = build_primitive_solid_vertices([loft])
        self.assertGreater(len(vertices), 0)
        self.assertEqual(len(vertices) % 9, 0)
        self.assertEqual((len(vertices) // 9) % 3, 0)

    def test_numeric_spinbox_and_table_widget(self) -> None:
        """Verify NumericSpinBox focused-only mouse wheel handling and set_table_spinbox integration."""
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtWidgets import QTableWidget

        from setuav_studio.ui.widget.spinbox import (
            NumericSpinBox,
            set_table_spinbox,
        )

        # 1. Test NumericSpinBox widget
        spinbox = NumericSpinBox(decimals=1, step=1.0, suffix="mm")
        spinbox.setValue(100.0)
        self.assertEqual(spinbox.value(), 100.0)

        # Non-focused wheel event -> ignored so parent scroll area is not interrupted
        wheel_ev = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        spinbox.wheelEvent(wheel_ev)
        self.assertFalse(wheel_ev.isAccepted())
        self.assertEqual(spinbox.value(), 100.0)

        # Focused wheel event -> accepted and adjusts value
        spinbox.show()
        spinbox.setFocus()
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()
        if not spinbox._is_active_focus():
            spinbox.lineEdit().setFocus()
            QApplication.processEvents()
        wheel_ev.setAccepted(False)
        spinbox.wheelEvent(wheel_ev)
        if spinbox._is_active_focus():
            self.assertTrue(wheel_ev.isAccepted())
            self.assertEqual(spinbox.value(), 101.0)

        # 2. Test set_table_spinbox integration
        table = QTableWidget(3, 2)
        changed_vals = []
        sb = set_table_spinbox(
            table,
            0,
            1,
            50.0,
            step=2.0,
            decimals=1,
            suffix="mm",
            on_changed=lambda v: changed_vals.append(v),
            api=None,
        )
        self.assertIsNotNone(sb)
        self.assertEqual(table.cellWidget(0, 1), sb)
        self.assertEqual(sb.value(), 50.0)
        self.assertEqual(sb.suffix(), " mm")

        # Changing value triggers on_changed callback
        sb.setValue(54.0)
        self.assertIn(54.0, changed_vals)

    def test_nowheel_combobox_and_filter(self) -> None:
        """Verify NoWheelComboBox ignores mouse wheel events and ComboBoxWheelFilter intercepts them."""
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtWidgets import QComboBox

        from setuav_studio.ui.style.theme import ComboBoxWheelFilter
        from setuav_studio.ui.widget.spinbox import NoWheelComboBox

        # 1. Test NoWheelComboBox ignores wheelEvent
        combo = NoWheelComboBox()
        combo.addItems(["Option A", "Option B", "Option C"])
        combo.setCurrentIndex(0)

        wheel_ev = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        combo.wheelEvent(wheel_ev)
        self.assertFalse(wheel_ev.isAccepted())
        self.assertEqual(combo.currentIndex(), 0)

        # 2. Test ComboBoxWheelFilter intercepts standard QComboBox wheel events
        filter_obj = ComboBoxWheelFilter()
        std_combo = QComboBox()
        std_combo.addItems(["Option 1", "Option 2"])
        std_combo.setCurrentIndex(0)

        wheel_ev.setAccepted(True)
        res = filter_obj.eventFilter(std_combo, wheel_ev)
        self.assertTrue(res)
        self.assertFalse(wheel_ev.isAccepted())

    # -------------------------------------------------------------------------
    # AirfoilDialog coverage (Faz 3.11)
    # -------------------------------------------------------------------------

    def test_3d_section_selection_highlight(self) -> None:
        """A selected wing section is ringed on the wing's scene object."""
        from plugins.geometry.scene_controller import _collect_primitives
        from setuav_studio.ui.viewport import SceneObject
        from setuav_studio.ui.viewport.mesh import build_section_ring_vertices

        doc = open_project(TEST_PROJECT_PATH)
        providers: dict[str, GeometryProvider] = {
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry
        }
        geom_data = build_project_geometry(doc, providers)
        primitives, owners = _collect_primitives(geom_data.lofts)
        scene_objects = {
            object_id: SceneObject(
                object_id=object_id, component_id=owners[object_id], primitives=prims
            )
            for object_id, prims in primitives.items()
        }

        ring = build_section_ring_vertices(scene_objects, "main-wing", 0, 0)
        self.assertGreater(len(ring), 0)
        self.assertEqual(build_section_ring_vertices(scene_objects, "main-wing", 0, 99), [])


def _build_fuselage_component() -> dict:
    """Build a two-segment fuselage component for editor tests."""
    return {
        "id": "fuselage-1",
        "name": "Main Fuselage",
        "type": "org.setuav.core:fuselage",
        "mass": 500.0,
        "parameters": {
            "geometry": {
                "segments": [
                    {
                        "tag": "nose",
                        "loft": {"method": "smooth"},
                        "sections": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 80.0},
                            },
                            {
                                "position": {"x": 300.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 120.0},
                            },
                            {
                                "position": {"x": 700.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 60.0},
                            },
                        ],
                    },
                    {
                        "tag": "tail",
                        "loft": {"method": "ruled"},
                        "sections": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {
                                    "type": "polygon",
                                    "vertices": [
                                        {"y": -50.0, "z": -50.0, "radius": 0.0},
                                        {"y": 50.0, "z": -50.0, "radius": 0.0},
                                        {"y": 0.0, "z": 50.0, "radius": 0.0},
                                    ],
                                },
                            },
                            {
                                "position": {"x": 100.0, "y": 0.0, "z": 0.0},
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {
                                    "type": "triangle",
                                    "base_width": 60.0,
                                    "height": 40.0,
                                    "orientation": "up",
                                    "corner_radius": 2.0,
                                },
                            },
                        ],
                    },
                ]
            },
        },
    }

    def test_geometry_screenshot_transparent_background(self) -> None:
        """Verify screenshot transparent background action and capture parameter."""
        from setuav_studio.api import StudioAPI
        from setuav_studio.ui.viewport import StudioViewport

        api = StudioAPI()
        viewport = StudioViewport(api=api)
        self.addCleanup(get_qapp().processEvents)
        self.addCleanup(viewport.deleteLater)

        renderer = viewport.viewer
        assert renderer is not None

        with mock.patch.object(renderer, "capture_screenshot") as mock_capture:
            mock_capture.return_value = None

            # 1. Capture with transparent bg False
            viewport.capture_screenshot(1920, 1080, transparent_background=False)
            mock_capture.assert_called_with(1920, 1080, transparent_background=False)

            # 2. Capture with transparent bg True
            viewport.capture_screenshot(1920, 1080, transparent_background=True)
            mock_capture.assert_called_with(1920, 1080, transparent_background=True)

    def test_provider_uniform_signature_and_instance_source_controls(self) -> None:
        from pathlib import Path

        from setuav_studio.project import ProjectDocument

        wing = {
            "kind": "component",
            "id": "wing-src",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "airfoil": "2412",
                        },
                        {
                            "position": {"x": 20.0, "y": 500.0, "z": 0.0},
                            "chord": 150.0,
                            "airfoil": "2412",
                        },
                    ]
                }
            },
        }
        source_aileron = {
            "kind": "component",
            "id": "src-aileron",
            "type": "org.setuav.core:control-surface",
            "attach_to": "wing-src",
            "parameters": {
                "geometry": {
                    "type": "aileron",
                    "sizing_mode": "dimension",
                    "span_start": 200.0,
                    "span_end": 450.0,
                    "chord": 40.0,
                    "deflection": 15.0,
                }
            },
        }
        inst_wing = {
            "kind": "instance",
            "id": "wing-inst",
            "source": "wing-src",
            "derivation": {"type": "mirror", "plane": "XZ"},
        }
        doc = ProjectDocument(
            Path("/tmp/scene-inst.json"),
            "json",
            {"components": [wing, source_aileron, inst_wing]},
        )
        seen_calls: list[tuple[str, list[dict]]] = []

        def tracking_wing_provider(
            component: dict, controls: list[dict]
        ) -> tuple[LoftGeometry, ...]:
            seen_calls.append((str(component.get("id")), controls))
            return build_lifting_surface_geometry(component, controls)

        scene_geom = build_project_geometry(
            doc, {"org.setuav.core:lifting-surface": tracking_wing_provider}
        )
        self.assertEqual(len(seen_calls), 2)
        self.assertTrue(all(len(ctrls) == 1 for _, ctrls in seen_calls))
        inst_aileron_loft = next(
            (loft for loft in scene_geom.lofts if loft.component_id == "wing-inst:src-aileron"),
            None,
        )
        self.assertIsNotNone(inst_aileron_loft)


class _FakeViewport:
    def __init__(self) -> None:
        self.layers: set[str] = set()
        self.objects: dict[str, Any] = {}
        self.cleared: list[str | None] = []

    def has_layer(self, layer: str) -> bool:
        return layer in self.layers

    def add_layer(self, layer: str, name: str = "", visible: bool = True) -> None:
        self.layers.add(layer)

    def clear(self, layer: str | None = None) -> None:
        self.cleared.append(layer)
        self.objects.clear()

    def object_ids(self, layer: str | None = None) -> list[str]:
        return list(self.objects)

    def remove(self, object_id: str) -> None:
        self.objects.pop(object_id, None)

    def add_object(self, obj: Any) -> None:
        self.objects[obj.object_id] = obj


class _FakeApi:
    def __init__(self, project: Any) -> None:
        self.viewport = _FakeViewport()
        self.project = project
        self.statuses: list[tuple[str, str]] = []

    def show_status(self, message: str, level: str = "info", timeout_ms: int = 5000) -> None:
        self.statuses.append((message, level))


def _fuselage_project(profile: dict[str, Any]) -> SimpleNamespace:
    sections = [
        {"position": {"x": x, "y": 0.0, "z": 0.0}, "profile": dict(profile)} for x in (0.0, 300.0)
    ]
    return SimpleNamespace(
        data={
            "components": [
                {
                    "id": "body",
                    "type": "org.setuav.core:fuselage",
                    "parameters": {"geometry": {"segments": [{"sections": sections}]}},
                }
            ]
        }
    )


class AirframeSceneControllerTests(unittest.TestCase):
    def _controller(self, project: Any) -> tuple[Any, _FakeApi]:
        from plugins.geometry.engine.fuselage_geometry import build_fuselage_geometry
        from plugins.geometry.scene_controller import AirframeSceneController

        api = _FakeApi(project)
        controller = AirframeSceneController(
            cast(Any, api), {"org.setuav.core:fuselage": build_fuselage_geometry}
        )
        return controller, api

    def test_valid_geometry_is_drawn(self) -> None:
        controller, api = self._controller(_fuselage_project({"type": "circle", "diameter": 80.0}))
        controller.sync()
        self.assertIn("body", api.viewport.objects)
        self.assertEqual(api.statuses, [])

    def test_invalid_geometry_clears_airframe_and_reports_error(self) -> None:
        controller, api = self._controller(_fuselage_project({"type": "circle", "diameter": 80.0}))
        controller.sync()
        self.assertIn("body", api.viewport.objects)

        api.project = _fuselage_project({"type": "hexagon"})
        controller.sync()

        self.assertEqual(api.viewport.objects, {})
        self.assertEqual(len(api.statuses), 1)
        message, level = api.statuses[0]
        self.assertEqual(level, "error")
        self.assertIn("hexagon", message)


class NumberFieldTests(unittest.TestCase):
    def test_missing_key_uses_caller_default(self) -> None:
        from plugins.geometry.engine.transforms import number_field

        self.assertEqual(number_field({}, "x", 0.0), 0.0)
        self.assertEqual(number_field({"x": 3}, "x", 0.0), 3.0)

    def test_missing_key_without_default_raises(self) -> None:
        from plugins.geometry.engine.transforms import number_field

        with self.assertRaises(ValueError):
            number_field({}, "chord")

    def test_non_numeric_value_raises(self) -> None:
        from plugins.geometry.engine.transforms import number_field, transform_matrix

        for value in ("12", None, True, [1.0]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                number_field({"x": value}, "x", 0.0)
        with self.assertRaises(ValueError):
            transform_matrix({"position": {"x": "left"}})


if __name__ == "__main__":
    unittest.main()
