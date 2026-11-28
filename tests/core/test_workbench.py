"""Unit tests for Workbench and Tool Contribution systems."""

from __future__ import annotations

import itertools
import unittest

from PySide6.QtWidgets import QLabel, QMenu

from setuav_studio.api import (
    PanelContribution,
    StudioAPI,
    ToolContribution,
)
from setuav_studio.ui.shell import MainWindow
from tests._common import get_qapp


class TestWorkbenchAndTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_workbench_dock_registration(self) -> None:
        api = StudioAPI()
        win = MainWindow(api)

        # Register custom panel
        api.register_panel(
            PanelContribution(
                id="custom.panel",
                title="Custom Panel",
                factory=lambda: QLabel("Custom Dock Widget"),
            )
        )

        # Panel is registered and dock is present
        self.assertIn("custom.panel", win._panels)
        custom_dock = win._panels["custom.panel"][1]
        self.assertFalse(custom_dock.isHidden())

    def test_add_point_mass_places_a_selected_mass_at_the_origin(self) -> None:
        from pathlib import Path

        from setuav_studio.project import ProjectDocument
        from setuav_studio.ui.editor.component import BaseComponentEditor
        from setuav_studio.ui.shell.native_registrations import (
            POINT_MASS_TYPE,
            _on_add_point_mass_triggered,
            register_native_component_types,
        )

        api = StudioAPI()
        register_native_component_types(api)
        project = ProjectDocument(Path("point-mass.json"), "json", {"components": []})
        api._host.set_project(project)

        _on_add_point_mass_triggered(api)
        _on_add_point_mass_triggered(api)

        components = project.data["components"]
        self.assertEqual(
            [(c["id"], c["name"]) for c in components],
            [("point-mass", "Point Mass"), ("point-mass-2", "Point Mass 2")],
        )
        self.assertEqual(components[0]["type"], POINT_MASS_TYPE)
        self.assertEqual(components[0]["transform"]["position"], {"x": 0.0, "y": 0.0, "z": 0.0})
        self.assertGreater(components[0]["mass"], 0.0)
        self.assertIs(api.current_selection, components[1])
        editor = api.create_component_editor(components[1])
        self.assertIsInstance(editor, BaseComponentEditor)
        assert editor is not None
        editor.deleteLater()
        api.undo()
        self.assertEqual(len(project.data["components"]), 1)
        api.redo()
        self.assertEqual(len(project.data["components"]), 2)

    def test_default_layout_fills_the_window_without_gaps(self) -> None:
        win = MainWindow(StudioAPI())
        self.addCleanup(win.close)
        win.layout_manager.apply_default_layout()
        docks = [
            win.layout_manager.dock(panel_id)
            for panel_id in ("studio:project-explorer", "studio:viewer-3d", "studio:properties")
        ]
        win.resize(1400, 900)
        win.show()
        for width in (1400, 1900):
            win.resize(width, 900)
            for _ in range(30):
                get_qapp().processEvents()
            spans = [(d.geometry().left(), d.geometry().right()) for d in docks if d is not None]
            self.assertEqual(len(spans), 3)
            self.assertEqual(spans[0][0], 0)
            # Neighbouring docks are separated only by the splitter handle.
            for (_, right), (left, _) in itertools.pairwise(spans):
                self.assertLessEqual(left - right, 8)
            self.assertGreaterEqual(spans[-1][1], win.width() - 1)

    def test_fullscreen_roundtrip_preserves_restored_dock_layout(self) -> None:
        from PySide6.QtCore import Qt

        win = MainWindow(StudioAPI())
        self.addCleanup(win.close)
        win.resize(1280, 720)
        # Mirror __main__.py: show() runs before restore_dock_layout().
        win.show()
        get_qapp().processEvents()
        win.layout_manager.reset_layout()
        for _ in range(10):
            get_qapp().processEvents()

        tree = win.layout_manager.dock("studio:project-explorer")
        view = win.layout_manager.dock("studio:viewer-3d")
        prop = win.layout_manager.dock("studio:properties")
        assert tree is not None and view is not None and prop is not None
        before_tops = (tree.geometry().top(), view.geometry().top(), prop.geometry().top())

        # Enter fullscreen and return to normal state without resizing first.
        win.setWindowState(Qt.WindowState.WindowFullScreen)
        get_qapp().processEvents()
        win.setWindowState(Qt.WindowState.WindowNoState)
        for _ in range(15):
            get_qapp().processEvents()

        after_tops = (tree.geometry().top(), view.geometry().top(), prop.geometry().top())
        self.assertEqual(after_tops, before_tops)
        # All three columns remain side by side rather than stacked vertically.
        self.assertLess(tree.geometry().left(), view.geometry().left())
        self.assertLess(view.geometry().left(), prop.geometry().left())

    def test_status_bar_shows_colored_messages_and_auto_clears(self) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QPalette

        from setuav_studio.ui.style.theme import status_color

        api = StudioAPI()
        win = MainWindow(api)
        get_qapp().processEvents()

        api.show_status("analysis complete", "success", 0)
        self.assertEqual(win.status_manager.status_label.text(), "analysis complete")
        self.assertEqual(
            win.status_manager.status_label.palette().color(QPalette.ColorRole.WindowText).name(),
            status_color("success"),
        )

        api.show_status("invalid input", "error", 0)
        self.assertEqual(win.status_manager.status_label.text(), "invalid input")
        self.assertEqual(
            win.status_manager.status_label.palette().color(QPalette.ColorRole.WindowText).name(),
            status_color("error"),
        )

        api.clear_status()
        self.assertEqual(win.status_manager.status_label.text(), "")

        api.show_status("will clear", "warning", 20)
        QTimer.singleShot(60, get_qapp().quit)
        get_qapp().exec()
        self.assertEqual(win.status_manager.status_label.text(), "")

    def test_progress_bar_shows_and_hides(self) -> None:
        from PySide6.QtWidgets import QProgressBar

        api = StudioAPI()
        win = MainWindow(api)
        get_qapp().processEvents()

        bar = win.status_manager.progress_bar
        self.assertIsInstance(bar, QProgressBar)
        self.assertTrue(bar.isHidden())

        api.report_progress(2, 10, "Analyzing")
        self.assertFalse(bar.isHidden())
        self.assertEqual(bar.maximum(), 10)
        self.assertEqual(bar.value(), 2)
        self.assertIn("Analyzing", bar.text())

        api.report_progress(10, 10, "Analyzing")
        self.assertTrue(bar.isHidden())

    def test_tool_registration_in_tools_menu(self) -> None:
        api = StudioAPI()
        win = MainWindow(api)

        called = []

        # Register tool under "Propulsion" group
        api.register_tool(
            ToolContribution(
                title="Sample Tool",
                group="Propulsion",
                callback=lambda: called.append(True),
            )
        )

        # Find Tools menu in menuBar
        tools_action = next(a for a in win.menuBar().actions() if "tools" in a.text().lower())
        self.assertIsNotNone(tools_action)
        tools_menu = tools_action.menu()
        self.assertIsNotNone(tools_menu)
        assert isinstance(tools_menu, QMenu)

        # Find Propulsion submenu
        prop_action = next(a for a in tools_menu.actions() if "propulsion" in a.text().lower())
        self.assertIsNotNone(prop_action)
        prop_menu = prop_action.menu()
        self.assertIsNotNone(prop_menu)
        assert isinstance(prop_menu, QMenu)

        # Find and trigger the Sample Tool action
        sample_action = next(a for a in prop_menu.actions() if "sample tool" in a.text().lower())
        sample_action.trigger()
        self.assertEqual(called, [True])

    def test_studio_api_event_bus_publish_subscribe(self) -> None:
        api = StudioAPI()
        received_payloads: list[dict[str, int]] = []

        def handler(payload: dict[str, int]) -> None:
            received_payloads.append(payload)

        # 1. Subscribe
        api.subscribe("custom.test_event", handler)

        # 2. Publish event
        api.publish("custom.test_event", {"value": 42})
        self.assertEqual(len(received_payloads), 1)
        self.assertEqual(received_payloads[0]["value"], 42)

        # 3. Unsubscribe
        api.unsubscribe("custom.test_event", handler)
        api.publish("custom.test_event", {"value": 99})
        # Count should remain 1
        self.assertEqual(len(received_payloads), 1)

    def test_untitled_project_ignores_same_named_file_on_disk_for_unsaved_changes(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from setuav_studio.project import create_project

        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                api = StudioAPI()
                win = MainWindow(api)
                self.addCleanup(win.close)
                win.project_controller.new_untitled_project()
                assert win.project_controller.project is not None
                assert win.project_controller.project.untitled

                # Create an unrelated saved file at the same path as the untitled placeholder name
                unrelated = create_project(
                    Path(win.project_controller.project.location),
                )
                unrelated.data["components"].append(
                    {"id": "disk-only", "name": "Disk Only", "type": "org.setuav.core:point-mass"}
                )
                from setuav_studio.project import save_project

                save_project(unrelated)

                changes = win.project_controller.collect_unsaved_changes()
                self.assertEqual(changes, [])
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
