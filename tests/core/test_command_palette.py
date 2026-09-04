"""Unit tests for Command Palette dialog."""

from __future__ import annotations

import unittest

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence

from setuav_studio.api.api import StudioAPI
from setuav_studio.ui.shell.command_palette import CommandItem, CommandPaletteDialog
from setuav_studio.ui.shell.window import MainWindow
from tests._common import get_qapp


class TestCommandPalette(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.window = MainWindow(self.api)
        self.am = self.window._action_manager

    def tearDown(self) -> None:
        self.window.close()
        QCoreApplication.processEvents()

    def test_command_palette_action_registered(self) -> None:
        self.assertIn("core.command_palette.open", self.am.command_actions)
        act = self.am.command_actions["core.command_palette.open"]
        self.assertEqual(act.shortcut(), QKeySequence("Ctrl+Shift+P"))

    def test_command_palette_dialog_collects_commands(self) -> None:
        dlg = CommandPaletteDialog(self.window, self.api)
        commands = dlg._collect_commands(self.am)
        self.assertGreater(len(commands), 0)

        # Should include core commands
        titles = [c.title for c in commands]
        self.assertTrue(any("Open" in t or "New" in t for t in titles))
        self.assertTrue(any("Background Tasks" in t for t in titles))
        self.assertTrue(any("Design Constraints" in t for t in titles))
        self.assertTrue(any("Settings" in t for t in titles))

    def test_command_palette_filter(self) -> None:
        dlg = CommandPaletteDialog(self.window, self.api)
        dlg.populate_and_show(self.am)
        QCoreApplication.processEvents()

        # Filter for 'tasks'
        dlg.search_edit.setText("tasks")
        QCoreApplication.processEvents()
        self.assertGreater(len(dlg._filtered_commands), 0)
        top = dlg._filtered_commands[0]
        self.assertIn("Tasks", top.title)

        # Filter for non-existent text
        dlg.search_edit.setText("xyznonexistent123")
        QCoreApplication.processEvents()
        self.assertEqual(len(dlg._filtered_commands), 0)

        dlg.close()

    def test_command_palette_execution(self) -> None:
        executed = []
        custom_cmd = CommandItem(
            id="test.custom",
            title="Custom Test Command",
            category="Test",
            callback=lambda: executed.append(True),
        )
        dlg = CommandPaletteDialog(self.window, self.api)
        dlg._commands = [custom_cmd]
        dlg._filter_commands("")
        QCoreApplication.processEvents()

        # Execute
        dlg._execute_command(custom_cmd)
        self.assertEqual(executed, [True])

    def test_command_palette_keyboard_navigation(self) -> None:
        executed = []
        cmd1 = CommandItem(id="1", title="Cmd 1", category="Test", callback=lambda: executed.append(1))
        cmd2 = CommandItem(id="2", title="Cmd 2", category="Test", callback=lambda: executed.append(2))

        dlg = CommandPaletteDialog(self.window, self.api)
        dlg._commands = [cmd1, cmd2]
        dlg._filter_commands("")
        QCoreApplication.processEvents()

        self.assertEqual(dlg.list_widget.currentRow(), 0)

        # Press Down arrow
        down_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        dlg.eventFilter(dlg, down_event)
        self.assertEqual(dlg.list_widget.currentRow(), 1)

        # Press Enter key
        enter_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        dlg.eventFilter(dlg, enter_event)
        self.assertEqual(executed, [2])


if __name__ == "__main__":
    unittest.main()
