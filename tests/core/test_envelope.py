"""Unit tests for core 3D physical envelopes, mesh volume, centroid, and inertia tensor calculations."""

from __future__ import annotations

import math

import pytest

from setuav_studio.utilities.envelope import (
    compute_box_envelope,
    compute_cylinder_envelope,
    compute_ellipsoid_envelope,
    compute_loft_envelope,
    compute_mesh_mass_properties,
    resolve_component_envelope,
    resolve_envelope_definition,
)


def test_unit_cube_mesh_mass_properties() -> None:
    # 100x100x100 mm cube from (0,0,0) to (100,100,100)
    s = 100.0
    vertices = [
        (0.0, 0.0, 0.0),  # 0
        (s, 0.0, 0.0),  # 1
        (s, s, 0.0),  # 2
        (0.0, s, 0.0),  # 3
        (0.0, 0.0, s),  # 4
        (s, 0.0, s),  # 5
        (s, s, s),  # 6
        (0.0, s, s),  # 7
    ]
    # Outward-facing triangles
    faces = [
        # Bottom (-Z)
        (0, 2, 1),
        (0, 3, 2),
        # Top (+Z)
        (4, 5, 6),
        (4, 6, 7),
        # Front (-Y)
        (0, 1, 5),
        (0, 5, 4),
        # Back (+Y)
        (2, 3, 7),
        (2, 7, 6),
        # Left (-X)
        (0, 4, 7),
        (0, 7, 3),
        # Right (+X)
        (1, 2, 6),
        (1, 6, 5),
    ]
    triangles = [(vertices[f[0]], vertices[f[1]], vertices[f[2]]) for f in faces]

    vol, centroid, bbox, inertia = compute_mesh_mass_properties(triangles)

    # 1. Volume must be 100^3 = 1,000,000 mm^3
    assert math.isclose(vol, 1_000_000.0, rel_tol=1e-5)

    # 2. Centroid must be (50.0, 50.0, 50.0) mm
    assert math.isclose(centroid[0], 50.0, abs_tol=1e-3)
    assert math.isclose(centroid[1], 50.0, abs_tol=1e-3)
    assert math.isclose(centroid[2], 50.0, abs_tol=1e-3)

    # 3. Bounding box size: 100 x 100 x 100 mm
    assert math.isclose(bbox[0], 100.0, abs_tol=1e-3)
    assert math.isclose(bbox[1], 100.0, abs_tol=1e-3)
    assert math.isclose(bbox[2], 100.0, abs_tol=1e-3)

    # 4. Unit inertia: for cube with side s (in meters: s=0.1 m):
    # I_xx / m = (s_y^2 + s_z^2) / 12 = (0.01 + 0.01) / 12 = 0.02 / 12 = 0.00166667 m^2
    Ixx, Iyy, Izz, Ixy, Ixz, Iyz = inertia
    expected_u_inertia = (0.1**2 + 0.1**2) / 12.0
    assert math.isclose(Ixx, expected_u_inertia, rel_tol=1e-3)
    assert math.isclose(Iyy, expected_u_inertia, rel_tol=1e-3)
    assert math.isclose(Izz, expected_u_inertia, rel_tol=1e-3)
    assert math.isclose(Ixy, 0.0, abs_tol=1e-6)
    assert math.isclose(Ixz, 0.0, abs_tol=1e-6)
    assert math.isclose(Iyz, 0.0, abs_tol=1e-6)


def test_compute_box_envelope() -> None:
    env = compute_box_envelope(size_mm=(200.0, 100.0, 50.0), offset_mm=(10.0, 0.0, 0.0))

    assert env.get("shape") == "box"
    assert math.isclose(env.get("volume_mm3", 0.0), 200.0 * 100.0 * 50.0, rel_tol=1e-4)

    size = env.get("size_mm", {})
    assert size.get("x") == 200.0
    assert size.get("y") == 100.0
    assert size.get("z") == 50.0

    offset = env.get("offset_mm", {})
    assert offset.get("x") == 10.0
    assert offset.get("y") == 0.0
    assert offset.get("z") == 0.0

    # Unit inertia for solid box in m^2:
    # u_ixx = ((sy^2 + sz^2) / 12) / 1e6 = ((100^2 + 50^2) / 12) / 1e6 = 12500 / 12e6 = 0.00104167
    u_i = env.get("unit_inertia", {})
    expected_ixx = ((100.0**2 + 50.0**2) / 12.0) / 1.0e6
    assert math.isclose(u_i.get("ixx", 0.0), expected_ixx, rel_tol=1e-4)


def test_compute_cylinder_envelope() -> None:
    radius = 25.0
    length = 100.0
    env = compute_cylinder_envelope(size_mm=(length, 2.0 * radius, 2.0 * radius))

    assert env.get("shape") == "cylinder"
    assert math.isclose(env["volume_mm3"], math.pi * radius**2 * length, rel_tol=1e-4)
    assert env["size_mm"] == {"x": length, "y": 2.0 * radius, "z": 2.0 * radius}

    # Axial unit inertia 0.5 r^2, transverse L^2 / 12 + r^2 / 4 (m^2 = mm^2 / 1e6)
    u_i = env["unit_inertia"]
    assert math.isclose(u_i["ixx"], 0.5 * radius**2 / 1.0e6, rel_tol=1e-4)
    assert math.isclose(u_i["iyy"], (length**2 / 12.0 + radius**2 / 4.0) / 1.0e6, rel_tol=1e-4)


def test_elliptic_cylinder_keeps_its_section() -> None:
    env = compute_cylinder_envelope(size_mm=(100.0, 60.0, 40.0))
    assert env["size_mm"] == {"x": 100.0, "y": 60.0, "z": 40.0}
    assert math.isclose(env["volume_mm3"], math.pi * 30.0 * 20.0 * 100.0, rel_tol=1e-4)


def test_compute_ellipsoid_envelope() -> None:
    env = compute_ellipsoid_envelope(size_mm=(100.0, 60.0, 40.0))
    assert env["shape"] == "sphere"
    assert math.isclose(env["volume_mm3"], 4.0 / 3.0 * math.pi * 50.0 * 30.0 * 20.0, rel_tol=1e-4)
    assert math.isclose(env["unit_inertia"]["ixx"], (30.0**2 + 20.0**2) / 5.0 / 1.0e6, rel_tol=1e-4)


def test_geometry_envelope_is_returned_as_stored() -> None:
    stored = {
        "shape": "trapezoid",
        "size_mm": {"x": 800.0, "y": 120.0, "z": 120.0},
        "offset_mm": {"x": 360.0, "y": 0.0, "z": 0.0},
        "volume_mm3": 5_000_000.0,
        "unit_inertia": {
            "ixx": 0.001,
            "iyy": 0.05,
            "izz": 0.05,
            "ixy": 0.0,
            "ixz": 0.0,
            "iyz": 0.0,
        },
        "sections": [{"station_x_mm": 0.0, "width_mm": 80.0, "height_mm": 90.0}],
    }
    assert resolve_envelope_definition(stored) == stored
    assert resolve_envelope_definition(stored) is not stored

    with pytest.raises(ValueError, match="needs geometry sections"):
        resolve_envelope_definition({**stored, "sections": []})


def test_compute_loft_envelope() -> None:
    # Loft with two square sections along Z
    sec1 = [(-20.0, -20.0, 0.0), (20.0, -20.0, 0.0), (20.0, 20.0, 0.0), (-20.0, 20.0, 0.0)]
    sec2 = [(-20.0, -20.0, 100.0), (20.0, -20.0, 100.0), (20.0, 20.0, 100.0), (-20.0, 20.0, 100.0)]

    env = compute_loft_envelope([sec1, sec2])
    assert env.get("shape") == "box"
    expected_vol = 40.0 * 40.0 * 100.0  # 160,000 mm³
    assert math.isclose(env.get("volume_mm3", 0.0), expected_vol, rel_tol=0.01)

    size = env.get("size_mm", {})
    assert math.isclose(size.get("x", 0.0), 40.0, abs_tol=1.0)
    assert math.isclose(size.get("y", 0.0), 40.0, abs_tol=1.0)
    assert math.isclose(size.get("z", 0.0), 100.0, abs_tol=1.0)


def test_resolve_component_envelope_explicit_box() -> None:
    comp = {
        "id": "battery-1",
        "name": "LiPo 4S",
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 140.0, "y": 45.0, "z": 30.0},
        },
    }
    env = resolve_component_envelope(comp)
    assert env.get("shape") == "box"
    assert math.isclose(env.get("volume_mm3", 0.0), 140.0 * 45.0 * 30.0, rel_tol=1e-4)
