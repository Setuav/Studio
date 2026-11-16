"""Unit tests for core spatial transform and attachment utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from setuav_studio.api.api import StudioAPI
from setuav_studio.project.document import ProjectDocument
from setuav_studio.utilities.transform import (
    attach_component,
    attached_component_ids,
    components_by_id,
    euler_to_matrix,
    inverse_rotate_vector,
    matrix_to_euler,
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


def test_resolve_world_transform_follows_attachments() -> None:
    comp_a = {
        "id": "a",
        "name": "Comp A",
        "transform": {
            "position": {"x": 100.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 90.0},
        },
    }
    # B sits 50 mm along A's local X; A is yawed 90 deg, so that is +50 mm along Y.
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


def test_resolve_world_transform_chains_rotated_frames() -> None:
    fuselage = {"id": "fuselage", "name": "Fuselage"}
    motor = {
        "id": "motor-1",
        "name": "Motor 1",
        "attach_to": "fuselage",
        "transform": {
            "position": {"x": 800.0, "y": 0.0, "z": 25.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 180.0},
        },
    }
    spinner = {
        "id": "spinner",
        "name": "Spinner",
        "attach_to": "motor-1",
        "transform": {
            "position": {"x": -35.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
    }
    comps = {"fuselage": fuselage, "motor-1": motor, "spinner": spinner}
    w_pos, w_rot = resolve_world_transform("spinner", comps)

    # Motor at x=800 with yaw=180 deg; local -X points along vehicle +X: 800 + 35 = 835.
    assert abs(w_pos[0] - 835.0) < 1e-4
    assert abs(w_pos[1] - 0.0) < 1e-4
    assert abs(w_pos[2] - 25.0) < 1e-4
    assert abs(w_rot[2] - 180.0) < 1e-4


def test_resolve_world_transform_cycle_detection() -> None:
    comp_a = {
        "id": "a",
        "attach_to": "b",
        "transform": {"position": {"x": 10.0, "y": 0.0, "z": 0.0}},
    }
    comp_b = {
        "id": "b",
        "attach_to": "a",
        "transform": {"position": {"x": 20.0, "y": 0.0, "z": 0.0}},
    }
    comps = {"a": comp_a, "b": comp_b}
    with pytest.raises(ValueError, match="attachment cycle"):
        resolve_world_transform("a", comps)


def test_resolve_world_transform_rejects_unknown_components() -> None:
    orphan = {"id": "orphan", "attach_to": "missing"}
    with pytest.raises(ValueError, match="'missing', which 'orphan' attaches to, is not in"):
        resolve_world_transform("orphan", {"orphan": orphan})
    with pytest.raises(ValueError, match="'unknown' is not in"):
        resolve_world_transform("unknown", {"orphan": orphan})


def _placed(component_id: str, x: float, yaw: float, **extra: Any) -> dict[str, Any]:
    return {
        "id": component_id,
        "name": component_id,
        "transform": {
            "position": {"x": x, "y": 20.0, "z": 10.0},
            "rotation": {"roll": 5.0, "pitch": 10.0, "yaw": yaw},
        },
        **extra,
    }


def test_attach_preserving_the_world_transform_keeps_the_component_in_place() -> None:
    target = _placed("target", 100.0, 30.0)
    child = _placed("child", 150.0, 35.0)
    comps = {"target": target, "child": child}
    before = resolve_world_transform("child", comps)

    attach_component(child, "target", comps, preserve_world_transform=True)
    assert child["attach_to"] == "target"
    after = resolve_world_transform("child", comps)
    for expected, actual in zip(before, after, strict=True):
        assert actual == pytest.approx(expected, abs=1e-3)

    attach_component(child, None, comps, preserve_world_transform=True)
    assert "attach_to" not in child
    detached = resolve_world_transform("child", comps)
    for expected, actual in zip(before, detached, strict=True):
        assert actual == pytest.approx(expected, abs=1e-3)


def test_attach_keeping_the_local_transform_moves_with_the_target_frame() -> None:
    target = {"id": "target", "transform": {"position": {"x": 100.0, "y": 0.0, "z": 0.0}}}
    child = _placed("child", 50.0, 0.0)
    comps = {"target": target, "child": child}

    attach_component(child, "target", comps, preserve_world_transform=False)

    assert child["transform"]["position"]["x"] == 50.0
    world_pos, _ = resolve_world_transform("child", comps)
    assert world_pos == pytest.approx((150.0, 20.0, 10.0), abs=1e-6)


def test_attach_rejects_unknown_targets_and_cycles() -> None:
    a = _placed("a", 0.0, 0.0)
    b = _placed("b", 10.0, 0.0, attach_to="a")
    c = _placed("c", 20.0, 0.0, attach_to="b")
    comps = {"a": a, "b": b, "c": c}

    assert attached_component_ids("a", comps) == {"b", "c"}
    with pytest.raises(ValueError, match="'missing' is not in"):
        attach_component(a, "missing", comps, preserve_world_transform=True)
    for target in ("a", "c"):
        with pytest.raises(ValueError, match="cycle"):
            attach_component(a, target, comps, preserve_world_transform=True)
    assert "attach_to" not in a


def test_studio_api_attach_undo_redo() -> None:
    api = StudioAPI()
    box = _placed("box_1", 100.0, 30.0)
    cyl = _placed("cyl_1", 150.0, 35.0)
    proj = ProjectDocument(Path("test.json"), "json", {"components": [box, cyl]})
    api._host.set_project(proj)
    w_pos_before, _ = resolve_world_transform("cyl_1", components_by_id(proj))

    api.attach_component(cyl, "box_1", preserve_world_transform=True)
    assert cyl["attach_to"] == "box_1"
    w_pos_after, _ = resolve_world_transform("cyl_1", components_by_id(proj))
    assert w_pos_after == pytest.approx(w_pos_before, abs=1e-3)

    api.undo()
    assert "attach_to" not in cyl
    assert cyl["transform"]["position"]["x"] == 150.0

    api.redo()
    assert cyl["attach_to"] == "box_1"
    w_pos_redo, _ = resolve_world_transform("cyl_1", components_by_id(proj))
    assert w_pos_redo == pytest.approx(w_pos_before, abs=1e-3)
