"""The values formulas read from airframe components match what the editors show."""

from __future__ import annotations

import unittest
from typing import ClassVar

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

    def test_control_surface_area_ratio_is_its_share_of_one_side(self) -> None:
        from plugins.geometry.engine.control_surface_geometry import (
            compute_control_surface_metrics,
        )

        wing = self.project.get_component("main-wing")
        aileron = self.project.get_component("aileron")
        assert wing is not None and aileron is not None
        metrics = compute_control_surface_metrics(
            dict(aileron["parameters"]["geometry"]), wing["parameters"]["geometry"]["profiles"]
        )
        model = self.scope["aileron"]
        self.assertGreater(model.area_ratio, 0.0)
        self.assertAlmostEqual(model.area_ratio, metrics["area_ratio"])
        self.assertAlmostEqual(model.area, metrics["area_dm2"])

    def test_constraint_status_reads_measured_geometry(self) -> None:
        from setuav_studio.ui.editor.constraint import ConstraintPropertyEditor

        constraint = {
            "id": "c_span",
            "name": "Span",
            "expression": "main_wing.span > 0",
            "severity": "warning",
            "enabled": True,
        }
        self.project.data["constraints"] = [constraint]
        editor = ConstraintPropertyEditor(self.api, constraint)
        self.addCleanup(editor.deleteLater)
        self.assertEqual(editor._property_value(editor.general_table, "status"), "✔ Passed")

    def test_formulas_on_measured_geometry_evaluate_when_the_project_opens(self) -> None:
        from setuav_studio.project.evaluator import recompute_project_expressions

        point_mass = self.project.get_component("avionics-point-mass")
        assert point_mass is not None
        position = point_mass.setdefault("transform", {}).setdefault("position", {})
        position.setdefault("_expressions", {})["x"] = "=main_wing.span / 10"
        # Opening a project evaluates its formulas before any plugin model exists.
        recompute_project_expressions(self.project)
        self.assertNotEqual(self.project.expression_diagnostics, [])

        self.api._host.set_project(self.project)
        self.assertEqual(self.api.expression_diagnostics, [])
        self.assertAlmostEqual(position["x"], self.scope["main_wing"].span / 10, places=6)


class EditorFormulaTests(unittest.TestCase):
    """Numeric cells that accept a formula store it, and the recompute follows it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        plugin = AirframeDesignPlugin()
        plugin.activate(self.api)
        self.addCleanup(plugin.deactivate, self.api)
        self.project = open_project(TEST_PROJECT_PATH)
        self.project.data["parameters"]["k"] = {"value": 2.0, "unit": "1"}
        self.api._host.set_project(self.project)

    def _component(self, component_id: str) -> dict:
        component = self.project.get_component(component_id)
        assert component is not None
        return component

    def _set_k(self, value: float) -> None:
        parameters = self.project.data["parameters"]
        self.api.edit_project("Set k", lambda: parameters["k"].update(value=value))

    def test_airfoil_shaping_keeps_its_formula(self) -> None:
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor

        wing = self._component("main-wing")
        editor = LiftingSurfaceEditor(self.api, wing)
        self.addCleanup(editor.deleteLater)
        editor._on_airfoil_shaping_spinbox_changed("thickness_scale", "=k/2")
        self._set_k(3.0)
        self.assertAlmostEqual(
            wing["parameters"]["geometry"]["airfoil_shaping"]["thickness_scale"], 1.5
        )

    def test_polygon_vertex_keeps_its_formula(self) -> None:
        from plugins.geometry.editors.fuselage.editor import FuselageEditor

        fuselage = self._component("fuselage")
        section = fuselage["parameters"]["geometry"]["segments"][0]["sections"][0]
        section["profile"] = {
            "type": "polygon",
            "vertices": [
                {"y": 10.0, "z": 0.0, "radius": 0.0},
                {"y": 0.0, "z": 10.0, "radius": 0.0},
                {"y": -10.0, "z": 0.0, "radius": 0.0},
            ],
        }
        editor = FuselageEditor(self.api, fuselage)
        self.addCleanup(editor.deleteLater)
        editor._load_section(0)
        editor._on_vertex_spin_changed(0, 0, "=k*10")
        self._set_k(4.0)
        self.assertAlmostEqual(section["profile"]["vertices"][0]["y"], 40.0)

    def test_inline_completion_offers_measured_values(self) -> None:
        from setuav_studio.ui.widget.table import ExpressionPropertyCell

        cell = ExpressionPropertyCell(api=self.api)
        self.addCleanup(cell.deleteLater)
        names = {insert for insert, _label in cell.line_edit._build_completion_items()}
        self.assertIn("main_wing.span", names)
        self.assertIn("main_wing.planform_area", names)
        self.assertIn("k", names)

    def test_envelope_rejects_a_formula(self) -> None:
        from setuav_studio.ui.editor.envelope import EnvelopeEditor

        point_mass = self._component("avionics-point-mass")
        editor = EnvelopeEditor(self.api, point_mass)
        self.addCleanup(editor.deleteLater)
        before = dict(point_mass.get("envelope") or {})
        cell = editor.dimension_spins["x"]
        editor._on_vector_changed(cell, "=k*10")
        self.assertEqual(dict(point_mass.get("envelope") or {}), before)


class ControlSurfaceSizingTests(unittest.TestCase):
    """Control surface area follows the hinge line the 3D model cuts."""

    PROFILES: ClassVar[list[dict]] = [
        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 300.0},
        {"position": {"x": 0.0, "y": 1000.0, "z": 0.0}, "chord": 100.0},
    ]

    def test_full_span_quarter_chord_flap_is_a_quarter_of_the_panel(self) -> None:
        from plugins.geometry.engine.control_surface_geometry import (
            compute_control_surface_metrics,
        )

        rectangle = [
            {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "chord": 200.0},
            {"position": {"x": 0.0, "y": 1000.0, "z": 0.0}, "chord": 200.0},
        ]
        geometry = {
            "sizing_mode": "ratio",
            "eta_start": 0.0,
            "eta_end": 1.0,
            "chord_fraction": 0.25,
        }
        self.assertAlmostEqual(
            compute_control_surface_metrics(geometry, rectangle)["area_ratio"], 25.0
        )

    def test_unswept_hinge_keeps_the_control_chord_at_span_start(self) -> None:
        from plugins.geometry.engine.control_surface_geometry import control_area_mm2

        # Hinge 60 mm ahead of the trailing edge at span start, parallel to the span axis:
        # the control chord falls from 60 mm to 20 mm over 200 mm of taper.
        geometry = {
            "sizing_mode": "dimension",
            "span_start": 0.0,
            "span_end": 200.0,
            "chord": 60.0,
            "hinge_sweep": 0.0,
        }
        self.assertAlmostEqual(control_area_mm2(geometry, self.PROFILES), 8000.0, places=3)


if __name__ == "__main__":
    unittest.main()
