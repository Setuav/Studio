"""Unit tests for core spatial transform and reparenting utilities."""

from __future__ import annotations

import pytest

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
        "attach_to": "a",
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

    assert child.get("attach_to") == "parent_a"
    w_pos_after, w_rot_after = resolve_world_transform("child", comps)

    for i in range(3):
        assert abs(w_pos_before[i] - w_pos_after[i]) < 1e-3
        assert abs(w_rot_before[i] - w_rot_after[i]) < 1e-3

    # Detach back to World
    reparent_component(child, None, comps, preserve_world_transform=True)
    assert child.get("attach_to") is None
    w_pos_detached, w_rot_detached = resolve_world_transform("child", comps)

    for i in range(3):
        assert abs(w_pos_before[i] - w_pos_detached[i]) < 1e-3
        assert abs(w_rot_before[i] - w_rot_detached[i]) < 1e-3


def test_studio_api_reparent_undo_redo(qtbot: pytest.FixtureRequest) -> None:
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
    from pathlib import Path

    proj = ProjectDocument(Path("test.json"), "json", {"components": [box, cyl]})
    api.current_project = proj

    w_pos_before, w_rot_before = resolve_world_transform("cyl_1", proj)

    # Reparent via API
    api.reparent_component(cyl, "box_1", preserve_world_transform=True)
    assert cyl.get("attach_to") == "box_1"

    w_pos_after, w_rot_after = resolve_world_transform("cyl_1", proj)
    for i in range(3):
        assert abs(w_pos_before[i] - w_pos_after[i]) < 1e-3
        assert abs(w_rot_before[i] - w_rot_after[i]) < 1e-3

    # Undo
    api.undo()
    assert cyl.get("attach_to") is None
    assert cyl["transform"]["position"]["x"] == 150.0
    w_pos_undo, _ = resolve_world_transform("cyl_1", proj)
    assert abs(w_pos_before[0] - w_pos_undo[0]) < 1e-3

    # Redo
    api.redo()
    assert cyl.get("attach_to") == "box_1"
    w_pos_redo, _ = resolve_world_transform("cyl_1", proj)
    assert abs(w_pos_before[0] - w_pos_redo[0]) < 1e-3
