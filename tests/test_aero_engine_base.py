"""Unit tests for Aerodynamic Engine Base abstractions and data models."""
from __future__ import annotations

from setuav_studio.plugins.aerodynamics.engine.base import (
    AeroEngine,
    AeroResult,
    AnalysisMethod,
    AnalysisType,
    EngineCapabilities,
    FlightCondition,
    PolarPoint,
    ReferenceValues,
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
            analysis_types=frozenset({AnalysisType.SINGLE_POINT, AnalysisType.ALPHA_SWEEP}),
            supports_fuselage=True,
            supports_control_surfaces=False,
        )

    def analyze(
        self,
        components: list[dict],
        condition: FlightCondition,
        method: AnalysisMethod = AnalysisMethod.AERO_BUILDUP,
        settings: dict | None = None,
    ) -> AeroResult:
        polar = [
            PolarPoint(alpha=-2.0, cl=0.1, cd=0.015, cm=-0.02, cl_over_cd=6.67),
            PolarPoint(alpha=2.0, cl=0.5, cd=0.025, cm=-0.05, cl_over_cd=20.0),
            PolarPoint(alpha=6.0, cl=0.9, cd=0.050, cm=-0.08, cl_over_cd=18.0),
        ]
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
            oswald_efficiency=0.88,
        )


def test_flight_condition_defaults() -> None:
    fc = FlightCondition()
    assert fc.velocity == 25.0
    assert fc.alpha == 2.0
    assert fc.altitude == 0.0
    assert fc.alpha_min == -10.0
    assert fc.alpha_max == 18.0
    assert fc.alpha_steps == 29


def test_reference_values() -> None:
    ref = ReferenceValues(s_ref=0.45, b_ref=1.5, c_ref=0.3, x_cg=0.1, y_cg=0.0, z_cg=-0.02)
    assert ref.s_ref == 0.45
    assert ref.b_ref == 1.5
    assert ref.c_ref == 0.3


def test_dummy_engine_execution() -> None:
    engine = DummyEngine()
    assert engine.name == "DummyEngine"
    assert engine.is_available() is True

    caps = engine.capabilities()
    assert AnalysisMethod.VLM in caps.methods
    assert AnalysisMethod.AERO_BUILDUP in caps.methods
    assert caps.supports_fuselage is True

    result = engine.analyze([], FlightCondition())
    assert result.engine_name == "DummyEngine"
    assert result.method == AnalysisMethod.AERO_BUILDUP
    assert len(result.polar_points) == 3
    assert result.cl_max == 0.9
    assert result.ld_max == 20.0
    assert result.reference.s_ref == 0.5
