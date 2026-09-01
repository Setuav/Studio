import unittest

from setuav_studio.project.configurations import (
    ConfigurationManager,
    apply_configuration_delta,
    compute_configuration_delta,
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


class DeltaConfigurationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_components = [
            {
                "id": "fuselage-1",
                "name": "Fuselage",
                "type": "org.setuav.core:fuselage",
                "parameters": {"mass": 500.0},
            },
            {
                "id": "wing-1",
                "name": "Main Wing",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {"geometry": {"span": 2000.0, "chord": 250.0}},
            },
        ]
        self.base_parameters = {"aspect_ratio": 8.0, "cruise_speed": 25.0}

    def test_apply_delta_with_overrides_and_additions(self) -> None:
        cfg = {
            "id": "vtol",
            "name": "VTOL Config",
            "tag": "VTOL",
            "parameter_overrides": {
                "project.parameters.aspect_ratio": 10.0,
                "wing-1.parameters.geometry.span": 2600.0,
            },
            "excluded_components": [],
            "added_components": [
                {"id": "motor-vtol-1", "name": "VTOL Motor", "type": "org.setuav.core:motor"}
            ],
            "component_overrides": {
                "wing-1": {"name": "Long Span Wing"},
            },
        }
        comps, params, _ = apply_configuration_delta(
            self.base_components, self.base_parameters, [], cfg
        )

        self.assertEqual(len(comps), 3)
        self.assertEqual(comps[1]["name"], "Long Span Wing")
        self.assertEqual(comps[1]["parameters"]["geometry"]["span"], 2600.0)
        self.assertEqual(comps[2]["id"], "motor-vtol-1")
        self.assertEqual(params["aspect_ratio"], 10.0)
        self.assertEqual(params["cruise_speed"], 25.0)  # inherited

    def test_compute_delta(self) -> None:
        curr_components = [
            {
                "id": "fuselage-1",
                "name": "Fuselage",
                "type": "org.setuav.core:fuselage",
                "parameters": {"mass": 500.0},
            },
            {
                "id": "wing-1",
                "name": "High Speed Wing",
                "type": "org.setuav.core:lifting-surface",
                "parameters": {"geometry": {"span": 1800.0, "chord": 250.0}},
            },
            {
                "id": "pod-1",
                "name": "Camera Pod",
                "type": "org.setuav.core:point-mass",
            },
        ]
        curr_parameters = {"aspect_ratio": 7.0, "cruise_speed": 35.0}

        delta = compute_configuration_delta(
            self.base_components, self.base_parameters, curr_components, curr_parameters
        )

        self.assertEqual(delta["excluded_components"], [])
        self.assertEqual(len(delta["added_components"]), 1)
        self.assertEqual(delta["added_components"][0]["id"], "pod-1")
        self.assertEqual(delta["component_overrides"]["wing-1"]["name"], "High Speed Wing")
        self.assertEqual(delta["parameter_overrides"]["wing-1.parameters.geometry.span"], 1800.0)
        self.assertEqual(delta["parameter_overrides"]["project.parameters.aspect_ratio"], 7.0)
        self.assertEqual(delta["parameter_overrides"]["project.parameters.cruise_speed"], 35.0)

    def test_configuration_manager_lifecycle(self) -> None:
        project_data = {
            "components": self.base_components,
            "parameters": self.base_parameters,
            "configurations": [
                {
                    "id": "speed",
                    "name": "High Speed",
                    "tag": "SPD",
                    "parameter_overrides": {
                        "project.parameters.cruise_speed": 40.0,
                    },
                    "excluded_components": [],
                    "added_components": [],
                    "component_overrides": {
                        "wing-1": {"name": "Clipped Wing"},
                    },
                }
            ],
        }
        manager = ConfigurationManager(project_data)

        # Initially in base
        self.assertIsNone(manager.get_active_id())
        self.assertEqual(project_data["components"][1]["name"], "Main Wing")

        # Switch to speed config
        manager.set_active_id("speed")
        self.assertEqual(project_data["components"][1]["name"], "Clipped Wing")
        self.assertEqual(project_data["parameters"]["cruise_speed"], 40.0)

        # Switch back to base
        manager.set_active_id(None)
        self.assertEqual(project_data["components"][1]["name"], "Main Wing")
        self.assertEqual(project_data["parameters"]["cruise_speed"], 25.0)


if __name__ == "__main__":
    unittest.main()
