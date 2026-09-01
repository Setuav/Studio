import unittest

from setuav_studio.project.parameters import (
    CircularDependencyError,
    ParameterResolver,
)


class ParameterResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ParameterResolver()

    def test_resolve_scalars_only(self) -> None:
        params = {"aspect_ratio": 8.5, "wing_area": 0.85, "name": "TestWing"}
        resolved = self.resolver.resolve_all(params)
        self.assertEqual(resolved, params)

    def test_resolve_derived_parameters(self) -> None:
        params = {
            "aspect_ratio": 8.0,
            "wing_area": 2.0,
            "wing_span": "= sqrt(aspect_ratio * wing_area)",
            "mean_chord": "= wing_area / wing_span",
        }
        resolved = self.resolver.resolve_all(params)
        self.assertAlmostEqual(resolved["aspect_ratio"], 8.0)
        self.assertAlmostEqual(resolved["wing_area"], 2.0)
        self.assertAlmostEqual(resolved["wing_span"], 4.0)
        self.assertAlmostEqual(resolved["mean_chord"], 0.5)

    def test_evaluation_order(self) -> None:
        params = {
            "c": "= b * 2",
            "a": 10,
            "b": "= a + 5",
        }
        order = self.resolver.get_evaluation_order(params)
        self.assertEqual(order, ["a", "b", "c"])
        resolved = self.resolver.resolve_all(params)
        self.assertEqual(resolved, {"a": 10, "b": 15, "c": 30})

    def test_detect_circular_dependency(self) -> None:
        params = {
            "a": "= b + 1",
            "b": "= a + 1",
        }
        cycles = self.resolver.detect_cycles(params)
        self.assertTrue(len(cycles) > 0)
        with self.assertRaises(CircularDependencyError):
            self.resolver.resolve_all(params)

    def test_get_dependents(self) -> None:
        params = {
            "a": 10,
            "b": "= a * 2",
            "c": "= b + 5",
            "d": 20,
        }
        deps_of_a = self.resolver.get_dependents(params, "a")
        self.assertEqual(deps_of_a, {"b", "c"})
        self.assertEqual(self.resolver.get_dependents(params, "d"), set())

    def test_evaluate_component_parameters(self) -> None:
        project_params = {
            "aspect_ratio": 8.0,
            "wing_area": 2.0,
            "wing_span": "= sqrt(aspect_ratio * wing_area)",
        }
        resolved_project = self.resolver.resolve_all(project_params)

        component_params = {
            "geometry": {
                "span": "= wing_span * 1000",
                "profiles": [
                    {"chord": "= wing_span / 4 * 1000", "position": 0.0},
                    {"chord": 200.0, "position": 1.0},
                ],
            },
            "name": "Main Wing",
        }

        evaluated = self.resolver.evaluate_component_parameters(component_params, resolved_project)

        self.assertEqual(evaluated["name"], "Main Wing")
        self.assertAlmostEqual(evaluated["geometry"]["span"], 4000.0)
        self.assertAlmostEqual(evaluated["geometry"]["profiles"][0]["chord"], 1000.0)
        self.assertEqual(evaluated["geometry"]["profiles"][1]["chord"], 200.0)


if __name__ == "__main__":
    unittest.main()
