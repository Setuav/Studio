import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from setuav_studio.project import ProjectOpenError, open_project, save_project


class ProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.project_data = {"spec_version": "2.0.0", "name": "Test Project"}

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_opens_project_folder(self) -> None:
        self._write_project_json()

        project = open_project(self.root)

        self.assertEqual(project.kind, "folder")
        self.assertEqual(project.data, self.project_data)

    def test_opens_project_json(self) -> None:
        project_file = self._write_project_json()

        project = open_project(project_file)

        self.assertEqual(project.kind, "json")
        self.assertEqual(project.data, self.project_data)

    def test_opens_suav_archive(self) -> None:
        archive_path = self.root / "test.suav"
        with ZipFile(archive_path, "w") as archive:
            archive.writestr("project.json", json.dumps(self.project_data))

        project = open_project(archive_path)

        self.assertEqual(project.kind, "archive")
        self.assertEqual(project.data, self.project_data)

    def test_save_rejects_read_only_project(self) -> None:
        """4.13: read-only projects (opened under a failing validation) refuse to save."""
        from setuav_studio.project import ProjectSaveError, ProjectDocument

        project = ProjectDocument(
            path=Path("/tmp/ro.json"),
            kind="json",
            data={"name": "ro"},
            read_only=True,
        )
        with self.assertRaises(ProjectSaveError):
            save_project(project)


    def test_rejects_folder_without_project_json(self) -> None:
        with self.assertRaises(ProjectOpenError):
            open_project(self.root)

    def test_saves_project_json(self) -> None:
        project = open_project(self._write_project_json())
        project.data["name"] = "Changed"
        project.modified = True

        save_project(project)

        self.assertEqual(open_project(project.path).data["name"], "Changed")
        self.assertFalse(project.modified)

    def test_saves_folder_as_archive_with_assets(self) -> None:
        self._write_project_json()
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "note.txt").write_text("asset", encoding="utf-8")
        project = open_project(self.root)
        archive_path = self.root.parent / f"{self.root.name}.suav"
        self.addCleanup(archive_path.unlink, missing_ok=True)

        save_project(project, archive_path)

        with ZipFile(archive_path) as archive:
            self.assertEqual(archive.read("assets/note.txt"), b"asset")
            self.assertEqual(
                json.loads(archive.read("project.json")),
                self.project_data,
            )

    def _write_project_json(self) -> Path:
        project_file = self.root / "project.json"
        project_file.write_text(json.dumps(self.project_data), encoding="utf-8")
        return project_file


if __name__ == "__main__":
    unittest.main()
