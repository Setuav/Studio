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
        from setuav_studio.project import ProjectDocument, ProjectSaveError

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

    def test_lossless_extension_roundtrip_and_helpers(self) -> None:
        """Verify extensions are preserved on roundtrip and helpers work seamlessly."""
        self.project_data["components"] = [
            {
                "id": "wing_1",
                "name": "Main Wing",
                "type": "org.setuav.core:lifting-surface",
                "extensions": {
                    "com.thirdparty.solar": {"cell_count": 36, "efficiency": 0.22},
                },
            }
        ]
        self.project_data["extensions"] = {
            "com.thirdparty.mission": {"waypoint_count": 12},
        }
        project_file = self._write_project_json()
        project = open_project(project_file)

        # 1. Read extensions via helpers
        self.assertEqual(project.get_extension("com.thirdparty.mission"), {"waypoint_count": 12})
        self.assertEqual(
            project.get_component_extension("wing_1", "com.thirdparty.solar"),
            {"cell_count": 36, "efficiency": 0.22},
        )
        self.assertIsNone(project.get_extension("nonexistent"))

        # 2. Modify extensions via helpers
        project.set_extension("com.thirdparty.mission", {"waypoint_count": 24})
        project.set_component_extension(
            "wing_1", "com.thirdparty.solar", {"cell_count": 48, "efficiency": 0.24}
        )
        save_project(project)

        # 3. Reload from disk and verify lossless preservation
        reloaded = open_project(project_file)
        self.assertEqual(reloaded.get_extension("com.thirdparty.mission")["waypoint_count"], 24)
        self.assertEqual(
            reloaded.get_component_extension("wing_1", "com.thirdparty.solar")["cell_count"], 48
        )

    def test_undo_redo_extension_edits_via_studio_api(self) -> None:
        """Verify StudioAPI.edit_project_extension and edit_component_extension support Undo/Redo."""
        from setuav_studio.plugin_system import StudioAPI

        self.project_data["components"] = [
            {"id": "c1", "name": "Test Comp", "type": "org.setuav.core:generic", "extensions": {}}
        ]
        self.project_data["extensions"] = {}
        project = open_project(self._write_project_json())

        api = StudioAPI()
        api.set_project(project)

        # 1. Edit project extension
        api.edit_project_extension(
            "com.example.test",
            "Set test config",
            lambda ext: ext.update({"alpha": 10}),
        )
        self.assertEqual(project.get_extension("com.example.test")["alpha"], 10)

        # 2. Undo project extension edit
        api.undo()
        self.assertIsNone(project.get_extension("com.example.test"))

        # 3. Redo project extension edit
        api.undo_stack.redo()
        self.assertEqual(project.get_extension("com.example.test")["alpha"], 10)

        # 4. Edit component extension
        api.edit_component_extension(
            "c1",
            "com.example.comp_ext",
            "Set comp prop",
            lambda ext: ext.update({"gain": 1.5}),
        )
        self.assertEqual(project.get_component_extension("c1", "com.example.comp_ext")["gain"], 1.5)

        # 5. Undo component extension edit
        api.undo()
        self.assertIsNone(project.get_component_extension("c1", "com.example.comp_ext"))

    def _write_project_json(self) -> Path:
        project_file = self.root / "project.json"
        project_file.write_text(json.dumps(self.project_data), encoding="utf-8")
        return project_file


if __name__ == "__main__":
    unittest.main()
