"""Unit tests for aircraft mass, center of gravity, and inertia tensor resolution."""

from __future__ import annotations

import json
import math
import unittest

from setuav_studio.utilities.mass_balance import (
    _parallel_axis,
    get_component_subparts,
    resolve_aircraft_mass_properties,
    resolve_component_aggregate_mass_properties,
    resolve_component_intrinsic_mass_properties,
    resolve_component_local_cg,
)
from tests._common import TEST_PROJECT_PATH


def test_parallel_axis_theorem() -> None:
    # 2 kg point mass offset by 1 meter along X: (1.0, 0.0, 0.0) m
    # I_xx = m * (dy^2 + dz^2) = 0
    # I_yy = m * (dx^2 + dz^2) = 2.0 * 1.0 = 2.0
    # I_zz = m * (dx^2 + dy^2) = 2.0 * 1.0 = 2.0
    p_mat = _parallel_axis(2.0, (1.0, 0.0, 0.0))
    assert math.isclose(p_mat[0][0], 0.0, abs_tol=1e-6)
    assert math.isclose(p_mat[1][1], 2.0, rel_tol=1e-5)
    assert math.isclose(p_mat[2][2], 2.0, rel_tol=1e-5)


def test_resolve_component_local_cg() -> None:
    # 1. Declared local_cg_mm
    comp1 = {"local_cg_mm": {"x": 12.0, "y": -5.0, "z": 8.0}}
    assert resolve_component_local_cg(comp1) == (12.0, -5.0, 8.0)

    # 2. Fallback to envelope offset
    comp2 = {"envelope": {"offset_mm": {"x": 20.0, "y": 0.0, "z": -10.0}}}
    assert resolve_component_local_cg(comp2) == (20.0, 0.0, -10.0)

    # 3. Default fallback
    comp3 = {}
    assert resolve_component_local_cg(comp3) == (0.0, 0.0, 0.0)


def test_resolve_aircraft_mass_properties_empty() -> None:
    result = resolve_aircraft_mass_properties({"components": []})
    assert result.mass_kg == 0.0
    assert result.cg_body_m == (0.0, 0.0, 0.0)
    assert result.inertia_cg_kg_m2.ixx == 0.0


def test_resolve_aircraft_mass_properties_single_component() -> None:
    comp = {
        "id": "battery-1",
        "name": "LiPo Battery",
        "mass": 1000.0,  # 1000 g = 1.0 kg
        "transform": {
            "position": {"x": 800.0, "y": 0.0, "z": 50.0},  # mm
        },
    }
    result = resolve_aircraft_mass_properties({"components": [comp]})
    assert math.isclose(result.mass_kg, 1.0, rel_tol=1e-5)
    assert math.isclose(result.cg_body_m[0], 0.8, rel_tol=1e-5)
    assert math.isclose(result.cg_body_m[1], 0.0, abs_tol=1e-6)
    assert math.isclose(result.cg_body_m[2], 0.05, rel_tol=1e-5)


def test_resolve_aircraft_mass_properties_two_masses_balance() -> None:
    # Mass 1: 1 kg at x = 0.0 m
    # Mass 2: 3 kg at x = 2000.0 mm (2.0 m)
    # Total mass = 4 kg.
    # CG_x = (1.0 * 0.0 + 3.0 * 2.0) / 4.0 = 6.0 / 4.0 = 1.5 m
    comp1 = {
        "id": "comp-1",
        "mass": 1000.0,
        "transform": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}},
    }
    comp2 = {
        "id": "comp-2",
        "mass": 3000.0,
        "transform": {"position": {"x": 2000.0, "y": 0.0, "z": 0.0}},
    }
    result = resolve_aircraft_mass_properties({"components": [comp1, comp2]})
    assert math.isclose(result.mass_kg, 4.0, rel_tol=1e-5)
    assert math.isclose(result.cg_body_m[0], 1.5, rel_tol=1e-5)
    assert math.isclose(result.cg_body_m[1], 0.0, abs_tol=1e-6)
    assert math.isclose(result.cg_body_m[2], 0.0, abs_tol=1e-6)


def test_resolve_aircraft_mass_properties_follows_attachments() -> None:
    # Motor at x = 500 mm (0.5 m), 1.0 kg
    # Propeller attached to the motor 500 mm further aft (vehicle x = 1.0 m), 1.0 kg
    # Combined CG_x = (1.0 * 0.5 + 1.0 * 1.0) / 2.0 = 0.75 m
    motor = {
        "id": "motor-1",
        "mass": 1000.0,
        "transform": {"position": {"x": 500.0, "y": 0.0, "z": 0.0}},
    }
    prop = {
        "id": "prop-1",
        "attach_to": "motor-1",
        "mass": 1000.0,
        "transform": {"position": {"x": 500.0, "y": 0.0, "z": 0.0}},
    }
    result = resolve_aircraft_mass_properties({"components": [motor, prop]})
    assert math.isclose(result.mass_kg, 2.0, rel_tol=1e-5)
    assert math.isclose(result.cg_body_m[0], 0.75, rel_tol=1e-5)


def test_control_surface_on_mirrored_wing_is_symmetric() -> None:
    def wing(mirror: bool) -> dict[str, object]:
        return {
            "id": "wing",
            "type": "org.setuav.core:lifting-surface",
            "mass": 200.0,
            "transform": {"position": {"x": 100.0, "y": 0.0, "z": 0.0}},
            "parameters": {"geometry": {"mirror": mirror}},
        }

    aileron = {
        "id": "aileron",
        "type": "org.setuav.core:control-surface",
        "attach_to": "wing",
        "mass": 20.0,
        "transform": {"position": {"x": 50.0, "y": 400.0, "z": 0.0}},
    }

    mirrored = resolve_aircraft_mass_properties([wing(True), aileron])
    assert math.isclose(mirrored.cg_body_m[1], 0.0, abs_tol=1e-12)
    assert math.isclose(mirrored.cg_body_m[0], (200.0 * 0.1 + 20.0 * 0.15) / 220.0, abs_tol=1e-6)

    one_sided = resolve_aircraft_mass_properties([wing(False), aileron])
    assert math.isclose(one_sided.cg_body_m[1], 20.0 * 0.4 / 220.0, abs_tol=1e-6)


def test_aggregate_mass_includes_subparts_only() -> None:
    fuselage = {"id": "fuselage", "type": "fuselage", "mass": 300.0}
    wing = {
        "id": "wing",
        "type": "wing",
        "attach_to": "fuselage",
        "mass": 200.0,
        "transform": {"position": {"x": 100.0, "y": 0.0, "z": 0.0}},
    }
    aileron = {
        "id": "aileron",
        "type": "control-surface",
        "attach_to": "wing",
        "mass": 20.0,
        "transform": {"position": {"x": 50.0, "y": 0.0, "z": 0.0}},
    }
    components = [fuselage, wing, aileron]
    subpart_types = {"control-surface"}

    assert get_component_subparts("wing", components, subpart_types) == [aileron]
    assert get_component_subparts("fuselage", components, subpart_types) == []
    wing_total = resolve_component_aggregate_mass_properties("wing", components, subpart_types)
    assert math.isclose(wing_total.mass_kg, 0.22)
    assert math.isclose(wing_total.cg_body_m[0], (0.2 * 0.1 + 0.02 * 0.15) / 0.22, abs_tol=1e-6)
    fuselage_total = resolve_component_aggregate_mass_properties(
        "fuselage", components, subpart_types
    )
    assert math.isclose(fuselage_total.mass_kg, 0.3)


class MirroredMassTests(unittest.TestCase):
    """A mirrored part's CG lies in the plane it is mirrored in."""

    def _components(self) -> list[dict]:
        return json.loads((TEST_PROJECT_PATH / "project.json").read_text(encoding="utf-8"))[
            "components"
        ]

    def test_single_sided_control_surface_keeps_its_own_side(self) -> None:
        components = self._components()
        aileron = next(c for c in components if c["id"] == "aileron")
        mirrored = resolve_component_intrinsic_mass_properties("aileron", components)
        self.assertAlmostEqual(mirrored.cg_body_m[1], 0.0, places=9)

        aileron["parameters"]["geometry"]["symmetry_mode"] = "none"
        single = resolve_component_intrinsic_mass_properties("aileron", components)
        self.assertGreater(single.cg_body_m[1], 0.1)

    def test_mirror_plane_follows_the_attach_frame(self) -> None:
        components = self._components()
        fuselage = next(c for c in components if c["id"] == "fuselage")
        fuselage.setdefault("transform", {}).setdefault("position", {})["y"] = 20.0
        wing = resolve_component_intrinsic_mass_properties("main-wing", components)
        self.assertAlmostEqual(wing.cg_body_m[1], 0.020, places=9)
