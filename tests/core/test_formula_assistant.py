"""Unit tests for Formula Assistant toolbar action, FocusAwareLineEdit autocomplete, and ExpressionFocusTracker."""

from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QWidget

from setuav_studio.api import ParameterField, StudioAPI, TableParameterField
from setuav_studio.project.document import ProjectDocument
from setuav_studio.ui.editor.component import TableExpressionDelegate
from setuav_studio.ui.editor.constraint import ConstraintExpressionCell
from setuav_studio.ui.shell.native_registrations import (
    _can_open_expression_assistant,
    _on_open_expression_assistant,
)
from setuav_studio.ui.widget.table import (
    ExpressionFocusTracker,
    ExpressionPropertyCell,
    FocusAwareLineEdit,
)


class TestFormulaAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.doc = ProjectDocument(
            path=Path("/tmp/test_formula_proj.json"),
            kind="json",
            data={
                "parameters": {
                    "SPAN": 2000.0,
                    "CHORD": 250.0,
                },
                "components": [
                    {
                        "id": "wing-1",
                        "type": "wing",
                        "name": "Main Wing",
                        "parameters": {
                            "area": 500000.0,
                        },
                    }
                ],
            },
        )
        self.api._host.set_project(self.doc)

    def tearDown(self) -> None:
        ExpressionFocusTracker.set_active_editor(None)

    def test_expression_focus_tracker(self) -> None:
        events: list[bool] = []

        def listener() -> None:
            events.append(ExpressionFocusTracker.has_active_editor())

        ExpressionFocusTracker.add_listener(listener)
        try:
            self.assertFalse(ExpressionFocusTracker.has_active_editor())

            mock_editor = object()
            ExpressionFocusTracker.set_active_editor(mock_editor)
            self.assertTrue(ExpressionFocusTracker.has_active_editor())
            self.assertIs(ExpressionFocusTracker.get_active_editor(), mock_editor)
            self.assertTrue(events[-1])

            ExpressionFocusTracker.set_active_editor(None)
            self.assertFalse(ExpressionFocusTracker.has_active_editor())
            self.assertFalse(events[-1])
        finally:
            ExpressionFocusTracker.remove_listener(listener)

    def test_focus_aware_line_edit_autocomplete_symbols(self) -> None:
        widget = QWidget()
        self.addCleanup(widget.deleteLater)

        edit = FocusAwareLineEdit(widget, api=self.api)
        symbols = edit._get_symbols()

        # Math functions and constants
        self.assertIn("pi", symbols)
        self.assertIn("sqrt(", symbols)
        self.assertIn("sin(", symbols)

        # Project parameters and component parameters
        self.assertIn("SPAN", symbols)
        self.assertIn("CHORD", symbols)
        self.assertIn("wing_1", symbols)
        self.assertIn("wing_1.area", symbols)

    def test_focus_aware_line_edit_autocomplete_trigger(self) -> None:
        widget = QWidget()
        self.addCleanup(widget.deleteLater)

        edit = FocusAwareLineEdit(widget, api=self.api)
        # Type '=' alone should NOT open completer popup
        edit.setText("=")
        self.assertTrue(edit._completer is None or not edit._completer.popup().isVisible())

        # Type '=120' (number) should NOT open popup
        edit.setText("=120")
        self.assertTrue(edit._completer is None or not edit._completer.popup().isVisible())

        # Type '=SP' should trigger completer with prefix 'SP' and suggest 'SPAN'
        edit.setText("=SP")
        self.assertIsNotNone(edit._completer)
        assert edit._completer is not None
        self.assertEqual(edit._completer.completionPrefix(), "SP")
        self.assertEqual(edit._completer.currentCompletion(), "SPAN")

        # Priority: project parameters come before functions in completion items
        items = edit._build_completion_items()
        keys = [k for k, _ in items]
        span_idx = keys.index("SPAN")
        sqrt_idx = keys.index("sqrt(")
        self.assertLess(span_idx, sqrt_idx)

    def test_focus_aware_line_edit_escape_closes_popup(self) -> None:
        widget = QWidget()
        self.addCleanup(widget.deleteLater)

        edit = FocusAwareLineEdit(widget, api=self.api)
        edit.setText("=SP")
        self.assertIsNotNone(edit._completer)
        assert edit._completer is not None
        popup = edit._completer.popup()
        popup.show()
        self.assertTrue(popup.isVisible())

        # Press Escape
        key_esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(edit, key_esc)
        self.assertFalse(popup.isVisible())
        self.assertEqual(edit.text(), "=SP")

    def test_focus_aware_line_edit_function_completion_cursor_at_end(self) -> None:
        widget = QWidget()
        self.addCleanup(widget.deleteLater)

        edit = FocusAwareLineEdit(widget, api=self.api)
        edit.setText("=sq")

        key_tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(edit, key_tab)

        self.assertEqual(edit.text(), "=sqrt(")
        # Cursor should remain at the very end of the text in the input
        self.assertEqual(edit.cursorPosition(), len(edit.text()))

    def test_focus_aware_line_edit_arrow_navigation_and_tab(self) -> None:
        widget = QWidget()
        self.addCleanup(widget.deleteLater)

        edit = FocusAwareLineEdit(widget, api=self.api)
        edit.setText("=SP")
        self.assertIsNotNone(edit._completer)
        assert edit._completer is not None
        popup = edit._completer.popup()
        self.assertIsNotNone(popup)
        assert popup is not None
        popup.show()

        # Press Down arrow to navigate through suggestions
        key_down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(edit, key_down)
        self.assertGreaterEqual(popup.currentIndex().row(), 0)

        # Press Tab to accept selected item
        key_tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(edit, key_tab)

        self.assertEqual(edit.text(), "=SPAN")
        self.assertEqual(edit.cursorPosition(), len(edit.text()))

    def test_expression_property_cell_focus_tracking(self) -> None:
        cell = ExpressionPropertyCell(
            initial_value="100.0",
            label="Span",
            api=self.api,
        )
        self.addCleanup(cell.deleteLater)

        self.assertFalse(ExpressionFocusTracker.has_active_editor())
        cell._on_focus_in()
        self.assertTrue(ExpressionFocusTracker.has_active_editor())
        self.assertIs(ExpressionFocusTracker.get_active_editor(), cell)

        cell._on_focus_out()
        cell._maybe_clear_focus_tracker()
        self.assertFalse(ExpressionFocusTracker.has_active_editor())

    def test_constraint_expression_cell_focus_tracking(self) -> None:
        cell = ConstraintExpressionCell(
            initial_value="SPAN > 1000",
            api=self.api,
        )
        self.addCleanup(cell.deleteLater)

        self.assertFalse(ExpressionFocusTracker.has_active_editor())
        cell._on_focus_in()
        self.assertTrue(ExpressionFocusTracker.has_active_editor())
        self.assertIs(ExpressionFocusTracker.get_active_editor(), cell)

        cell._on_focus_out()
        cell._maybe_clear_focus_tracker()
        self.assertFalse(ExpressionFocusTracker.has_active_editor())

    def test_toolbar_action_predicate(self) -> None:
        # With project loaded but no active editor -> False
        self.assertFalse(_can_open_expression_assistant(self.api))

        # With active editor -> True
        mock_editor = object()
        ExpressionFocusTracker.set_active_editor(mock_editor)
        self.assertTrue(_can_open_expression_assistant(self.api))

        # No project loaded -> False
        self.api.current_project = None
        self.assertFalse(_can_open_expression_assistant(self.api))

    def test_toolbar_action_trigger_delegates_to_active_editor(self) -> None:
        called = False

        class MockAdapter:
            def open_assistant(self) -> None:
                nonlocal called
                called = True

        ExpressionFocusTracker.set_active_editor(MockAdapter())
        _on_open_expression_assistant(self.api)
        self.assertTrue(called)

    def test_focus_aware_line_edit_tab_completion(self) -> None:
        widget = QWidget()
        self.addCleanup(widget.deleteLater)

        edit = FocusAwareLineEdit(widget, api=self.api)
        edit.setText("=SP")

        # Send Tab key event
        key_tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(edit, key_tab)

        self.assertEqual(edit.text(), "=SPAN")
        self.assertFalse(edit._completer.popup().isVisible())

    def test_focus_aware_line_edit_enter_commits_and_exits(self) -> None:
        cell = ExpressionPropertyCell(
            initial_value="100.0",
            label="Span",
            api=self.api,
        )
        self.addCleanup(cell.deleteLater)

        cell.line_edit.setText("=SPAN * 2")

        # Press Enter: should commit current text, close popup, and clear focus / exit editing
        key_enter = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        )
        QApplication.sendEvent(cell.line_edit, key_enter)

        # ExpressionPropertyCell evaluated value for SPAN (2000.0) * 2 = 4000.0
        self.assertEqual(cell.text(), "=SPAN * 2")
        self.assertEqual(cell.value(), 4000.0)
        self.assertFalse(cell.line_edit.hasFocus())

    def test_expression_property_cell_tab_completion_does_not_revert(self) -> None:
        cell = ExpressionPropertyCell(
            initial_value="=2 * SPAN",
            label="Span",
            api=self.api,
        )
        self.addCleanup(cell.deleteLater)
        cell.show()

        # Enter edit mode (focus in)
        cell._on_focus_in()
        self.assertEqual(cell.line_edit.text(), "=2 * SPAN")

        # User deletes and types '=SP'
        cell.line_edit.setText("=SP")
        self.assertIsNotNone(cell.line_edit._completer)
        assert cell.line_edit._completer is not None
        popup = cell.line_edit._completer.popup()
        self.assertIsNotNone(popup)
        assert popup is not None
        popup.show()

        # Press Down arrow to select SPAN
        key_down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(cell.line_edit, key_down)

        # Press Tab to accept completion
        key_tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(cell.line_edit, key_tab)

        # Crucial check: input text must be '=SPAN', NOT reverted to '=2 * SPAN'
        self.assertEqual(cell.line_edit.text(), "=SPAN")
        self.assertEqual(cell.line_edit.cursorPosition(), len("=SPAN"))

        # Press Enter to commit and exit
        key_enter = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        )
        QApplication.sendEvent(cell.line_edit, key_enter)

        self.assertEqual(cell.text(), "=SPAN")
        self.assertEqual(cell.value(), 2000.0)

    def test_table_expression_delegate_enter_commits_and_closes_editor(self) -> None:
        table = QTableWidget(3, 2)
        self.addCleanup(table.deleteLater)

        item = QTableWidgetItem("100.0")
        table.setItem(1, 1, item)
        table.show()

        tf = TableParameterField(
            key="sec",
            label="Sec",
            columns=(ParameterField(key="val", label="Val", field_type=float, default=0.0),),
        )
        delegate = TableExpressionDelegate(self.api, tf, parent=table)
        table.setItemDelegate(delegate)
        table.editItem(item)

        edit = table.findChild(FocusAwareLineEdit)
        self.assertIsNotNone(edit)
        assert edit is not None

        edit.setText("=SPAN / 2")
        key_enter = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        )
        QApplication.sendEvent(edit, key_enter)

        self.assertEqual(item.text(), "=SPAN / 2")
        # Editor should be closed / not visible and table not editing
        self.assertFalse(edit.isVisible())
        self.assertEqual(table.state(), QTableWidget.State.NoState)


if __name__ == "__main__":
    unittest.main()
