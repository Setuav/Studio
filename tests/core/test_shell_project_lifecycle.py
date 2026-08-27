"""Headless tests for MainWindow project and persistence workflows."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument, ProjectOpenError, ProjectSaveError
from setuav_studio.shell import MainWindow, apply_runtime_validation
from tests._common import get_qapp


class _FakeSettings:
    values: ClassVar[dict[str, object]] = {}

    def value(self, key: str, fallback: object = None) -> object:
        return self.values.get(key, fallback)

    def setValue(self, key: str, value: object) -> None:
        self.values[key] = value

    def remove(self, key: str) -> None:
        self.values.pop(key, None)


class ShellProjectLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.window = MainWindow(self.api)
        self.addCleanup(self.window.deleteLater)
        _FakeSettings.values = {}

    def test_interactive_strict_validation_supports_cancel_and_read_only(self) -> None:
        project = self._project()
        issues = [
            SimpleNamespace(path=f"$.item[{index}]", message="invalid") for index in range(12)
        ]

        with patch("setuav_studio.shell.QMessageBox") as message_box:
            instance = message_box.return_value
            cancel_button = object()
            read_only_button = object()
            instance.addButton.side_effect = [read_only_button, cancel_button]
            instance.clickedButton.return_value = cancel_button
            self.assertEqual(
                apply_runtime_validation(project, issues, "strict", self.window),
                "cancel",
            )
            self.assertIn("and 2 more", instance.setInformativeText.call_args.args[0])

        project.read_only = False
        with patch("setuav_studio.shell.QMessageBox") as message_box:
            instance = message_box.return_value
            instance.addButton.side_effect = [object(), object()]
            instance.clickedButton.return_value = object()
            self.assertEqual(
                apply_runtime_validation(project, issues[:1], "strict", self.window),
                "read_only",
            )
        self.assertTrue(project.read_only)

    def test_open_project_reports_read_errors_and_cancelled_validation(self) -> None:
        with (
            patch("setuav_studio.shell.open_project", side_effect=ProjectOpenError("broken")),
            patch("setuav_studio.shell.QMessageBox.critical") as critical,
        ):
            self.assertFalse(self.window.open_project("broken.json"))
        critical.assert_called_once()

        project = self._project()
        with (
            patch("setuav_studio.shell.open_project", return_value=project),
            patch("setuav_studio.shell.validate_project", return_value=[object()]),
            patch("setuav_studio.shell.apply_runtime_validation", return_value="cancel"),
        ):
            self.assertFalse(self.window.open_project("project.json"))
        self.assertIsNone(self.window._project)

    def test_open_project_respects_unsaved_close_decision(self) -> None:
        project = self._project()
        with (
            patch("setuav_studio.shell.open_project", return_value=project),
            patch("setuav_studio.shell.validate_project", return_value=[]),
            patch.object(self.window, "_confirm_project_close", return_value=False),
        ):
            self.assertFalse(self.window.open_project("project.json"))
        self.assertIsNone(self.window._project)

    def test_open_project_updates_normal_read_only_and_degraded_ui(self) -> None:
        project = self._project()
        with (
            patch("setuav_studio.shell.open_project", return_value=project),
            patch("setuav_studio.shell.validate_project", return_value=[]),
            patch.object(self.window, "_add_recent_project") as add_recent,
        ):
            self.assertTrue(self.window.open_project("project.json"))
        self.assertIs(self.api.current_project, project)
        self.assertIn("Demo", self.window.windowTitle())
        self.assertIn("Project opened: Demo", self.window._status_label.text())
        add_recent.assert_called_once_with(project.location)

        read_only = self._project("Read Only")
        read_only.read_only = True
        with (
            patch("setuav_studio.shell.open_project", return_value=read_only),
            patch("setuav_studio.shell.validate_project", return_value=[object(), object()]),
            patch("setuav_studio.shell.apply_runtime_validation", return_value="read_only"),
            patch.object(self.window, "_confirm_project_close", return_value=True),
            patch.object(self.window, "_add_recent_project"),
        ):
            self.assertTrue(self.window.open_project("readonly.json"))
        self.assertIn("read-only", self.window._status_label.text())
        self.assertFalse(self.window._degraded_badge.isVisible())

        degraded = self._project("Degraded")
        self.api._host.bind_project_requirement_checker(lambda _data: ["Missing plugin: example"])
        with (
            patch("setuav_studio.shell.open_project", return_value=degraded),
            patch("setuav_studio.shell.validate_project", return_value=[]),
            patch.object(self.window, "_confirm_project_close", return_value=True),
            patch.object(self.window, "_add_recent_project"),
        ):
            self.assertTrue(self.window.open_project("degraded.json"))
        self.assertIn("Missing plugin", self.window._degraded_badge.toolTip())
        self.assertIn("Degraded mode", self.window._status_label.text())

    def test_degraded_details_and_window_titles_handle_empty_states(self) -> None:
        with patch("setuav_studio.shell.QMessageBox.warning") as warning:
            self.window._show_degraded_details()
            self.window._project = self._project()
            self.window._show_degraded_details()
            self.window._project.plugin_issues = ["Missing plugin"]
            self.window._show_degraded_details()
        warning.assert_called_once()

        self.window._project = None
        self.window._update_window_title()
        self.assertEqual(self.window.windowTitle(), "Setuav Studio")
        unnamed = self._project("")
        unnamed.modified = True
        self.window._project = unnamed
        self.window._update_window_title()
        self.assertIn("project*", self.window.windowTitle())

    def test_save_project_handles_empty_error_and_success_states(self) -> None:
        self.assertFalse(self.window.save_project())
        self.window._project = self._project()

        with (
            patch("setuav_studio.shell.save_project", side_effect=ProjectSaveError("disk full")),
            patch("setuav_studio.shell.QMessageBox.critical") as critical,
        ):
            self.assertFalse(self.window.save_project())
        critical.assert_called_once()

        with (
            patch("setuav_studio.shell.save_project") as save,
            patch.object(self.window, "_add_recent_project") as add_recent,
            patch.object(self.window._host, "mark_project_saved") as mark_saved,
        ):
            self.assertTrue(self.window.save_project())
        save.assert_called_once_with(self.window._project)
        mark_saved.assert_called_once()
        add_recent.assert_called_once()
        self.assertEqual(self.window._status_label.text(), "Project saved")

    def test_save_as_handles_empty_cancel_error_and_success_states(self) -> None:
        self.assertFalse(self.window.save_project_as())
        self.window._project = self._project()

        with patch("setuav_studio.shell.QFileDialog.getSaveFileName", return_value=("", "")):
            self.assertFalse(self.window.save_project_as())

        with (
            patch(
                "setuav_studio.shell.QFileDialog.getSaveFileName",
                return_value=("output.suav", ""),
            ),
            patch("setuav_studio.shell.save_project", side_effect=ProjectSaveError("failed")),
            patch("setuav_studio.shell.QMessageBox.critical") as critical,
        ):
            self.assertFalse(self.window.save_project_as())
        critical.assert_called_once()

        with (
            patch(
                "setuav_studio.shell.QFileDialog.getSaveFileName",
                return_value=("output.suav", ""),
            ),
            patch("setuav_studio.shell.save_project") as save,
            patch.object(self.window, "_add_recent_project"),
        ):
            self.assertTrue(self.window.save_project_as())
        save.assert_called_once_with(self.window._project, "output.suav")

    def test_collect_unsaved_changes_compares_components_assemblies_and_analyses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_file = Path(temporary_directory) / "project.json"
            disk_data = {
                "name": "Demo",
                "components": [
                    {"id": "modified", "name": "Old"},
                    {"id": "deleted", "name": "Deleted"},
                ],
                "assemblies": [{"id": "assembly", "name": "Old Assembly"}],
            }
            project_file.write_text(json.dumps(disk_data), encoding="utf-8")
            self.window._project = ProjectDocument(
                project_file,
                "json",
                {
                    "name": "Demo",
                    "components": [
                        "invalid",
                        {"id": "modified", "name": "Changed"},
                        {"id": "new", "name": "New"},
                    ],
                    "assemblies": [
                        "invalid",
                        {"id": "assembly", "name": "Changed Assembly"},
                        {"id": "new-assembly", "name": "New Assembly"},
                    ],
                },
            )
            with (
                patch(
                    "setuav_studio.plugins.aerodynamics.analysis_store.analysis_entries",
                    side_effect=lambda doc: (
                        [] if doc is not self.window._project else [{"id": "aero", "name": "Aero"}]
                    ),
                ),
                patch(
                    "setuav_studio.plugins.flight_performance.analysis_store.analysis_entries",
                    side_effect=lambda doc: (
                        []
                        if doc is not self.window._project
                        else [{"id": "perf", "name": "Performance"}]
                    ),
                ),
            ):
                changes = self.window._collect_unsaved_changes()

        self.assertEqual(
            changes,
            [
                "Modified Component: Changed",
                "New Component: New",
                "Deleted Component: Deleted",
                "Modified Assembly: Changed Assembly",
                "New Assembly: New Assembly",
                "Unsaved Aerodynamic Analysis: Aero",
                "Unsaved Flight Performance Analysis: Performance",
            ],
        )

    def test_collect_unsaved_changes_handles_no_project_and_read_failures(self) -> None:
        self.assertEqual(self.window._collect_unsaved_changes(), [])
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_file = Path(temporary_directory) / "project.json"
            project_file.write_text("{}", encoding="utf-8")
            self.window._project = ProjectDocument(project_file, "json", {"components": []})
            with (
                patch("setuav_studio.project.open_project", side_effect=RuntimeError("failed")),
                patch(
                    "setuav_studio.plugins.aerodynamics.analysis_store.analysis_entries",
                    side_effect=RuntimeError("aero failed"),
                ),
                patch(
                    "setuav_studio.plugins.flight_performance.analysis_store.analysis_entries",
                    side_effect=RuntimeError("performance failed"),
                ),
            ):
                self.assertEqual(self.window._collect_unsaved_changes(), [])
            self.window._project.data["components"] = None
            self.assertEqual(self.window._collect_unsaved_changes(), [])

    def test_confirm_close_supports_save_discard_cancel_and_long_summary(self) -> None:
        self.assertTrue(self.window._confirm_project_close())
        self.window._project = self._project()
        self.window._project.modified = True

        with (
            patch.object(self.window, "_collect_unsaved_changes", return_value=[]),
            patch(
                "setuav_studio.shell.QMessageBox.exec", return_value=QMessageBox.StandardButton.Save
            ),
            patch.object(self.window, "save_project", return_value=False) as save,
        ):
            self.assertFalse(self.window._confirm_project_close())
        save.assert_called_once()

        many_changes = [f"Change {index}" for index in range(10)]
        with (
            patch.object(self.window, "_collect_unsaved_changes", return_value=many_changes),
            patch(
                "setuav_studio.shell.QMessageBox.exec",
                return_value=QMessageBox.StandardButton.Discard,
            ),
        ):
            self.assertTrue(self.window._confirm_project_close())
        with (
            patch.object(self.window, "_collect_unsaved_changes", return_value=[]),
            patch(
                "setuav_studio.shell.QMessageBox.exec",
                return_value=QMessageBox.StandardButton.Cancel,
            ),
        ):
            self.assertFalse(self.window._confirm_project_close())

    def test_recent_projects_and_file_dialogs_cover_empty_and_selected_paths(self) -> None:
        with patch("setuav_studio.shell.QSettings", _FakeSettings):
            self.assertEqual(self.window._recent_projects(), [])
            _FakeSettings.values["recent_projects"] = "one.json"
            self.assertEqual(self.window._recent_projects(), ["one.json"])
            self.window._update_recent_menu()
            with patch.object(self.window, "open_project") as open_recent:
                self.window._recent_menu.actions()[0].trigger()
            open_recent.assert_called_once_with("one.json")

            self.window._add_recent_project(Path("two.json"))
            self.assertEqual(self.window._recent_projects()[0], "two.json")
            self.window._trim_recent_projects(1)
            self.assertEqual(self.window._recent_projects(), ["two.json"])
            self.window._clear_recent_projects()
            self.assertEqual(self.window._recent_projects(), [])
            self.assertFalse(self.window._recent_menu.actions()[0].isEnabled())

        with patch.object(self.window, "open_project") as open_selected:
            with patch(
                "setuav_studio.shell.QFileDialog.getOpenFileName",
                side_effect=[("", ""), ("project.json", "")],
            ):
                self.window._open_project_file()
                self.window._open_project_file()
            with patch(
                "setuav_studio.shell.QFileDialog.getExistingDirectory",
                side_effect=["", "project-folder"],
            ):
                self.window._open_project_folder()
                self.window._open_project_folder()
        self.assertEqual(
            [call.args[0] for call in open_selected.call_args_list],
            ["project.json", "project-folder"],
        )

    def test_open_last_project_uses_first_recent_entry(self) -> None:
        with (
            patch.object(self.window, "_recent_projects", side_effect=[[], ["first", "second"]]),
            patch.object(self.window, "open_project") as open_project,
        ):
            self.window.open_last_project()
            self.window.open_last_project()
        open_project.assert_called_once_with("first")

    @staticmethod
    def _project(name: str = "Demo") -> ProjectDocument:
        return ProjectDocument(
            Path("project.json"),
            "json",
            {"name": name, "components": [], "assemblies": []},
        )


if __name__ == "__main__":
    unittest.main()
