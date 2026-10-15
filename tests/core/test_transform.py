"""Unit tests for core spatial transform and reparenting utilities."""

from __future__ import annotations

import math
from pathlib import Path

from setuav_studio.api.api import StudioAPI
from setuav_studio.project.document import ProjectDocument
from setuav_studio.utilities.transform import (
    euler_to_matrix,
    inverse_rotate_vector,
    matrix_to_euler,
    reparent_component,
    resolve_world_transform,
    rotate_vector,
)


def test_euler_matrix_roundtrip() -> None:
    test_cases = [
        (0.0, 0.0, 0.0),
        (10.0, 20.0, 30.0),
        (-45.0, 15.0, 90.0),
        (120.0, -35.0, -110.0),
        (0.0, 90.0, 0.0),
        (0.0, -90.0, 0.0),
        (15.0, 90.0, 45.0),
        (-20.0, -90.0, 60.0),
    ]
    for roll, pitch, yaw in test_cases:
        mat = euler_to_matrix(roll, pitch, yaw)
        r2, p2, y2 = matrix_to_euler(mat)
        mat2 = euler_to_matrix(r2, p2, y2)
        diff = max(abs(mat[i][j] - mat2[i][j]) for i in range(3) for j in range(3))
        assert diff < 1e-5, f"Failed for ({roll}, {pitch}, {yaw})"


def test_vector_rotation_inverse() -> None:
    vec = (12.3, -45.6, 78.9)
    rot = (25.0, -35.0, 45.0)
    rotated = rotate_vector(vec, rot)
    restored = inverse_rotate_vector(rotated, rot)
    for i in range(3):
        assert abs(vec[i] - restored[i]) < 1e-6


def test_resolve_world_transform_hierarchy() -> None:
    comp_a = {
        "id": "a",
        "name": "Comp A",
        "transform": {
            "position": {"x": 100.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 90.0},
        },
    }
    # Comp B is 50 mm forward along X in A's local frame.
    # Since A has yaw=90 deg, in world coordinates this is +50 mm along Y!
    comp_b = {
        "id": "b",
        "name": "Comp B",
        "parent": "a",
        "transform": {
            "position": {"x": 50.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
    }
    comps = {"a": comp_a, "b": comp_b}
    w_pos, w_rot = resolve_world_transform("b", comps)

    assert abs(w_pos[0] - 100.0) < 1e-4
    assert abs(w_pos[1] - 50.0) < 1e-4
    assert abs(w_pos[2] - 0.0) < 1e-4
    assert abs(w_rot[2] - 90.0) < 1e-4


def test_resolve_world_transform_child_follows_parent_frame() -> None:
    propulsion = {
        "id": "propulsion",
        "name": "Propulsion",
        "has_transform": False,
    }
    motor = {
        "id": "motor-1",
        "name": "Motor 1",
        "parent": "propulsion",
        "transform": {
            "position": {"x": 800.0, "y": 0.0, "z": 25.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 180.0},
        },
    }
    propeller = {
        "id": "prop-1",
        "name": "Propeller",
        "parent": "motor-1",
        "transform": {
            "position": {"x": -35.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
    }
    comps = {"propulsion": propulsion, "motor-1": motor, "prop-1": propeller}
    w_pos, w_rot = resolve_world_transform("prop-1", comps)

    # Motor at x=800 with yaw=180 deg. Propeller at local -35 along X.
    # In yaw=180 frame, local -X points in world +X direction: 800 - (-35) = 835.
    assert abs(w_pos[0] - 835.0) < 1e-4
    assert abs(w_pos[1] - 0.0) < 1e-4
    assert abs(w_pos[2] - 25.0) < 1e-4
    assert abs(w_rot[2] - 180.0) < 1e-4


def test_resolve_world_transform_skips_non_spatial_containers() -> None:
    airframe = {
        "id": "airframe",
        "name": "Airframe",
        "type": "org.setuav.core:airframe",
        "has_transform": False,
        "transform": {"position": {"x": 999.0, "y": 0.0, "z": 0.0}},
    }
    wing = {
        "id": "wing-1",
        "name": "Main Wing",
        "parent": "airframe",
        "transform": {
            "position": {"x": 200.0, "y": 0.0, "z": 50.0},
            "rotation": {"roll": 0.0, "pitch": 2.0, "yaw": 0.0},
        },
    }
    comps = {"airframe": airframe, "wing-1": wing}
    w_pos, w_rot = resolve_world_transform("wing-1", comps)

    assert abs(w_pos[0] - 200.0) < 1e-4
    assert abs(w_pos[2] - 50.0) < 1e-4
    assert abs(w_rot[1] - 2.0) < 1e-4


def test_resolve_world_transform_cycle_detection() -> None:
    # A points to B, B points to A -> should break cycle gracefully
    comp_a = {
        "id": "a",
        "parent": "b",
        "transform": {"position": {"x": 10.0, "y": 0.0, "z": 0.0}},
    }
    comp_b = {
        "id": "b",
        "parent": "a",
        "transform": {"position": {"x": 20.0, "y": 0.0, "z": 0.0}},
    }
    comps = {"a": comp_a, "b": comp_b}
    w_pos, _ = resolve_world_transform("a", comps)
    # Should not raise RecursionError and return finite coordinates
    assert math.isfinite(w_pos[0])


def test_reparent_preserves_world_transform() -> None:
    parent_a = {
        "id": "parent_a",
        "name": "Parent A",
        "transform": {
            "position": {"x": 100.0, "y": 50.0, "z": 20.0},
            "rotation": {"roll": 10.0, "pitch": 20.0, "yaw": 30.0},
        },
    }
    child = {
        "id": "child",
        "name": "Child",
        "transform": {
            "position": {"x": 150.0, "y": 70.0, "z": 40.0},
            "rotation": {"roll": 15.0, "pitch": 25.0, "yaw": 35.0},
        },
    }
    comps = {"parent_a": parent_a, "child": child}

    w_pos_before, w_rot_before = resolve_world_transform("child", comps)

    # Reparent child to parent_a
    reparent_component(child, "parent_a", comps, preserve_world_transform=True)

    assert child.get("parent") == "parent_a"
    w_pos_after, w_rot_after = resolve_world_transform("child", comps)

    for i in range(3):
        assert abs(w_pos_before[i] - w_pos_after[i]) < 1e-3
        assert abs(w_rot_before[i] - w_rot_after[i]) < 1e-3

    # Detach back to World
    reparent_component(child, None, comps, preserve_world_transform=True)
    assert child.get("parent") is None
    w_pos_detached, w_rot_detached = resolve_world_transform("child", comps)

    for i in range(3):
        assert abs(w_pos_before[i] - w_pos_detached[i]) < 1e-3
        assert abs(w_rot_before[i] - w_rot_detached[i]) < 1e-3


def test_studio_api_reparent_undo_redo() -> None:
    api = StudioAPI()
    box = {
        "id": "box_1",
        "name": "Box 1",
        "transform": {
            "position": {"x": 100.0, "y": 50.0, "z": 20.0},
            "rotation": {"roll": 10.0, "pitch": 20.0, "yaw": 30.0},
        },
    }
    cyl = {
        "id": "cyl_1",
        "name": "Cyl 1",
        "transform": {
            "position": {"x": 150.0, "y": 70.0, "z": 40.0},
            "rotation": {"roll": 15.0, "pitch": 25.0, "yaw": 35.0},
        },
    }
    proj = ProjectDocument(Path("test.json"), "json", {"components": [box, cyl]})
    api.current_project = proj

    w_pos_before, _ = resolve_world_transform("cyl_1", proj)

    # Reparent via API
    api.reparent_component(cyl, "box_1", preserve_world_transform=True)
    assert cyl.get("parent") == "box_1"

    w_pos_after, _ = resolve_world_transform("cyl_1", proj)
    for i in range(3):
        assert abs(w_pos_before[i] - w_pos_after[i]) < 1e-3

    # Undo
    api.undo()
    assert cyl.get("parent") is None
    assert cyl["transform"]["position"]["x"] == 150.0
    w_pos_undo, _ = resolve_world_transform("cyl_1", proj)
    assert abs(w_pos_before[0] - w_pos_undo[0]) < 1e-3

    # Redo
    api.redo()
    assert cyl.get("parent") == "box_1"
    w_pos_redo, _ = resolve_world_transform("cyl_1", proj)
    assert abs(w_pos_before[0] - w_pos_redo[0]) < 1e-3
