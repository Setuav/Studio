"""Unit tests for ProjectDocument lifecycle, persistence, undo/redo, and extension data."""

from __future__ import annotations

import json
import math
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest

from setuav_studio.project import (
    ProjectDocument,
    ProjectOpenError,
    ProjectSaveError,
    create_project,
    open_project,
    save_project,
)


def test_create_project_builds_valid_archive(tmp_path: Path) -> None:
    suav_path = tmp_path / "airplane.suav"
    project = create_project(suav_path)

    assert project.kind == "archive"
    assert project.modified
    assert project.data["name"] == "airplane"
    assert project.data["components"] == []
    assert project.data["plugins"] == []

    # Saving created project creates the file on disk
    save_project(project)
    assert suav_path.exists()
    assert not project.modified

    # Reject unsupported extensions
    with pytest.raises(ProjectSaveError):
        create_project(tmp_path / "test.unsupported")


def test_open_project_json(tmp_path: Path) -> None:
    json_path = tmp_path / "project.json"
    data = {"spec_version": "2.0.0", "name": "JSON Plane", "components": []}
    json_path.write_text(json.dumps(data), encoding="utf-8")

    project = open_project(json_path)
    assert project.kind == "json"
    assert project.data["name"] == "JSON Plane"
    assert not project.modified


def test_open_project_folder(tmp_path: Path) -> None:
    data = {"spec_version": "2.0.0", "name": "Folder Plane", "components": []}
    (tmp_path / "project.json").write_text(json.dumps(data), encoding="utf-8")

    project = open_project(tmp_path)
    assert project.kind == "folder"
    assert project.data["name"] == "Folder Plane"


def test_open_project_suav_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.suav"
    data = {"spec_version": "2.0.0", "name": "Archived Plane", "components": []}
    with ZipFile(archive_path, "w") as zf:
        zf.writestr("project.json", json.dumps(data))

    project = open_project(archive_path)
    assert project.kind == "archive"
    assert project.data["name"] == "Archived Plane"


def test_open_project_errors(tmp_path: Path) -> None:
    # 1. Non-existent path
    with pytest.raises(ProjectOpenError):
        open_project(tmp_path / "does_not_exist.suav")

    # 2. Folder without project.json
    empty_folder = tmp_path / "empty_dir"
    empty_folder.mkdir()
    with pytest.raises(ProjectOpenError):
        open_project(empty_folder)

    # 3. Corrupt archive
    corrupt = tmp_path / "corrupt.suav"
    corrupt.write_bytes(b"not a valid zip file")
    with pytest.raises(ProjectOpenError):
        open_project(corrupt)


def test_save_rejects_read_only_project(tmp_path: Path) -> None:
    project = ProjectDocument(
        path=tmp_path / "ro.json",
        kind="json",
        data={"name": "read_only"},
        read_only=True,
    )
    with pytest.raises(ProjectSaveError):
        save_project(project)


def test_save_folder_as_archive_with_assets(tmp_path: Path) -> None:
    folder = tmp_path / "uav_folder"
    folder.mkdir()
    (folder / "project.json").write_text(json.dumps({"name": "Asset Plane"}), encoding="utf-8")
    assets_dir = folder / "assets"
    assets_dir.mkdir()
    (assets_dir / "airfoil.dat").write_text("airfoil data", encoding="utf-8")

    project = open_project(folder)
    target_archive = tmp_path / "exported.suav"
    save_project(project, target_archive)

    assert target_archive.exists()
    with ZipFile(target_archive, "r") as zf:
        assert json.loads(zf.read("project.json"))["name"] == "Asset Plane"
        assert zf.read("assets/airfoil.dat") == b"airfoil data"


def test_plugin_data_and_extensions_roundtrip(tmp_path: Path) -> None:
    project = create_project(tmp_path / "ext_test.suav")
    project.data["components"] = [
        {
            "id": "wing-1",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
        }
    ]

    # 1. Set & Get Root Plugin Data
    project.set_plugin_data("mission_plugin", {"waypoints": [1, 2, 3]})
    assert project.get_plugin_data("mission_plugin") == {"waypoints": [1, 2, 3]}
    assert project.get_plugin_data("unknown", default="fallback") == "fallback"

    # 2. Set & Get Component Plugin Data
    project.set_component_plugin_data("wing-1", "aero_plugin", {"cl_max": 1.4})
    assert project.get_component_plugin_data("wing-1", "aero_plugin") == {"cl_max": 1.4}
    assert project.get_component_plugin_data("wing-1", "missing", default=None) is None
    assert (
        project.get_component_plugin_data("missing-comp", "aero_plugin", default="missing")
        == "missing"
    )

    # 3. Remove Plugin Data
    project.remove_plugin_data("mission_plugin")
    assert project.get_plugin_data("mission_plugin") is None

    # 4. Save and reload
    save_project(project)
    reloaded = open_project(project.path)
    assert reloaded.get_component_plugin_data("wing-1", "aero_plugin") == {"cl_max": 1.4}


def test_component_lookup_helpers() -> None:
    doc = ProjectDocument(
        Path("test.json"),
        "json",
        {
            "components": [
                {"id": "c1", "name": "Fuselage"},
                {"id": "c2", "name": "Wing", "parent": "c1"},
            ]
        },
    )
    assert doc.get_component("c1") == {"id": "c1", "name": "Fuselage"}
    assert doc.get_component("missing") is None

    # Non-list components fallback
    doc_corrupt = ProjectDocument(Path("test.json"), "json", {"components": "invalid"})
    assert doc_corrupt.get_component("c1") is None


def test_safe_json_serialization_numpy_and_paths(tmp_path: Path) -> None:
    project = create_project(tmp_path / "numpy_test.suav")
    project.data["parameters"] = {
        "float_val": np.float64(2.71828),
        "int_val": np.int32(100),
        "array_val": np.array([10.0, 20.0, 30.0]),
        "path_val": Path("/tmp/uav"),
        "set_val": {"alpha", "beta"},
    }
    save_project(project)

    reloaded = open_project(project.path)
    params = reloaded.data["parameters"]
    assert math.isclose(params["float_val"], 2.71828, rel_tol=1e-5)
    assert params["int_val"] == 100
    assert params["array_val"] == [10.0, 20.0, 30.0]
    assert params["path_val"] == "/tmp/uav"
    assert set(params["set_val"]) == {"alpha", "beta"}


def test_save_project_validation_prevents_corrupt_hierarchy(tmp_path: Path) -> None:
    project = create_project(tmp_path / "cyclic_test.suav")
    # Circular parent dependency: A -> B -> A
    project.data["components"] = [
        {"id": "a", "name": "Comp A", "parent": "b"},
        {"id": "b", "name": "Comp B", "parent": "a"},
    ]
    with pytest.raises(ProjectSaveError):
        save_project(project)


def test_typed_component_and_mass_properties() -> None:
    doc = ProjectDocument(
        Path("test.json"),
        "json",
        {
            "components": [
                {
                    "id": "c1",
                    "name": "Main Wing",
                    "type": "org.setuav.core:generic",
                    "mass": 2500.0,
                    "cg": [1.0, 0.0, 0.2],
                }
            ]
        },
    )
    typed = doc.get_typed_component("c1")
    assert typed is not None
    assert typed.name == "Main Wing"
    assert doc.get_typed_component("nonexistent") is None

    mass_props = doc.mass_properties
    assert mass_props is not None
    assert math.isclose(mass_props.mass_kg, 2.5)
    assert doc.get_mass_properties() == mass_props
