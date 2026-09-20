"""Contract tests for Setuav Studio SDK."""

from __future__ import annotations

import unittest

from PySide6.QtCore import Qt

import setuav_studio_sdk as sdk


class SDKContractTests(unittest.TestCase):
    def test_toolbar_contribution_requires_one_action_form(self) -> None:
        with self.assertRaises(ValueError):
            sdk.ToolbarContribution(id="invalid", title="Invalid")

    def test_panel_uses_left_dock_by_default(self) -> None:
        contribution = sdk.PanelContribution(
            id="com.example.panel",
            title="Panel",
            factory=lambda: None,  # type: ignore[return-value]
        )
        self.assertEqual(contribution.area, Qt.DockWidgetArea.LeftDockWidgetArea)

    def test_domain_models_accessible_via_sdk(self) -> None:
        self.assertIsNotNone(sdk.Component)
        self.assertIsNotNone(sdk.Vehicle)
        self.assertIsNotNone(sdk.Data)
        self.assertIsNotNone(sdk.ProjectDocument)
        self.assertIsNotNone(sdk.BaseComponentEditor)

    def test_parameter_field_descriptor(self) -> None:
        class SampleComponent(sdk.Component):
            span = sdk.ParameterField(default=1200.0, unit="mm")

        comp = SampleComponent(id="s1", name="Sample")
        self.assertEqual(comp.span, 1200.0)
        comp.span = 1500.0
        self.assertEqual(comp.span, 1500.0)
        fields = SampleComponent.get_fields()
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0].key, "span")
        self.assertEqual(fields[0].unit, "mm")


if __name__ == "__main__":
    unittest.main()
