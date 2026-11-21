"""Tests for the mass tab of a component with subparts."""

from __future__ import annotations

import unittest

from setuav_studio.api import ComponentTypeContribution, StudioAPI
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

        self.editor.cg_spins["x"].setValue(self.editor.cg_spins["x"].value() + 5.0)
        self.editor._commit_pending()

        self.assertAlmostEqual(float(self.wing["mass"]), 250.0)
        aircraft_after = resolve_aircraft_mass_properties(self.project).mass_kg
        self.assertAlmostEqual(aircraft_after, aircraft_before, places=9)


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
