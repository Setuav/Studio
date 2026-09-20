"""Tests for the stable plugin API and lifecycle contracts."""

from __future__ import annotations

import unittest

from setuav_studio import api, plugin


class PluginAPIContractTests(unittest.TestCase):
    def test_public_api_exports_essential_contracts(self) -> None:
        self.assertTrue(hasattr(api, "StudioAPI"))
        self.assertTrue(hasattr(api, "StudioPlugin"))
        self.assertTrue(hasattr(api, "PanelContribution"))
        self.assertTrue(hasattr(api, "ActionContribution"))
        self.assertTrue(hasattr(api, "ToolContribution"))
        self.assertTrue(hasattr(api, "ToolbarContribution"))
        self.assertTrue(hasattr(api, "ComponentTreeNodeContribution"))
        self.assertTrue(hasattr(api, "ComponentTreeProvider"))
        self.assertTrue(hasattr(api, "ComponentTypeContribution"))
        self.assertTrue(hasattr(api, "ProjectTreeNodeContribution"))
        self.assertTrue(hasattr(api, "ProjectTreeProvider"))
        self.assertTrue(hasattr(api, "StudioEvents"))
        self.assertTrue(hasattr(api, "ParameterField"))
        self.assertTrue(hasattr(api, "Component"))

    def test_component_type_registration(self) -> None:
        inst = api.StudioAPI()
        contrib = api.ComponentTypeContribution(
            id="org.test:sensor",
            name="Custom Sensor",
            category="Sensors",
        )
        inst.register_component_type(contrib)
        self.assertEqual(inst.get_component_type("org.test:sensor"), contrib)
        self.assertEqual(inst.get_component_type_label("org.test:sensor"), "Custom Sensor")
        # Fallback for unregistered types
        self.assertEqual(inst.get_component_type_label("org.test:camera-mount"), "Camera Mount")

        inst.unregister_component_type("org.test:sensor")
        self.assertIsNone(inst.get_component_type("org.test:sensor"))
        self.assertEqual(inst.get_component_type_label("org.test:sensor"), "Sensor")

    def test_plugin_entry_point_group_is_stable(self) -> None:
        self.assertEqual(plugin.PLUGIN_ENTRY_POINT_GROUP, "setuav_studio.plugins")

    def test_public_api_exports_only_declared_symbols(self) -> None:
        for name in api.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(api, name))

    def test_studio_events_enum_contract(self) -> None:
        events = api.StudioEvents
        self.assertEqual(events.AERODYNAMICS_ANALYSIS_COMPLETED, "aerodynamics.analysis_completed")
        self.assertEqual(
            events.FLIGHT_PERFORMANCE_ANALYSIS_COMPLETED,
            "flight_performance.analysis_completed",
        )
        self.assertEqual(
            events.WEIGHT_BALANCE_ANALYSIS_COMPLETED, "weight_balance.analysis_completed"
        )
        self.assertEqual(events.PROPULSION_RESULTS_UPDATED, "propulsion.results_updated")
        self.assertEqual(
            events.GEOMETRY_VIEWER_SETTINGS_CHANGED, "geometry.viewer.settings.changed"
        )
        self.assertEqual(events.UNITS_CHANGED, "units.changed")
        self.assertEqual(events.TASK_STARTED, "task.started")
        self.assertEqual(events.TASK_PROGRESS, "task.progress")
        self.assertEqual(events.TASK_FINISHED, "task.finished")
        self.assertEqual(events.TASK_CANCELLED, "task.cancelled")
        self.assertEqual(events.TASK_ERROR, "task.error")
        # Subclass of str
        self.assertIsInstance(events.PROJECT_OPENED, str)

    def test_studio_api_exposes_units_service(self) -> None:
        inst = api.StudioAPI()
        self.assertIsNotNone(inst.units)
        self.assertTrue(hasattr(inst.units, "to_display"))
        self.assertTrue(hasattr(inst.units, "to_base"))
        self.assertTrue(hasattr(inst.units, "get_unit_symbol"))

    def test_studio_api_registration_surface(self) -> None:
        inst = api.StudioAPI()
        expected_pairs = [
            ("register_panel", "unregister_panel"),
            ("register_toolbar_item", "unregister_toolbar_item"),
            ("register_action", "unregister_action"),
            ("register_settings_page", "unregister_settings_page"),
            ("register_tool", "unregister_tool"),
            ("register_component_type", "unregister_component_type"),
            ("register_component_editor", "unregister_component_editor"),
            ("register_kind_editor", "unregister_kind_editor"),
            ("register_component_icon", "unregister_component_icon"),
            ("register_kind_icon", "unregister_kind_icon"),
            ("register_component_model", "unregister_component_model"),
            ("register_component_tree_provider", "unregister_component_tree_provider"),
            ("register_project_tree_provider", "unregister_project_tree_provider"),
            ("register_solver", "unregister_solver"),
        ]
        for reg, unreg in expected_pairs:
            with self.subTest(reg=reg, unreg=unreg):
                self.assertTrue(hasattr(inst, reg), f"Missing {reg}")
                self.assertTrue(hasattr(inst, unreg), f"Missing {unreg}")


if __name__ == "__main__":
    unittest.main()
