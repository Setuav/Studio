"""Unit tests for ProjectDocument lifecycle, persistence, undo/redo, and extension data."""

from __future__ import annotations

import json
import math
from importlib.metadata import version
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
    assert project.name == "airplane"
    assert "name" not in project.data
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
    data = {"format_version": "1.0", "components": []}
    json_path.write_text(json.dumps(data), encoding="utf-8")

    project = open_project(json_path)
    assert project.kind == "json"
    assert project.name == tmp_path.name
    assert not project.modified


def test_open_project_folder(tmp_path: Path) -> None:
    data = {"format_version": "1.0", "components": []}
    (tmp_path / "project.json").write_text(json.dumps(data), encoding="utf-8")

    project = open_project(tmp_path)
    assert project.kind == "folder"
    assert project.name == tmp_path.name


def test_open_project_suav_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.suav"
    data = {"format_version": "1.0", "components": []}
    with ZipFile(archive_path, "w") as zf:
        zf.writestr("project.json", json.dumps(data))

    project = open_project(archive_path)
    assert project.kind == "archive"
    assert project.name == "archive"


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
    (folder / "project.json").write_text(
        json.dumps({"format_version": "1.0", "components": []}), encoding="utf-8"
    )
    assets_dir = folder / "assets"
    assets_dir.mkdir()
    (assets_dir / "airfoil.dat").write_text("airfoil data", encoding="utf-8")

    project = open_project(folder)
    target_archive = tmp_path / "exported.suav"
    save_project(project, target_archive)

    assert target_archive.exists()
    with ZipFile(target_archive, "r") as zf:
        assert json.loads(zf.read("project.json")) == {
            "format_version": "1.0",
            "studio_version": version("setuav-studio"),
            "components": [],
        }
        assert zf.read("assets/airfoil.dat") == b"airfoil data"


def test_extensions_roundtrip(tmp_path: Path) -> None:
    project = create_project(tmp_path / "ext_test.suav")
    project.data["components"] = [
        {
            "id": "wing-1",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
            "extensions": {"aero_plugin": {"cl_max": 1.4}},
        }
    ]
    project.data["extensions"] = {"mission_plugin": {"waypoints": [1, 2, 3]}}

    save_project(project)
    reloaded = open_project(project.path)
    assert reloaded.data["extensions"] == {"mission_plugin": {"waypoints": [1, 2, 3]}}
    assert reloaded.data["components"][0]["extensions"] == {"aero_plugin": {"cl_max": 1.4}}


def test_component_lookup_helpers() -> None:
    doc = ProjectDocument(
        Path("test.json"),
        "json",
        {
            "components": [
                {"id": "c1", "name": "Fuselage"},
                {"id": "c2", "name": "Wing", "attach_to": "c1"},
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
    # Attachment cycle: A -> B -> A
    project.data["components"] = [
        {"id": "a", "name": "Comp A", "attach_to": "b"},
        {"id": "b", "name": "Comp B", "attach_to": "a"},
    ]
    with pytest.raises(ProjectSaveError):
        save_project(project)


def test_mass_properties() -> None:
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
                    "transform": {"position": {"x": 400.0, "y": 0.0, "z": 100.0}},
                    "local_cg_mm": {"x": 100.0, "y": 0.0, "z": 50.0},
                    "inertia_kg_m2": {"ixx": 0.1, "iyy": 0.2, "izz": 0.3},
                }
            ]
        },
    )
    mass_props = doc.mass_properties
    assert mass_props is not None
    assert math.isclose(mass_props.mass_kg, 2.5)
    assert math.isclose(mass_props.cg_body_m[0], 0.5)
    assert math.isclose(mass_props.cg_body_m[1], 0.0)
    assert math.isclose(mass_props.cg_body_m[2], 0.15)
    assert math.isclose(mass_props.inertia_cg_kg_m2.ixx, 0.1)
    assert math.isclose(mass_props.inertia_cg_kg_m2.iyy, 0.2)
    assert math.isclose(mass_props.inertia_cg_kg_m2.izz, 0.3)


def test_save_records_the_format_and_studio_version(tmp_path: Path) -> None:
    project = create_project(tmp_path / "plane.suav")
    project.data.pop("format_version")
    save_project(project)
    with ZipFile(tmp_path / "plane.suav") as archive:
        data = json.loads(archive.read("project.json"))
    assert data["format_version"] == "1.0"
    assert data["studio_version"] == version("setuav-studio")


@pytest.mark.parametrize(
    ("format_version", "message"),
    [
        (None, "no valid project format version"),
        (1, "no valid project format version"),
        ("2.0", "Update Setuav Studio"),
        ("0.9", "no longer reads"),
    ],
)
def test_open_rejects_a_format_of_another_major(
    tmp_path: Path, format_version: object, message: str
) -> None:
    path = tmp_path / "project.json"
    path.write_text(
        json.dumps({"format_version": format_version, "components": []}), encoding="utf-8"
    )
    with pytest.raises(ProjectOpenError, match=message):
        open_project(path)


def test_open_warns_about_a_newer_minor(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    path.write_text(
        json.dumps({"format_version": "1.4", "studio_version": "0.3.0", "components": []}),
        encoding="utf-8",
    )
    project = open_project(path)
    assert project.format_warning is not None
    assert "Setuav Studio 0.3.0" in project.format_warning


def test_open_project_respects_recompute_and_api_arguments(tmp_path: Path) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.model.component import Component

    class _WingModel(Component):
        @property
        def custom_metric(self) -> float:
            return 42.0

    path = tmp_path / "project.json"
    path.write_text(
        json.dumps(
            {
                "format_version": "1.0",
                "components": [
                    {"id": "main-wing", "type": "test:wing", "mass": 100.0},
                    {
                        "id": "ballast",
                        "type": "test:mass",
                        "mass": 99.0,
                        "_expressions": {"mass": "= main_wing.custom_metric * 2"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    # Raw read (used by shell open + unsaved-changes diff) does not mutate or produce false errors.
    raw_doc = open_project(path, recompute=False)
    assert raw_doc.expression_diagnostics == []
    assert raw_doc.data["components"][1]["mass"] == 99.0

    # Opening with plugin API evaluates plugin model properties cleanly with zero diagnostics.
    api = StudioAPI()
    api.register_component_model("test:wing", _WingModel)
    hydrated = open_project(path, api=api)
    assert hydrated.expression_diagnostics == []
    assert hydrated.data["components"][1]["mass"] == 84.0
