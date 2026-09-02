"""Tests for the stable third-party plugin SDK surface."""

import unittest

import setuav_studio_sdk as sdk
from setuav_studio import api


class PluginSDKTests(unittest.TestCase):
    def test_public_api_owns_plugin_contracts(self) -> None:
        self.assertIsNot(sdk.StudioAPI, api.StudioAPI)
        self.assertIs(sdk.StudioPlugin, api.StudioPlugin)
        self.assertIs(sdk.PanelContribution, api.PanelContribution)
        self.assertIs(sdk.ActionContribution, api.ActionContribution)

        public_methods = {
            name
            for name, value in sdk.StudioAPI.__dict__.items()
            if callable(value) and not name.startswith("_")
        }
        implementation_methods = {
            name for name in dir(api.StudioAPI) if callable(getattr(api.StudioAPI, name))
        }
        self.assertLessEqual(public_methods, implementation_methods)

    def test_public_api_identifiers_are_stable(self) -> None:
        self.assertEqual(sdk.PLUGIN_API_VERSION, "1.0")
        self.assertEqual(sdk.PLUGIN_ENTRY_POINT_GROUP, "setuav_studio.plugins")

    def test_public_api_exports_only_declared_symbols(self) -> None:
        for name in sdk.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(sdk, name))

    def test_studio_events_enum_contract(self) -> None:
        self.assertEqual(
            sdk.StudioEvents.AERODYNAMICS_ANALYSIS_COMPLETED, "aerodynamics.analysis_completed"
        )
        self.assertEqual(
            sdk.StudioEvents.FLIGHT_PERFORMANCE_ANALYSIS_COMPLETED,
            "flight_performance.analysis_completed",
        )
        self.assertEqual(
            sdk.StudioEvents.WEIGHT_BALANCE_ANALYSIS_COMPLETED, "weight_balance.analysis_completed"
        )
        self.assertEqual(sdk.StudioEvents.PROPULSION_RESULTS_UPDATED, "propulsion.results_updated")
        self.assertEqual(
            sdk.StudioEvents.GEOMETRY_VIEWER_SETTINGS_CHANGED, "geometry.viewer.settings.changed"
        )
        self.assertEqual(sdk.StudioEvents.TASK_STARTED, "task.started")
        self.assertEqual(sdk.StudioEvents.TASK_PROGRESS, "task.progress")
        self.assertEqual(sdk.StudioEvents.TASK_FINISHED, "task.finished")
        self.assertEqual(sdk.StudioEvents.TASK_CANCELLED, "task.cancelled")
        self.assertEqual(sdk.StudioEvents.TASK_ERROR, "task.error")
        # Subclass of str
        self.assertIsInstance(sdk.StudioEvents.PROJECT_OPENED, str)


if __name__ == "__main__":
    unittest.main()
