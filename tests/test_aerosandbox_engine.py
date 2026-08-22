"""Unit tests for AeroSandbox aerodynamic engine implementation."""
from __future__ import annotations

import pytest
from setuav_studio.plugins.aerodynamics.engine.base import (
    AnalysisMethod,
    AnalysisType,
    FlightCondition,
)
from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import (
    HAS_AEROSANDBOX,
    AeroSandboxEngine,
)


def _sample_components() -> list[dict]:
    return [
        {
            "id": "fuselage_1",
            "name": "Main Fuselage",
            "type": "org.setuav.core:fuselage",
            "parameters": {
                "geometry": {
                    "segments": [
                        {
                            "sections": [
                                {
                                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "profile": {"type": "circle", "diameter": 80.0},
                                },
                                {
                                    "position": {"x": 800.0, "y": 0.0, "z": 0.0},
                                    "profile": {"type": "circle", "diameter": 40.0},
                                },
                            ]
                        }
                    ]
                }
            },
        },
        {
            "id": "wing_1",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
            "transform": {
                "position": {"x": 200.0, "y": 0.0, "z": 50.0},
            },
            "parameters": {
                "geometry": {
                    "mirror": True,
                    "profiles": [
                        {
                            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "chord": 200.0,
                            "rotation": {"x": 2.0},
                            "airfoil": "2412",
                        },
                        {
                            "position": {"x": 50.0, "y": 750.0, "z": 20.0},
                            "chord": 120.0,
                            "rotation": {"x": 0.0},
                            "airfoil": "2412",
                        },
                    ],
                }
            },
        },
    ]


def test_engine_metadata() -> None:
    engine = AeroSandboxEngine()
    assert engine.name == "AeroSandbox"
    caps = engine.capabilities()
    assert AnalysisMethod.VLM in caps.methods
    assert AnalysisMethod.AERO_BUILDUP in caps.methods
    assert AnalysisType.SINGLE_POINT in caps.analysis_types
    assert AnalysisType.ALPHA_SWEEP in caps.analysis_types
    assert caps.supports_fuselage is True


@pytest.mark.skipif(not HAS_AEROSANDBOX, reason="AeroSandbox not installed")
def test_geometry_conversion_to_airplane() -> None:
    engine = AeroSandboxEngine()
    components = _sample_components()
    airplane = engine._build_airplane(components)

    assert len(airplane.wings) == 1
    assert len(airplane.fuselages) == 1

    wing = airplane.wings[0]
    assert wing.name == "Main Wing"
    assert wing.symmetric is True
    assert len(wing.xsecs) == 2

    # Check root cross section conversion (mm -> m)
    root = wing.xsecs[0]
    assert pytest.approx(root.xyz_le[0], rel=1e-3) == 0.2  # 200 mm base_x
    assert pytest.approx(root.xyz_le[1], rel=1e-3) == 0.0
    assert pytest.approx(root.xyz_le[2], rel=1e-3) == 0.05 # 50 mm base_z
    assert pytest.approx(root.chord, rel=1e-3) == 0.2      # 200 mm chord
    assert root.twist == 2.0

    tip = wing.xsecs[1]
    assert pytest.approx(tip.xyz_le[0], rel=1e-3) == 0.25 # 200 + 50 mm
    assert pytest.approx(tip.xyz_le[1], rel=1e-3) == 0.75 # 750 mm
    assert pytest.approx(tip.chord, rel=1e-3) == 0.12     # 120 mm chord

    span, area = engine._compute_reference_geometry(airplane)
    assert span > 1.4  # symmetric 750mm half-span -> ~1.5m total
    assert area > 0.2


@pytest.mark.skipif(not HAS_AEROSANDBOX, reason="AeroSandbox not installed")
def test_analyze_aerobuildup_sweep() -> None:
    engine = AeroSandboxEngine()
    components = _sample_components()
    cond = FlightCondition(
        velocity=20.0,
        altitude=500.0,
        alpha_min=-4.0,
        alpha_max=8.0,
        alpha_steps=7,
    )

    result = engine.analyze(components, cond, method=AnalysisMethod.AERO_BUILDUP)
    assert result.method == AnalysisMethod.AERO_BUILDUP
    assert len(result.polar_points) == 7
    assert result.cl_max > 0.0
    assert result.cd_min > 0.0
    assert result.ld_max > 0.0
    assert result.reference.s_ref > 0.0
    assert result.reference.b_ref > 0.0
    assert result.reynolds > 10000.0


@pytest.mark.skipif(not HAS_AEROSANDBOX, reason="AeroSandbox not installed")
def test_analyze_vlm_single_point() -> None:
    engine = AeroSandboxEngine()
    components = _sample_components()
    cond = FlightCondition(
        velocity=25.0,
        altitude=0.0,
        alpha=4.0,
        alpha_steps=1,
    )

    result = engine.analyze(components, cond, method=AnalysisMethod.VLM)
    assert result.method == AnalysisMethod.VLM
    assert len(result.polar_points) == 1
    pt = result.polar_points[0]
    assert pt.alpha == 4.0
    assert pt.cl > 0.0
    assert pt.cd > 0.0


@pytest.mark.skipif(not HAS_AEROSANDBOX, reason="AeroSandbox not installed")
def test_analyze_fixed_wing_fixture() -> None:
    import json
    from pathlib import Path

    fixture_path = Path(__file__).parent / "fixtures" / "fixed-wing" / "project.json"
    with open(fixture_path, encoding="utf-8") as f:
        proj_data = json.load(f)

    components = proj_data.get("components", [])
    engine = AeroSandboxEngine()
    cond = FlightCondition(
        velocity=25.0,
        altitude=1000.0,
        alpha_min=-2.0,
        alpha_max=10.0,
        alpha_steps=5,
    )

    # 1. AeroBuildup with Clark-Y wing
    result_ab = engine.analyze(components, cond, method=AnalysisMethod.AERO_BUILDUP)
    assert result_ab.method == AnalysisMethod.AERO_BUILDUP
    assert len(result_ab.polar_points) == 5
    assert result_ab.cl_max > 0.5
    assert result_ab.ld_max > 5.0

    # 2. VLM with Clark-Y wing
    result_vlm = engine.analyze(components, cond, method=AnalysisMethod.VLM)
    assert result_vlm.method == AnalysisMethod.VLM
    assert len(result_vlm.polar_points) == 5
    assert result_vlm.cl_max > 0.5
