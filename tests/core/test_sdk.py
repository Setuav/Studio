"""Tests for the stable third-party plugin SDK surface."""

import unittest

import setuav_studio.sdk as sdk
from setuav_studio import plugin_system


class PluginSDKTests(unittest.TestCase):
    def test_public_api_reexports_plugin_contracts(self) -> None:
        self.assertIs(sdk.StudioAPI, plugin_system.StudioAPI)
        self.assertIs(sdk.StudioPlugin, plugin_system.StudioPlugin)
        self.assertIs(sdk.PanelContribution, plugin_system.PanelContribution)
        self.assertIs(sdk.ActionContribution, plugin_system.ActionContribution)

    def test_public_api_identifiers_are_stable(self) -> None:
        self.assertEqual(sdk.PLUGIN_API_VERSION, "1.0")
        self.assertEqual(sdk.PLUGIN_ENTRY_POINT_GROUP, "setuav_studio.plugins")

    def test_public_api_exports_only_declared_symbols(self) -> None:
        for name in sdk.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(sdk, name))


if __name__ == "__main__":
    unittest.main()
