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
        self.assertTrue(hasattr(api, "ProjectTreeNodeContribution"))
        self.assertTrue(hasattr(api, "ProjectTreeProvider"))
        self.assertTrue(hasattr(api, "StudioEvents"))
        self.assertTrue(hasattr(api, "ParameterField"))
        self.assertTrue(hasattr(api, "Component"))

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
        self.assertEqual(events.TASK_STARTED, "task.started")
        self.assertEqual(events.TASK_PROGRESS, "task.progress")
        self.assertEqual(events.TASK_FINISHED, "task.finished")
        self.assertEqual(events.TASK_CANCELLED, "task.cancelled")
        self.assertEqual(events.TASK_ERROR, "task.error")
        # Subclass of str
        self.assertIsInstance(events.PROJECT_OPENED, str)


if __name__ == "__main__":
    unittest.main()
