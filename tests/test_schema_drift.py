"""Schema drift gate: project data must validate against the packaged spec schemas.

The schemas under ``setuav_studio/schemas/`` are the source of truth for the
project data model. The fixture project must always validate clean — any new
key written by editors that is not declared in the schema fails this gate.
"""

from __future__ import annotations

import json
import unittest
from copy import deepcopy

from setuav_studio.schema_validation import get_catalog, validate_project
from tests._common import TEST_PROJECT_PATH


def _load_fixture() -> dict:
    with open(TEST_PROJECT_PATH / "project.json", encoding="utf-8") as f:
        return json.load(f)


class SchemaDriftTests(unittest.TestCase):
    def test_fixture_project_validates_clean(self) -> None:
        """The fixture project must have zero schema issues (drift gate)."""
        project = _load_fixture()
        issues = validate_project(project)
        self.assertEqual(
            issues,
            [],
            msg="Schema drift detected:\n" + "\n".join(str(i) for i in issues),
        )

    def test_fixture_component_types_are_registered(self) -> None:
        """Every component type used by the fixture must be registered.

        The fixture represents one concrete aircraft, so it does not need an
        instance of every catalog type (for example, a rotor is optional).
        """
        catalog = get_catalog()
        plugin = catalog.plugins["org.setuav.core"]
        fixture_types = {c.get("type") for c in _load_fixture()["components"]}
        unknown = fixture_types - set(plugin.component_types)
        self.assertEqual(
            unknown,
            set(),
            msg=f"Fixture uses unregistered component types: {sorted(unknown)}",
        )

    def test_editor_written_lifting_surface_keys_validate(self) -> None:
        """Geometry keys written by LiftingSurfaceEditor must be schema-legal."""
        project = _load_fixture()
        wing = next(c for c in project["components"] if c["id"] == "main-wing")
        geometry = wing["parameters"]["geometry"]
        geometry["tip_treatment"] = {
            "type": "winglet",
            "length": 30.0,
            "offset_x": 5.0,
            "winglet_height": 120.0,
            "cant_angle": 80.0,
            "winglet_sweep": 35.0,
            "toe_angle": 2.0,
            "root_chord_scale": 1.0,
            "tip_chord_scale": 0.6,
        }
        geometry["airfoil_shaping"] = {
            "te_thickness": 0.004,
            "thickness_scale": 1.2,
            "camber_scale": 0.8,
        }
        geometry["section_align"] = "normal"
        geometry["twist_location"] = 0.3
        self.assertEqual(validate_project(project), [])

    def test_unknown_key_is_rejected(self) -> None:
        """A key not declared in the schema must fail validation."""
        project = _load_fixture()
        project["components"][1]["parameters"]["geometry"]["bogus_key"] = 1
        issues = validate_project(project)
        self.assertTrue(
            any("bogus_key" in issue.message for issue in issues),
            msg=f"Expected 'bogus_key' rejection, got: {issues}",
        )

    def test_invalid_enum_value_is_rejected(self) -> None:
        project = _load_fixture()
        wing = next(c for c in project["components"] if c["id"] == "main-wing")
        wing["parameters"]["geometry"]["tip_treatment"]["type"] = "not_a_tip_type"
        issues = validate_project(project)
        self.assertTrue(any("tip_treatment" in issue.path for issue in issues))

    def test_unknown_component_type_does_not_crash(self) -> None:
        """Components from unknown plugins are skipped, not an error."""
        project = deepcopy(_load_fixture())
        project["components"][0]["type"] = "org.other.plugin:widget"
        issues = validate_project(project)
        self.assertFalse(
            any("widget" in issue.message for issue in issues),
            msg=f"Unknown plugin type should not fail: {issues}",
        )


if __name__ == "__main__":
    unittest.main()
