"""Focused tests for the eight-parameter wing planform driver solver."""

from __future__ import annotations

import unittest

from setuav_studio.plugins.geometry.engine.wing_driver_solver import (
    PLANFORM_PARAM_KEYS,
    compute_all_8_parameters,
    solve_8_parameter_driver,
)


class WingDriverSolverTests(unittest.TestCase):
    def assert_planform_matches(
        self,
        result: dict[str, float],
        *,
        span: float,
        root_chord: float,
        tip_chord: float,
        is_symmetric: bool = True,
        y_offset: float = 0.0,
    ) -> None:
        expected = compute_all_8_parameters(
            span,
            root_chord,
            tip_chord,
            is_symmetric=is_symmetric,
            y_offset=y_offset,
        )
        self.assertEqual(set(result), set(PLANFORM_PARAM_KEYS))
        for key in PLANFORM_PARAM_KEYS:
            self.assertAlmostEqual(result[key], expected[key], places=7, msg=key)

    def test_compute_all_parameters_for_symmetric_planform(self) -> None:
        result = compute_all_8_parameters(1000.0, 200.0, 100.0)

        self.assertAlmostEqual(result["area"], 15.0)
        self.assertAlmostEqual(result["aspect_ratio"], 20.0 / 3.0)
        self.assertAlmostEqual(result["taper_ratio"], 0.5)
        self.assertAlmostEqual(result["ave_chord"], 150.0)
        self.assertAlmostEqual(result["mac"], 1400.0 / 9.0)

    def test_compute_all_parameters_respects_offset_and_asymmetry(self) -> None:
        offset = compute_all_8_parameters(
            1000.0,
            200.0,
            100.0,
            y_offset=100.0,
        )
        asymmetric = compute_all_8_parameters(
            500.0,
            200.0,
            100.0,
            is_symmetric=False,
        )

        self.assertAlmostEqual(offset["area"], 16.0)
        self.assertAlmostEqual(offset["aspect_ratio"], 6.25)
        self.assertAlmostEqual(asymmetric["area"], 7.5)
        self.assertAlmostEqual(asymmetric["aspect_ratio"], 10.0 / 3.0)

    def test_compute_all_parameters_clamps_non_positive_geometry(self) -> None:
        result = compute_all_8_parameters(0.0, -2.0, 0.0)

        self.assertGreater(result["span"], 0.0)
        self.assertGreater(result["root_chord"], 0.0)
        self.assertGreater(result["tip_chord"], 0.0)
        self.assertGreater(result["area"], 0.0)
        self.assertTrue(all(value > 0.0 for value in result.values()))

    def test_span_driver_combinations(self) -> None:
        current = {"span": 1000.0, "root_chord": 200.0, "tip_chord": 100.0}
        target = compute_all_8_parameters(1200.0, 240.0, 120.0)
        cases = (
            ("root-tip", {"span", "root_chord", "tip_chord"}, (1200.0, 240.0, 120.0)),
            ("root-taper", {"span", "root_chord", "taper_ratio"}, (1200.0, 240.0, 120.0)),
            ("tip-taper", {"span", "tip_chord", "taper_ratio"}, (1200.0, 240.0, 120.0)),
            ("area-taper", {"span", "area", "taper_ratio"}, (1200.0, 240.0, 120.0)),
            (
                "aspect-taper",
                {"span", "aspect_ratio", "taper_ratio"},
                (1200.0, 240.0, 120.0),
            ),
            ("area-root", {"span", "area", "root_chord"}, (1200.0, 240.0, 120.0)),
            (
                "aspect-root",
                {"span", "aspect_ratio", "root_chord"},
                (1200.0, 240.0, 120.0),
            ),
            ("area-tip", {"span", "area", "tip_chord"}, (1200.0, 240.0, 120.0)),
            ("fallback-taper", {"span", "taper_ratio", "mac"}, (1200.0, 200.0, 100.0)),
            ("fallback-root", {"span", "root_chord", "mac"}, (1200.0, 240.0, 100.0)),
            ("fallback-tip", {"span", "tip_chord", "mac"}, (1200.0, 200.0, 120.0)),
            ("fallback-current", {"span", "ave_chord", "mac"}, (1200.0, 200.0, 100.0)),
        )

        for name, drivers, expected_geometry in cases:
            with self.subTest(name=name):
                inputs = {key: target[key] for key in drivers}
                result = solve_8_parameter_driver(drivers, inputs, current)
                self.assert_planform_matches(
                    result,
                    span=expected_geometry[0],
                    root_chord=expected_geometry[1],
                    tip_chord=expected_geometry[2],
                )

    def test_non_span_driver_combinations(self) -> None:
        current = {"span": 1000.0, "root_chord": 200.0, "tip_chord": 100.0}
        target = compute_all_8_parameters(1200.0, 240.0, 120.0)
        target_geometry = (1200.0, 240.0, 120.0)
        cases = (
            ("area-aspect-taper", {"area", "aspect_ratio", "taper_ratio"}, target_geometry),
            ("area-aspect-root", {"area", "aspect_ratio", "root_chord"}, target_geometry),
            ("area-aspect-tip", {"area", "aspect_ratio", "tip_chord"}, target_geometry),
            ("area-aspect-current", {"area", "aspect_ratio", "mac"}, target_geometry),
            ("area-root-tip", {"area", "root_chord", "tip_chord"}, target_geometry),
            ("area-root-taper", {"area", "root_chord", "taper_ratio"}, target_geometry),
            ("aspect-root-tip", {"aspect_ratio", "root_chord", "tip_chord"}, target_geometry),
            (
                "fallback-root-tip",
                {"root_chord", "tip_chord", "taper_ratio"},
                (1000.0, 240.0, 120.0),
            ),
        )

        for name, drivers, expected_geometry in cases:
            with self.subTest(name=name):
                inputs = {key: target[key] for key in drivers}
                result = solve_8_parameter_driver(drivers, inputs, current)
                self.assert_planform_matches(
                    result,
                    span=expected_geometry[0],
                    root_chord=expected_geometry[1],
                    tip_chord=expected_geometry[2],
                )

    def test_solver_handles_asymmetric_and_offset_planforms(self) -> None:
        asymmetric_target = compute_all_8_parameters(
            600.0,
            200.0,
            100.0,
            is_symmetric=False,
        )
        asymmetric_cases = (
            {"span", "area", "taper_ratio"},
            {"span", "aspect_ratio", "taper_ratio"},
            {"span", "area", "tip_chord"},
            {"area", "aspect_ratio", "taper_ratio"},
            {"area", "aspect_ratio", "tip_chord"},
            {"area", "aspect_ratio", "mac"},
        )
        for drivers in asymmetric_cases:
            with self.subTest(drivers=drivers):
                asymmetric = solve_8_parameter_driver(
                    drivers,
                    {key: asymmetric_target[key] for key in drivers},
                    {},
                    is_symmetric=False,
                )
                self.assert_planform_matches(
                    asymmetric,
                    span=600.0,
                    root_chord=200.0,
                    tip_chord=100.0,
                    is_symmetric=False,
                )

        offset_target = compute_all_8_parameters(
            1200.0,
            240.0,
            120.0,
            y_offset=100.0,
        )
        offset = solve_8_parameter_driver(
            {"area", "root_chord", "tip_chord"},
            offset_target,
            {},
            y_offset=100.0,
        )
        self.assert_planform_matches(
            offset,
            span=1200.0,
            root_chord=240.0,
            tip_chord=120.0,
            y_offset=100.0,
        )

    def test_solver_uses_defaults_and_clamps_driver_inputs(self) -> None:
        defaults = solve_8_parameter_driver(set(), {}, {})
        self.assert_planform_matches(
            defaults,
            span=1000.0,
            root_chord=200.0,
            tip_chord=100.0,
        )

        clamped = solve_8_parameter_driver(
            {"span", "root_chord", "tip_chord"},
            {"span": 0.0, "root_chord": -1.0, "tip_chord": 0.0},
            {},
        )
        self.assertTrue(all(value > 0.0 for value in clamped.values()))


if __name__ == "__main__":
    unittest.main()
