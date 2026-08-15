import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from setuav_studio.project import ProjectOpenError, open_project


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

    def test_rejects_folder_without_project_json(self) -> None:
        with self.assertRaises(ProjectOpenError):
            open_project(self.root)

    def _write_project_json(self) -> Path:
        project_file = self.root / "project.json"
        project_file.write_text(json.dumps(self.project_data), encoding="utf-8")
        return project_file


if __name__ == "__main__":
    unittest.main()
