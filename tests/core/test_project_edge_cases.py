"""Boundary and failure-path tests for project persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from setuav_studio.project import (
    ProjectDocument,
    ProjectOpenError,
    ProjectSaveError,
    _write_json_file,
    _write_suav,
    open_project,
    save_project,
)


class ProjectEdgeCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.data = {"name": "Project", "components": []}

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_document_state_and_extension_helpers_handle_missing_data(self) -> None:
        folder_document = ProjectDocument(self.root / "project.json", "folder", {})
        json_document = ProjectDocument(self.root / "other.json", "json", {})
        self.assertEqual(folder_document.location, self.root)
        self.assertEqual(json_document.location, json_document.path)
        self.assertFalse(folder_document.degraded)
        folder_document.plugin_issues.append("missing plugin")
        self.assertTrue(folder_document.degraded)

        self.assertEqual(folder_document.get_plugin_data("missing", "fallback"), "fallback")
        folder_document.data["extensions"] = "invalid"
        folder_document.set_plugin_data("plugin", {"enabled": True})
        self.assertEqual(folder_document.get_plugin_data("plugin"), {"enabled": True})
        folder_document.remove_plugin_data("missing")
        folder_document.remove_plugin_data("plugin")
        self.assertIsNone(folder_document.get_plugin_data("plugin"))
        folder_document.data["extensions"] = "invalid"
        folder_document.remove_plugin_data("plugin")

    def test_component_extension_helpers_handle_invalid_and_missing_components(self) -> None:
        document = ProjectDocument(self.root / "project.json", "json", {"components": "invalid"})
        self.assertIsNone(document.get_component("missing"))
        self.assertEqual(
            document.get_component_plugin_data("missing", "ext", "fallback"), "fallback"
        )
        with self.assertRaises(KeyError):
            document.set_component_plugin_data("missing", "ext", {})

        component = {"id": "wing", "extensions": "invalid"}
        document.data["components"] = ["invalid", component]
        self.assertEqual(document.get_component_plugin_data("wing", "ext", "fallback"), "fallback")
        document.set_component_plugin_data("wing", "ext", {"value": 1})
        self.assertEqual(document.get_component_plugin_data("wing", "ext"), {"value": 1})

    def test_open_rejects_unsupported_invalid_and_non_object_json(self) -> None:
        with self.assertRaisesRegex(ProjectOpenError, "Expected a project"):
            open_project(self.root / "project.txt")

        invalid_json = self.root / "project.json"
        invalid_json.write_text("{invalid", encoding="utf-8")
        with self.assertRaisesRegex(ProjectOpenError, "Cannot read project file"):
            open_project(invalid_json)

        invalid_json.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ProjectOpenError, "must contain a JSON object"):
            open_project(invalid_json)

    def test_open_archive_reports_missing_root_file_corruption_and_missing_path(self) -> None:
        missing = self.root / "missing.suav"
        with self.assertRaisesRegex(ProjectOpenError, "archive not found"):
            open_project(missing)

        no_project = self.root / "no-project.suav"
        with ZipFile(no_project, "w") as archive:
            archive.writestr("asset.txt", "data")
        with self.assertRaisesRegex(ProjectOpenError, "no project.json"):
            open_project(no_project)

        corrupt = self.root / "corrupt.suav"
        corrupt.write_bytes(b"not a zip")
        with self.assertRaisesRegex(ProjectOpenError, "Cannot read project archive"):
            open_project(corrupt)

        invalid_json = self.root / "invalid-json.suav"
        with ZipFile(invalid_json, "w") as archive:
            archive.writestr("project.json", "{invalid")
        with self.assertRaisesRegex(ProjectOpenError, "Cannot read project archive"):
            open_project(invalid_json)

    def test_save_folder_in_place_preserves_kind(self) -> None:
        project_file = self.root / "project.json"
        project_file.write_text(json.dumps(self.data), encoding="utf-8")
        project = open_project(self.root)
        project.data["name"] = "Changed"

        save_project(project)

        self.assertEqual(project.kind, "folder")
        self.assertEqual(project.path, project_file)
        self.assertEqual(json.loads(project_file.read_text(encoding="utf-8"))["name"], "Changed")

    def test_save_as_json_updates_location_and_rejects_unknown_target(self) -> None:
        project = ProjectDocument(self.root / "original.json", "json", self.data, modified=True)
        target = self.root / "nested" / "project.json"

        save_project(project, target)
        self.assertEqual(project.path, target.resolve())
        self.assertEqual(project.kind, "json")
        self.assertFalse(project.modified)

        with self.assertRaisesRegex(ProjectSaveError, "Expected project.json"):
            save_project(project, self.root / "invalid.json")

    def test_save_wraps_os_errors(self) -> None:
        project = ProjectDocument(self.root / "project.json", "json", self.data)
        with (
            patch(
                "setuav_studio.project.document._write_json_file", side_effect=OSError("disk full")
            ),
            self.assertRaisesRegex(ProjectSaveError, "Cannot save project"),
        ):
            save_project(project)

    def test_atomic_json_writer_removes_temporary_file_after_replace_failure(self) -> None:
        target = self.root / "project.json"
        with (
            patch(
                "setuav_studio.project.document.os.replace", side_effect=OSError("replace failed")
            ),
            self.assertRaises(OSError),
        ):
            _write_json_file(target, self.data)

        self.assertEqual(list(self.root.glob(".project.json.*.tmp")), [])

    def test_atomic_archive_writer_removes_temporary_file_after_failure(self) -> None:
        target = self.root / "project.suav"
        project = ProjectDocument(self.root / "project.json", "json", self.data)
        with (
            patch(
                "setuav_studio.project.document.os.replace", side_effect=OSError("replace failed")
            ),
            self.assertRaises(OSError),
        ):
            _write_suav(project, target)

        self.assertEqual(list(self.root.glob(".project.suav.*.tmp")), [])

    def test_resaving_archive_preserves_assets_and_replaces_project_json(self) -> None:
        source = self.root / "source.suav"
        with ZipFile(source, "w") as archive:
            archive.writestr("project.json", json.dumps(self.data))
            archive.writestr("assets/note.txt", "asset")
        project = open_project(source)
        project.data["name"] = "Changed"
        target = self.root / "target.suav"

        save_project(project, target)

        with ZipFile(target) as archive:
            self.assertEqual(archive.read("assets/note.txt"), b"asset")
            self.assertEqual(json.loads(archive.read("project.json"))["name"], "Changed")

    def test_saving_missing_archive_source_and_json_project_skips_asset_copy(self) -> None:
        missing_archive = ProjectDocument(self.root / "missing.suav", "archive", self.data)
        archive_target = self.root / "from-missing.suav"
        save_project(missing_archive, archive_target)
        with ZipFile(archive_target) as archive:
            self.assertEqual(archive.namelist(), ["project.json"])

        json_project = ProjectDocument(self.root / "project.json", "json", self.data)
        json_target = self.root / "from-json.suav"
        save_project(json_project, json_target)
        with ZipFile(json_target) as archive:
            self.assertEqual(archive.namelist(), ["project.json"])


if __name__ == "__main__":
    unittest.main()
