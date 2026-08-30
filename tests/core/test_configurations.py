import unittest

from setuav_studio.plugins.core.configurations import (
    ConfigurationManager,
    get_by_path,
    parse_path_segments,
    set_by_path,
)


class PathUtilsTests(unittest.TestCase):
    def test_parse_path_segments(self) -> None:
        path = "wing-1.parameters.geometry.profiles[0].chord"
        segments = parse_path_segments(path)
        self.assertEqual(segments, ["wing-1", "parameters", "geometry", "profiles", 0, "chord"])

    def test_get_and_set_by_path(self) -> None:
        data = {
            "wing-1": {
                "parameters": {
                    "geometry": {
                        "profiles": [{"chord": 200.0}],
                        "span": 1500.0,
                    }
                }
            }
        }
        val = get_by_path(data, "wing-1.parameters.geometry.profiles[0].chord")
        self.assertEqual(val, 200.0)

        set_by_path(data, "wing-1.parameters.geometry.profiles[0].chord", 250.0)
        self.assertEqual(get_by_path(data, "wing-1.parameters.geometry.profiles[0].chord"), 250.0)

        set_by_path(data, "wing-1.parameters.geometry.sweep", 15.0)
        self.assertEqual(data["wing-1"]["parameters"]["geometry"]["sweep"], 15.0)


class ConfigurationManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_data = {
            "parameters": {
                "aspect_ratio": 8.0,
                "wing_area": 2.0,
                "wing_span": "= sqrt(aspect_ratio * wing_area)",
            },
            "configurations": [
                {
                    "id": "cruise",
                    "name": "Cruise Mode",
                    "tag": "CRZ",
                    "description": "Standard cruise",
                    "color": "#2196F3",
                    "parameters": {
                        "aspect_ratio": 10.0,
                        "wing_area": 2.0,
                        "wing_span": "= sqrt(aspect_ratio * wing_area)",
                    },
                    "components": [
                        {
                            "id": "wing-1",
                            "name": "Cruise Wing",
                            "type": "org.setuav.core:lifting-surface",
                            "parameters": {
                                "geometry": {
                                    "span": 2500.0,
                                    "chord": "= wing_span * 200",
                                }
                            },
                        }
                    ],
                }
            ],
            "components": [
                {
                    "id": "wing-1",
                    "name": "Base Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "parameters": {
                        "geometry": {
                            "span": 2000.0,
                            "chord": "= wing_span * 200",
                        }
                    },
                }
            ],
        }
        self.manager = ConfigurationManager(self.project_data)

    def test_initial_active_is_base(self) -> None:
        # Base is default active initially unless explicitly switched
        self.assertIsNone(self.manager.get_active_id())
        self.assertEqual(self.project_data["components"][0]["name"], "Base Wing")

    def test_switching_to_configuration_loads_variant_components(self) -> None:
        self.manager.set_active_id("cruise")
        self.assertEqual(self.manager.get_active_id(), "cruise")
        # In cruise configuration, component name is "Cruise Wing" and span is 2500
        self.assertEqual(self.project_data["components"][0]["name"], "Cruise Wing")
        self.assertEqual(
            self.project_data["components"][0]["parameters"]["geometry"]["span"], 2500.0
        )

        # Switch back to base
        self.manager.set_active_id(None)
        self.assertIsNone(self.manager.get_active_id())
        self.assertEqual(self.project_data["components"][0]["name"], "Base Wing")
        self.assertEqual(
            self.project_data["components"][0]["parameters"]["geometry"]["span"], 2000.0
        )

    def test_adding_component_in_configuration_does_not_affect_base(self) -> None:
        # Switch to cruise
        self.manager.set_active_id("cruise")
        # Add a new motor in cruise
        new_motor = {"id": "motor-1", "name": "Cruise Motor", "type": "org.setuav.core:motor"}
        self.project_data["components"].append(new_motor)
        self.assertEqual(len(self.project_data["components"]), 2)

        # Switch back to base
        self.manager.set_active_id(None)
        # Base still has only 1 component!
        self.assertEqual(len(self.project_data["components"]), 1)
        self.assertEqual(self.project_data["components"][0]["id"], "wing-1")

        # Switch to cruise again
        self.manager.set_active_id("cruise")
        # Cruise has 2 components!
        self.assertEqual(len(self.project_data["components"]), 2)
        self.assertEqual(self.project_data["components"][1]["id"], "motor-1")

    def test_modifying_component_name_in_configuration(self) -> None:
        # Switch to cruise
        self.manager.set_active_id("cruise")
        self.project_data["components"][0]["name"] = "Modified Cruise Wing"

        # Switch to base
        self.manager.set_active_id(None)
        self.assertEqual(self.project_data["components"][0]["name"], "Base Wing")

        # Switch to cruise
        self.manager.set_active_id("cruise")
        self.assertEqual(self.project_data["components"][0]["name"], "Modified Cruise Wing")

    def test_deleting_component_in_configuration(self) -> None:
        # Create VTOL configuration
        self.manager.create_configuration(name="VTOL", tag="VTOL")
        self.manager.set_active_id("vtol")
        self.assertEqual(len(self.project_data["components"]), 1)

        # Delete the component in VTOL
        self.project_data["components"].clear()
        self.assertEqual(len(self.project_data["components"]), 0)

        # Switch to base - Base still has the wing!
        self.manager.set_active_id(None)
        self.assertEqual(len(self.project_data["components"]), 1)

        # Switch to VTOL - VTOL has 0 components!
        self.manager.set_active_id("vtol")
        self.assertEqual(len(self.project_data["components"]), 0)


if __name__ == "__main__":
    unittest.main()
