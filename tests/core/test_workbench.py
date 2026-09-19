"""Unit tests for Workbench and Tool Contribution systems."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QLabel

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
        api.add_panel(
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

    def test_status_bar_shows_colored_messages_and_auto_clears(self) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QPalette

        from setuav_studio.ui.style.theme import status_color

        api = StudioAPI()
        win = MainWindow(api)
        get_qapp().processEvents()

        api.show_status("analysis complete", "success", 0)
        self.assertEqual(win._status_label.text(), "analysis complete")
        self.assertEqual(
            win._status_label.palette().color(QPalette.ColorRole.WindowText).name(),
            status_color("success"),
        )

        api.show_status("invalid input", "error", 0)
        self.assertEqual(win._status_label.text(), "invalid input")
        self.assertEqual(
            win._status_label.palette().color(QPalette.ColorRole.WindowText).name(),
            status_color("error"),
        )

        api.clear_status()
        self.assertEqual(win._status_label.text(), "")

        api.show_status("will clear", "warning", 20)
        QTimer.singleShot(60, get_qapp().quit)
        get_qapp().exec()
        self.assertEqual(win._status_label.text(), "")

    def test_progress_bar_shows_and_hides(self) -> None:
        from PySide6.QtWidgets import QProgressBar

        api = StudioAPI()
        win = MainWindow(api)
        get_qapp().processEvents()

        bar = win._progress_bar
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

        # Find Propulsion submenu
        prop_action = next(a for a in tools_menu.actions() if "propulsion" in a.text().lower())
        self.assertIsNotNone(prop_action)
        prop_menu = prop_action.menu()

        # Find and trigger the Sample Tool action
        sample_action = next(a for a in prop_menu.actions() if "sample tool" in a.text().lower())
        sample_action.trigger()
        self.assertEqual(called, [True])

    def test_log_button_opens_log_window(self) -> None:
        import logging

        from setuav_studio.ui.dialog.log import clear_log_buffer, install_log_buffer

        clear_log_buffer()
        install_log_buffer()
        logging.getLogger("setuav_studio.test").warning("hello log window")

        api = StudioAPI()
        win = MainWindow(api)
        get_qapp().processEvents()

        self.assertIsNotNone(win._log_button)
        win._log_button.click()
        self.assertIsNotNone(win._log_window)
        self.assertTrue(win._log_window.isVisible())
        self.assertEqual(win._log_window._table.columnCount(), 3)
        table_text = " ".join(
            item.text()
            for row in range(win._log_window._table.rowCount())
            for item in [win._log_window._table.item(row, c) for c in range(3)]
            if item is not None
        )
        self.assertIn("hello log window", table_text)
        self.assertTrue(win._log_window._table.wordWrap())

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


if __name__ == "__main__":
    unittest.main()
