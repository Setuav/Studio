"""Unit tests for Aerodynamic Engine Base abstractions and expanded data models."""
from __future__ import annotations

import unittest

from setuav_studio.plugins.aerodynamics.engine.base import (
    AeroEngine,
    AeroForcesMoments,
    AeroResult,
    AeroState,
    AnalysisMethod,
    AnalysisType,
    EngineCapabilities,
    FlightCondition,
    MultiDimensionalSweepResult,
    PolarPoint,
    ReferenceValues,
    SweepVariable,
)


class DummyEngine(AeroEngine):
    @property
    def name(self) -> str:
        return "DummyEngine"

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            methods=frozenset({AnalysisMethod.VLM, AnalysisMethod.AERO_BUILDUP}),
            analysis_types=frozenset({AnalysisType.SINGLE_POINT, AnalysisType.ALPHA_SWEEP, AnalysisType.MULTI_SWEEP}),
            supports_fuselage=True,
            supports_control_surfaces=True,
        )

    def analyze(
        self,
        components: list[dict],
        condition: FlightCondition,
        method: AnalysisMethod = AnalysisMethod.AERO_BUILDUP,
        settings: dict | None = None,
        progress_callback=None,
    ) -> AeroResult:
        polar = [
            PolarPoint(
                alpha=-2.0,
                cl=0.1,
                cd=0.015,
                cm=-0.02,
                cl_over_cd=6.67,
                cx=0.01,
                cy=0.001,
                cz=-0.098,
                cl_roll=-0.0005,
                cn=0.0002,
                beta=0.0,
                p=0.0,
                q=0.0,
                r=0.0,
                forces_moments=AeroForcesMoments(
                    fx_b=5.0,
                    fy_b=0.5,
                    fz_b=-49.0,
                    lift=50.0,
                    drag=7.5,
                    sideforce=0.5,
                    mx_b=-0.2,
                    my_b=-1.0,
                    mz_b=0.1,
                ),
                state=AeroState(alpha=-2.0, beta=0.0, velocity=25.0),
                velocity=25.0,
            ),
            PolarPoint(
                alpha=2.0,
                cl=0.5,
                cd=0.025,
                cm=-0.05,
                cl_over_cd=20.0,
                cx=0.02,
                cy=0.0,
                cz=-0.49,
                cl_roll=0.0,
                cn=0.0,
                beta=0.0,
                forces_moments=AeroForcesMoments(
                    fx_b=10.0,
                    fy_b=0.0,
                    fz_b=-245.0,
                    lift=250.0,
                    drag=12.5,
                    sideforce=0.0,
                ),
                state=AeroState(alpha=2.0, beta=0.0, velocity=25.0),
                velocity=25.0,
            ),
            PolarPoint(
                alpha=6.0,
                cl=0.9,
                cd=0.050,
                cm=-0.08,
                cl_over_cd=18.0,
                cx=0.04,
                cy=-0.001,
                cz=-0.89,
                cl_roll=0.0002,
                cn=-0.0001,
                beta=0.0,
                forces_moments=AeroForcesMoments(
                    fx_b=20.0,
                    fy_b=-0.5,
                    fz_b=-445.0,
                    lift=450.0,
                    drag=25.0,
                    sideforce=-0.5,
                ),
                state=AeroState(alpha=6.0, beta=0.0, velocity=25.0),
                velocity=25.0,
            ),
        ]
        sweep_res = MultiDimensionalSweepResult(
            variables=[SweepVariable(name="alpha", values=[-2.0, 2.0, 6.0], unit="deg")],
            points=polar,
            grid_shape=(3,),
        )
        return AeroResult(
            method=method,
            engine_name=self.name,
            polar_points=polar,
            cl_max=0.9,
            cl_max_alpha=6.0,
            cd_min=0.015,
            ld_max=20.0,
            ld_max_alpha=2.0,
            reference=ReferenceValues(s_ref=0.5, b_ref=1.8, c_ref=0.28),
            reynolds=350000.0,
            mach=0.073,
            dynamic_pressure=382.8,
            oswald_efficiency=0.88,
            sweep_result=sweep_res,
            condition=condition,
        )


class AeroEngineBaseTests(unittest.TestCase):
    def test_analysis_method_legacy_alias_migrates_to_aero_buildup(self) -> None:
        self.assertIs(AnalysisMethod.from_value("comprehensive"), AnalysisMethod.AERO_BUILDUP)
        self.assertIs(AnalysisMethod.from_value("aero_buildup"), AnalysisMethod.AERO_BUILDUP)

    def test_flight_condition_defaults_and_serialization(self) -> None:
        fc = FlightCondition()
        self.assertEqual(fc.velocity, 25.0)
        self.assertEqual(fc.alpha, 2.0)
        self.assertEqual(fc.beta, 0.0)
        self.assertEqual(fc.altitude, 0.0)
        self.assertEqual(fc.p, 0.0)
        self.assertEqual(fc.q, 0.0)
        self.assertEqual(fc.r, 0.0)
        self.assertEqual(fc.control_deflections, {})
        self.assertEqual(fc.alpha_min, -10.0)
        self.assertEqual(fc.alpha_max, 18.0)
        self.assertEqual(fc.alpha_steps, 29)

        # Serialization round-trip
        data = fc.to_dict()
        restored = FlightCondition.from_dict(data)
        self.assertEqual(fc, restored)

    def test_reference_values_and_serialization(self) -> None:
        ref = ReferenceValues(s_ref=0.45, b_ref=1.5, c_ref=0.3, x_cg=0.1, y_cg=0.0, z_cg=-0.02)
        self.assertEqual(ref.s_ref, 0.45)
        self.assertEqual(ref.b_ref, 1.5)
        self.assertEqual(ref.c_ref, 0.3)
        self.assertEqual(ref.x_cg, 0.1)

        data = ref.to_dict()
        restored = ReferenceValues.from_dict(data)
        self.assertEqual(ref, restored)

    def test_forces_moments_and_vectors(self) -> None:
        fm = AeroForcesMoments(
            fx_b=12.5,
            fy_b=-1.2,
            fz_b=-350.0,
            fx_w=-15.0,
            fy_w=-1.2,
            fz_w=-350.0,
            lift=350.0,
            drag=15.0,
            sideforce=-1.2,
            mx_b=0.45,
            my_b=-4.2,
            mz_b=0.12,
            mx_w=0.40,
            my_w=-4.2,
            mz_w=0.15,
        )
        self.assertEqual(fm.force_body, (12.5, -1.2, -350.0))
        self.assertEqual(fm.moment_body, (0.45, -4.2, 0.12))
        self.assertEqual(fm.force_wind, (-15.0, -1.2, -350.0))

        data = fm.to_dict()
        restored = AeroForcesMoments.from_dict(data)
        self.assertEqual(fm, restored)

        legacy = AeroForcesMoments.from_dict({"lift": 350.0, "drag": 15.0, "sideforce": -1.2})
        self.assertEqual(legacy.force_wind, (-15.0, -1.2, -350.0))

    def test_aero_state_and_serialization(self) -> None:
        state = AeroState(
            alpha=4.5,
            beta=-2.0,
            p=0.05,
            q=0.01,
            r=-0.02,
            velocity=30.0,
            altitude=1500.0,
            mach=0.09,
            reynolds=600000.0,
            dynamic_pressure=470.0,
            control_deflections={"elevator": -3.5, "aileron": 2.0},
        )
        self.assertEqual(state.alpha, 4.5)
        self.assertEqual(state.control_deflections["elevator"], -3.5)

        data = state.to_dict()
        restored = AeroState.from_dict(data)
        self.assertEqual(state, restored)

    def test_polar_point_6dof_and_shortcuts(self) -> None:
        fm = AeroForcesMoments(
            fx_b=15.0,
            fy_b=2.0,
            fz_b=-200.0,
            lift=200.0,
            drag=18.0,
            sideforce=2.0,
            mx_b=0.3,
            my_b=-2.5,
            mz_b=-0.1,
        )
        pt = PolarPoint(
            alpha=3.0,
            cl=0.65,
            cd=0.032,
            cm=-0.06,
            cd_induced=0.018,
            cd_profile=0.014,
            cl_over_cd=20.31,
            cx=0.025,
            cy=0.003,
            cz=-0.64,
            cl_roll=0.001,
            cn=-0.0005,
            beta=1.5,
            p=0.02,
            q=0.0,
            r=-0.01,
            forces_moments=fm,
            velocity=28.0,
            control_deflections={"rudder": 1.0},
        )
        self.assertEqual(pt.alpha, 3.0)
        self.assertEqual(pt.cl, 0.65)
        self.assertEqual(pt.cx, 0.025)
        self.assertEqual(pt.cz, -0.64)
        self.assertEqual(pt.cl_roll, 0.001)
        self.assertEqual(pt.cn, -0.0005)
        self.assertEqual(pt.lift, 200.0)
        self.assertEqual(pt.drag, 18.0)
        self.assertEqual(pt.force_body, (15.0, 2.0, -200.0))
        self.assertEqual(pt.moment_body, (0.3, -2.5, -0.1))

        # Serialization round-trip
        data = pt.to_dict()
        restored = PolarPoint.from_dict(data)
        self.assertEqual(pt.alpha, restored.alpha)
        self.assertEqual(pt.cx, restored.cx)
        self.assertEqual(pt.cz, restored.cz)
        self.assertEqual(pt.forces_moments.fx_b, restored.forces_moments.fx_b)

    def test_multi_dimensional_sweep_dataset(self) -> None:
        p1 = PolarPoint(alpha=0.0, cl=0.2, cd=0.015, beta=0.0, control_deflections={"elevator": 0.0})
        p2 = PolarPoint(alpha=5.0, cl=0.7, cd=0.035, beta=0.0, control_deflections={"elevator": 0.0})
        p3 = PolarPoint(alpha=0.0, cl=0.35, cd=0.018, beta=0.0, control_deflections={"elevator": -5.0})
        p4 = PolarPoint(alpha=5.0, cl=0.85, cd=0.040, beta=0.0, control_deflections={"elevator": -5.0})

        sweep = MultiDimensionalSweepResult(
            variables=[
                SweepVariable(name="alpha", values=[0.0, 5.0], unit="deg"),
                SweepVariable(name="elevator", values=[0.0, -5.0], unit="deg"),
            ],
            points=[p1, p2, p3, p4],
            grid_shape=(2, 2),
        )

        self.assertEqual(sweep.variable_names, ["alpha", "elevator"])

        # Slice for elevator == -5.0
        elev_slice = sweep.get_slice({"elevator": -5.0})
        self.assertEqual(len(elev_slice), 2)
        self.assertIn(p3, elev_slice)
        self.assertIn(p4, elev_slice)

        # Slice for alpha == 5.0
        alpha_slice = sweep.get_slice({"alpha": 5.0})
        self.assertEqual(len(alpha_slice), 2)
        self.assertIn(p2, alpha_slice)
        self.assertIn(p4, alpha_slice)

        # Find exact point
        found = sweep.find_point(alpha=5.0, elevator=-5.0)
        self.assertIsNotNone(found)
        self.assertEqual(found.cl, 0.85)

        # Serialization round-trip
        data = sweep.to_dict()
        restored = MultiDimensionalSweepResult.from_dict(data)
        self.assertEqual(len(restored.points), 4)
        self.assertEqual(restored.grid_shape, (2, 2))

    def test_dummy_engine_and_aero_result_serialization(self) -> None:
        engine = DummyEngine()
        cond = FlightCondition(velocity=25.0, alpha=2.0)
        result = engine.analyze([], cond)

        self.assertEqual(result.engine_name, "DummyEngine")
        self.assertEqual(result.method, AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(len(result.polar_points), 3)
        self.assertEqual(result.cl_max, 0.9)
        self.assertEqual(result.ld_max, 20.0)
        self.assertIsNotNone(result.sweep_result)
        self.assertEqual(len(result.sweep_result.points), 3)

        # get_point
        pt = result.get_point(alpha=2.0)
        self.assertIsNotNone(pt)
        self.assertEqual(pt.cl, 0.5)

        # Serialization round-trip
        data = result.to_dict()
        restored = AeroResult.from_dict(data)
        self.assertEqual(restored.engine_name, "DummyEngine")
        self.assertEqual(restored.method, AnalysisMethod.AERO_BUILDUP)
        self.assertEqual(len(restored.polar_points), 3)
        self.assertEqual(restored.polar_points[0].cx, 0.01)
        self.assertEqual(restored.polar_points[0].forces_moments.fx_b, 5.0)
        self.assertEqual(restored.sweep_result.grid_shape, (3,))


if __name__ == "__main__":
    unittest.main()
