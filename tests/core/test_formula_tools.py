"""Tests for the Formula Assistant's inserts and the default new constraint."""

from __future__ import annotations

import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QTreeWidgetItemIterator

from setuav_studio.api import StudioAPI
from setuav_studio.model.constraint import ConstraintChecker
from setuav_studio.model.expression import STANDARD_SYMBOLS, ExpressionEvaluator
from setuav_studio.project import open_project
from setuav_studio.ui.dialog.expression_dialog import MATH_FUNCTIONS, AdvancedExpressionDialog
from setuav_studio.ui.panels.project_explorer.dialog_actions import add_constraint_action
from tests._common import TEST_PROJECT_PATH, get_qapp, register_fixture_component_types


class FormulaToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        register_fixture_component_types(self.api)
        self.project = open_project(TEST_PROJECT_PATH)
        self.api._host.set_project(self.project)

    def test_listed_math_functions_exist_in_the_formula_engine(self) -> None:
        for label, _insert, _description in MATH_FUNCTIONS:
            name = label.split("(")[0]
            with self.subTest(name=name):
                self.assertIn(name, STANDARD_SYMBOLS)

    def test_operator_bar_inserts_a_power_that_evaluates(self) -> None:
        dialog = AdvancedExpressionDialog(self.api)
        self.addCleanup(dialog.deleteLater)
        operators = {button.text() for button in dialog.findChildren(QPushButton)}

        self.assertNotIn("^", operators)
        self.assertIn("**", operators)
        self.assertEqual(ExpressionEvaluator().evaluate("2 ** 3"), 8)

    def test_new_constraint_checks_without_error(self) -> None:
        add_constraint_action(self.api)

        constraint = self.project.data["constraints"][-1]
        result = ConstraintChecker().check_constraint(constraint, self.project.data)
        self.assertIsNone(result.error)
        self.assertTrue(result.passed)

    def _add_feature(self) -> None:
        wing = self.project.get_component("main-wing")
        assert wing is not None
        wing["extensions"] = {
            "com.example.manufacturing": {
                "features": [
                    {"id": "main-wing-shell", "type": "shell", "parameters": {"thickness": 1.2}}
                ]
            }
        }

    def test_component_features_are_in_formulas_and_the_assistant(self) -> None:
        self._add_feature()
        scope = self.project.get_scope(api=self.api)
        self.assertEqual(ExpressionEvaluator().evaluate("main_wing_shell.thickness", scope), 1.2)

        dialog = AdvancedExpressionDialog(self.api)
        self.addCleanup(dialog.deleteLater)
        tags = []
        iterator = QTreeWidgetItemIterator(dialog.comp_tree)
        while iterator.value():
            tag = iterator.value().data(0, Qt.ItemDataRole.UserRole)
            if tag:
                tags.append(tag)
            iterator += 1
        self.assertIn("main_wing_shell.thickness", tags)
        # Every tag the assistant inserts evaluates.
        for tag in tags:
            with self.subTest(tag=tag):
                ExpressionEvaluator().evaluate(tag, scope)

    def test_name_columns_fit_their_names(self) -> None:
        dialog = AdvancedExpressionDialog(self.api)
        self.addCleanup(dialog.deleteLater)
        self.assertGreaterEqual(dialog.comp_tree.header().sectionSize(0), 220)
        self.assertGreaterEqual(dialog.params_table.horizontalHeader().sectionSize(0), 220)

    def test_inline_completion_shows_type_names(self) -> None:
        from setuav_studio.ui.widget.table import ExpressionPropertyCell

        cell = ExpressionPropertyCell(api=self.api)
        self.addCleanup(cell.deleteLater)
        labels = [label for _insert, label in cell.line_edit._build_completion_items()]
        self.assertTrue(any(label.endswith("[Lifting Surface]") for label in labels))
        self.assertFalse(any("org.setuav" in label for label in labels))


if __name__ == "__main__":
    unittest.main()
