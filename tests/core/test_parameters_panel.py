"""Unit tests for ProjectParametersPanel."""

from __future__ import annotations

import unittest
from pathlib import Path

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.parameters.parameters_panel import ProjectParametersPanel
from tests._common import get_qapp


class TestProjectParametersPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_parameters_panel_loading_and_editing(self) -> None:
        api = StudioAPI()
        doc = ProjectDocument(
            path=Path("/tmp/test.json"),
            kind="json",
            data={
                "parameters": {
                    "aspect_ratio": 8.0,
                    "wing_area": 2.0,
                    "wing_span": "= sqrt(aspect_ratio * wing_area)",
                }
            },
        )
        api._host.set_project(doc)

        panel = ProjectParametersPanel(api)

        # Should load 3 parameters
        self.assertEqual(panel.table.rowCount(), 3)

        # Check values
        names = [panel.table.item(r, 0).text() for r in range(panel.table.rowCount())]
        self.assertIn("aspect_ratio", names)
        self.assertIn("wing_area", names)
        self.assertIn("wing_span", names)

        span_row = names.index("wing_span")
        self.assertEqual(panel.table.item(span_row, 1).text(), "= sqrt(aspect_ratio * wing_area)")
        self.assertEqual(panel.table.item(span_row, 2).text(), "4")


if __name__ == "__main__":
    unittest.main()
