"""Unit tests for Status Bar Problems badge, ProblemsDialog, and evaluation logic."""

from __future__ import annotations

import unittest

from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.dialog.problems import Problem, ProblemsDialog
from setuav_studio.ui.shell.status_bar import StatusBarManager
from setuav_studio.ui.shell.window import MainWindow
from tests._common import TEST_PROJECT_PATH, get_qapp


class TestStatusBarProblems(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_problem_dataclass(self) -> None:
        p = Problem(
            id="c1",
            title="Span limit",
            message="Span exceeds max",
            severity="error",
            source="Constraint",
        )
        self.assertEqual(p.id, "c1")
        self.assertEqual(p.title, "Span limit")
        self.assertEqual(p.severity, "error")

    def test_problems_dialog_rendering(self) -> None:
        problems = [
            Problem(
                id="c1",
                title="Span limit",
                message="Span must be <= 3.0",
                severity="error",
                source="Constraint",
            ),
            Problem(
                id="p1",
                title="Missing plugin",
                message="Aero plugin missing",
                severity="warning",
                source="Plugin",
            ),
        ]
        dialog = ProblemsDialog(problems)
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.problem_table.rowCount(), 2)
        dialog.close()
        dialog.deleteLater()

    def test_status_bar_manager_evaluate_problems(self) -> None:
        api = StudioAPI()
        window = MainWindow(api)
        sm = StatusBarManager(window, api)

        doc = ProjectDocument(
            path=TEST_PROJECT_PATH,
            kind="json",
            data={
                "id": "proj1",
                "parameters": {"span": 12.0},
                "constraints": [
                    {
                        "id": "c1",
                        "name": "Span limit",
                        "expression": "span <= 10.0",
                        "severity": "error",
                        "enabled": True,
                    }
                ],
            },
        )
        doc.plugin_issues = ["Required plugin 'org.setuav.aero' missing"]

        problems = sm.evaluate_problems(doc)
        self.assertEqual(len(problems), 2)
        self.assertEqual(problems[0].source, "Constraint")
        self.assertEqual(problems[0].severity, "error")
        self.assertEqual(problems[1].source, "Plugin")
        self.assertEqual(problems[1].severity, "warning")

        self.assertEqual(sm.error_count_label.text(), "1")
        self.assertEqual(sm.warning_count_label.text(), "1")

        # Test command palette button on status bar and Tools menu
        self.assertIsNotNone(sm.command_palette_button)
        self.assertIsNotNone(sm.tasks_button)
        self.assertIsNotNone(sm.log_button)

        # Tools menu check
        tools_actions = [
            a.text().replace("&", "").strip() for a in window._action_manager.tools_menu.actions()
        ]
        self.assertTrue(any("Command Palette" in a for a in tools_actions))
        self.assertFalse(any("Design Constraints" in a for a in tools_actions))

        window.close()
        window.deleteLater()

    def test_elided_status_label(self) -> None:
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QSizePolicy

        from setuav_studio.ui.shell.status_bar import ElidedStatusLabel

        label = ElidedStatusLabel()
        self.assertEqual(label.text(), "")
        self.assertEqual(label.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Ignored)
        self.assertEqual(label.minimumSizeHint().width(), 0)

        # Short text
        label.setText("Ready")
        self.assertEqual(label.text(), "Ready")
        self.assertEqual(label.toolTip(), "")

        # Long text
        long_msg = "Plugin load issues: plugins.aerodynamics: failed to import backend module because dependency is missing"
        label.setText(long_msg)
        self.assertEqual(label.text(), long_msg)
        self.assertEqual(label.toolTip(), long_msg)

        # With constrained width, displayed_text should be elided
        label.resize(QSize(100, 24))
        label._update_elided()
        self.assertTrue(len(label.displayed_text()) < len(long_msg))
        self.assertTrue(
            label.displayed_text().endswith("…") or label.displayed_text().endswith("...")
        )

        label.clear()
        self.assertEqual(label.text(), "")
        self.assertEqual(label.toolTip(), "")
        label.deleteLater()

    def test_studio_status_bar_delegates_show_message(self) -> None:
        api = StudioAPI()
        window = MainWindow(api)
        window.statusBar().showMessage("Plugin load issues: failed to load test plugin")
        self.assertIn("Plugin load issues: failed to load test plugin", window._status_label.text())
        self.assertEqual(window._status_manager._status_level, "error")

        window.statusBar().showMessage("Operation completed successfully")
        self.assertEqual(window._status_label.text(), "Operation completed successfully")
        self.assertEqual(window._status_manager._status_level, "info")

        window.statusBar().clearMessage()
        self.assertEqual(window._status_label.text(), "")
        window.close()
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
