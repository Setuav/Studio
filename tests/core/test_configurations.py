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
        self.assertEqual(
            segments, ["wing-1", "parameters", "geometry", "profiles", 0, "chord"]
        )

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
        self.assertEqual(
            get_by_path(data, "wing-1.parameters.geometry.profiles[0].chord"), 250.0
        )

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
                    "parameter_overrides": {
                        "project.parameters.aspect_ratio": 10.0,
                        "wing-1.parameters.geometry.span": 2500.0,
                    },
                    "is_default": True,
                }
            ],
            "components": [
                {
                    "id": "wing-1",
                    "name": "Main Wing",
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

    def test_initial_active_config(self) -> None:
        # Should initialize to default config
        self.assertEqual(self.manager.get_active_id(), "cruise")
        cfg = self.manager.get_active_configuration()
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["tag"], "CRZ")

    def test_create_and_delete_configuration(self) -> None:
        vtol = self.manager.create_configuration(
            name="VTOL Mode",
            tag="VTOL",
            description="Vertical takeoff",
            color="#FF9800",
        )
        self.assertEqual(vtol["id"], "vtol")
        self.assertEqual(len(self.manager.get_configurations()), 2)

        deleted = self.manager.delete_configuration("vtol")
        self.assertTrue(deleted)
        self.assertEqual(len(self.manager.get_configurations()), 1)

    def test_switching_configurations_and_listeners(self) -> None:
        calls = []
        self.manager.add_change_listener(lambda: calls.append(1))

        self.manager.set_active_id(None)  # Switch to base
        self.assertIsNone(self.manager.get_active_id())
        self.assertEqual(len(calls), 1)

        self.manager.set_active_id("cruise")
        self.assertEqual(self.manager.get_active_id(), "cruise")
        self.assertEqual(len(calls), 2)

    def test_effective_project_parameters(self) -> None:
        # In base (no config active)
        self.manager.set_active_id(None)
        base_params = self.manager.get_effective_project_parameters()
        self.assertAlmostEqual(base_params["aspect_ratio"], 8.0)
        self.assertAlmostEqual(base_params["wing_span"], 4.0)

        # In cruise config (AR overridden to 10.0)
        self.manager.set_active_id("cruise")
        crz_params = self.manager.get_effective_project_parameters()
        self.assertAlmostEqual(crz_params["aspect_ratio"], 10.0)
        # wing_span is derived: sqrt(10.0 * 2.0) = sqrt(20) ~ 4.472
        self.assertAlmostEqual(crz_params["wing_span"], (20.0) ** 0.5)

    def test_get_resolved_component(self) -> None:
        component = self.project_data["components"][0]

        # In base mode
        self.manager.set_active_id(None)
        resolved_base = self.manager.get_resolved_component(component)
        self.assertEqual(resolved_base["parameters"]["geometry"]["span"], 2000.0)
        self.assertAlmostEqual(
            resolved_base["parameters"]["geometry"]["chord"], 4.0 * 200
        )

        # In cruise mode
        self.manager.set_active_id("cruise")
        resolved_crz = self.manager.get_resolved_component(component)
        # Span was overridden to 2500.0
        self.assertEqual(resolved_crz["parameters"]["geometry"]["span"], 2500.0)
        # Chord is computed using effective wing_span (sqrt(20) ~ 4.472)
        self.assertAlmostEqual(
            resolved_crz["parameters"]["geometry"]["chord"], ((20.0) ** 0.5) * 200
        )


if __name__ == "__main__":
    unittest.main()
