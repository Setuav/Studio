"""Tests for the mass tab of a component with subparts."""

from __future__ import annotations

import unittest

from setuav_studio.api import ComponentTypeContribution, StudioAPI
from setuav_studio.model.expression import get_expression
from setuav_studio.project import open_project
from setuav_studio.ui.editor import MassPropertiesEditor
from setuav_studio.utilities.mass_balance import resolve_aircraft_mass_properties
from tests._common import TEST_PROJECT_PATH, get_qapp, register_fixture_component_types


class MassEditorWithSubpartsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        register_fixture_component_types(self.api)
        self.project = open_project(TEST_PROJECT_PATH)
        self.api._host.set_project(self.project)
        wing = self.project.get_component("main-wing")
        assert wing is not None
        self.wing = wing
        self.editor = MassPropertiesEditor(self.api, wing)
        self.addCleanup(self.editor.deleteLater)

    def _total_mass_text(self) -> str:
        table = self.editor.mass_table
        row = next(
            r
            for r in range(table.rowCount())
            if self.editor._property_key(table, r) == "total_mass"
        )
        item = table.item(row, 1)
        assert item is not None
        return item.text()

    def test_mass_field_shows_the_component_alone(self) -> None:
        self.assertAlmostEqual(self.editor.mass_g.value(), 250.0)
        # Wing 250 g, aileron 25 g and flap 0 g.
        self.assertEqual(self._total_mass_text(), "275.000 g")

    def test_editing_the_cg_does_not_count_subparts_twice(self) -> None:
        aircraft_before = resolve_aircraft_mass_properties(self.project).mass_kg

        self.editor._on_field_changed("cg.x", str(self.editor.cg_spins["x"].value() + 5.0))

        self.assertAlmostEqual(float(self.wing["mass"]), 250.0)
        aircraft_after = resolve_aircraft_mass_properties(self.project).mass_kg
        self.assertAlmostEqual(aircraft_after, aircraft_before, places=9)


class MassFormulaTests(unittest.TestCase):
    """The Mass tab keeps formulas like every other numeric field."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        register_fixture_component_types(self.api)
        self.project = open_project(TEST_PROJECT_PATH)
        self.project.data["parameters"]["k"] = {"value": 7.0, "unit": "1"}
        self.api._host.set_project(self.project)
        point_mass = self.project.get_component("avionics-point-mass")
        assert point_mass is not None
        self.point_mass = point_mass
        self.editor = MassPropertiesEditor(self.api, point_mass)
        self.addCleanup(self.editor.deleteLater)

    def _set_k(self, value: float) -> None:
        self.api.edit_project(
            "Set k", lambda: self.project.data["parameters"]["k"].update(value=value)
        )

    def test_mass_formula_is_kept_and_follows_its_constant(self) -> None:
        self.editor._on_field_changed("mass", "=k*10")
        self.assertEqual(get_expression(self.point_mass, "mass"), "=k*10")
        self.assertAlmostEqual(float(self.point_mass["mass"]), 70.0)

        self._set_k(8.0)
        self.assertAlmostEqual(float(self.point_mass["mass"]), 80.0)

    def test_a_number_replaces_a_mass_formula(self) -> None:
        self.editor._on_field_changed("mass", "=k*10")
        self.editor._on_field_changed("mass", "33")
        self.assertIsNone(get_expression(self.point_mass, "mass"))

        self._set_k(9.0)
        self.assertAlmostEqual(float(self.point_mass["mass"]), 33.0)

    def test_cg_formula_is_kept_and_only_its_axis_is_stored(self) -> None:
        self.editor._on_field_changed("cg.x", "=k*2")
        cg = self.point_mass["local_cg_mm"]
        self.assertEqual(get_expression(cg, "x"), "=k*2")
        self.assertNotIn("y", cg)

        self._set_k(5.0)
        self.assertAlmostEqual(float(cg["x"]), 10.0)

    def test_inertia_formula_is_kept(self) -> None:
        self.editor._on_field_changed("inertia.ixx", "=k/1000")
        self._set_k(2.0)
        self.assertAlmostEqual(float(self.point_mass["inertia_kg_m2"]["ixx"]), 0.002)


class DerivedMassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        register_fixture_component_types(self.api)
        # A plugin that derives the propulsor's mass marks its type so.
        self.api.register_component_type(
            ComponentTypeContribution(
                id="org.setuav.core:propulsor", name="Propulsor", derived_mass=True
            )
        )
        self.project = open_project(TEST_PROJECT_PATH)
        self.api._host.set_project(self.project)

    def _editor(self, component_id: str) -> MassPropertiesEditor:
        component = self.project.get_component(component_id)
        assert component is not None
        editor = MassPropertiesEditor(self.api, component)
        self.addCleanup(editor.deleteLater)
        return editor

    def test_derived_mass_is_read_only(self) -> None:
        self.assertTrue(self._editor("propulsor-cruise").mass_g.isReadOnly())

    def test_entered_mass_stays_editable(self) -> None:
        self.assertFalse(self._editor("main-wing").mass_g.isReadOnly())


if __name__ == "__main__":
    unittest.main()
