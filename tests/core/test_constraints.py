"""Unit tests for design constraints evaluation engine and UI."""

from __future__ import annotations

import unittest
from pathlib import Path

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.plugins.core.constraints import ConstraintChecker
from setuav_studio.plugins.core.ui.constraint_status import ConstraintStatusWidget
from setuav_studio.plugins.core.ui.constraints_dialog import ConstraintEditDialog
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class ConstraintEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = ConstraintChecker()
        self.project_data = {
            "parameters": {
                "aspect_ratio": 8.0,
                "wing_area": 2.0,
                "mtow": 50.0,
            },
            "components": [
                {
                    "id": "main-wing",
                    "name": "Main Wing",
                    "mass": 12.0,
                    "parameters": {
                        "geometry": {
                            "span": 2000.0,
                        }
                    },
                }
            ],
            "constraints": [
                {
                    "id": "c1",
                    "name": "Wing Loading Limit",
                    "expression": "mtow / wing_area <= 30",
                    "severity": "warning",
                    "enabled": True,
                },
                {
                    "id": "c2",
                    "name": "Aspect Ratio Minimum",
                    "expression": "aspect_ratio >= 6.0",
                    "severity": "error",
                    "enabled": True,
                },
                {
                    "id": "c3",
                    "name": "Disabled Rule",
                    "expression": "mtow < 10",
                    "enabled": False,
                },
            ],
        }

    def test_evaluate_constraints(self) -> None:
        results = self.checker.check_all(self.project_data)
        self.assertEqual(len(results), 3)

        # c1: 50 / 2 = 25 <= 30 -> True
        self.assertTrue(results[0].passed)
        self.assertEqual(results[0].id, "c1")
        self.assertAlmostEqual(results[0].resolved_values.get("mtow"), 50.0)

        # c2: 8.0 >= 6.0 -> True
        self.assertTrue(results[1].passed)

        # c3: disabled -> passed=True, enabled=False
        self.assertTrue(results[2].passed)
        self.assertFalse(results[2].enabled)

    def test_violated_constraint(self) -> None:
        self.project_data["parameters"]["mtow"] = 80.0
        # 80 / 2 = 40 <= 30 -> False
        results = self.checker.check_all(self.project_data)
        self.assertFalse(results[0].passed)
        self.assertIn("Wing Loading Limit", results[0].name)

    def test_syntax_or_unknown_variable_error(self) -> None:
        bad_constraint = {
            "id": "bad",
            "name": "Bad Expression",
            "expression": "unknown_var > 10",
            "enabled": True,
        }
        res = self.checker.check_constraint(bad_constraint, self.project_data)
        self.assertFalse(res.passed)
        self.assertIsNotNone(res.error)


class ConstraintUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_status_widget_reflects_project_state(self) -> None:
        api = StudioAPI()
        doc = ProjectDocument(
            path=Path("/tmp/test.json"),
            kind="json",
            data={
                "parameters": {"mtow": 20.0, "wing_area": 1.0},
                "constraints": [
                    {
                        "id": "c1",
                        "name": "Wing Loading",
                        "expression": "mtow / wing_area <= 25",
                        "enabled": True,
                    }
                ],
            },
        )
        api._host.set_project(doc)

        widget = ConstraintStatusWidget(api)
        self.assertIn("Constraints OK", widget.btn.text())

        # Cause violation
        doc.data["parameters"]["mtow"] = 50.0
        widget.refresh()
        self.assertIn("1 Violation", widget.btn.text())

    def test_edit_dialog_validation(self) -> None:
        dlg = ConstraintEditDialog(None, {"name": "Span Check", "expression": "span > 1000"})
        data = dlg.get_data()
        self.assertEqual(data["name"], "Span Check")
        self.assertEqual(data["expression"], "span > 1000")


if __name__ == "__main__":
    unittest.main()
