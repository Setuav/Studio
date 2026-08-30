"""Advanced Equation and Expression Editor Dialog with autocompletion and live preview."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugins.core.configurations import ConfigurationManager
from setuav_studio.plugins.core.constraints import ConstraintChecker
from setuav_studio.plugins.core.expressions import ExpressionEvaluator
from setuav_studio.plugins.core.parameters import ParameterResolver
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


MATH_FUNCTIONS: list[tuple[str, str, str]] = [
    ("sqrt(x)", "sqrt(", "Square root: sqrt(16) -> 4"),
    ("sin(x)", "sin(", "Sine of angle in radians"),
    ("cos(x)", "cos(", "Cosine of angle in radians"),
    ("tan(x)", "tan(", "Tangent of angle in radians"),
    ("deg2rad(x)", "deg2rad(", "Convert degrees to radians: deg2rad(180) -> pi"),
    ("rad2deg(x)", "rad2deg(", "Convert radians to degrees: rad2deg(pi) -> 180"),
    ("abs(x)", "abs(", "Absolute value: abs(-5) -> 5"),
    ("exp(x)", "exp(", "Exponential function e^x"),
    ("log(x)", "log(", "Natural logarithm (ln)"),
    ("log10(x)", "log10(", "Base-10 logarithm"),
    ("min(a, b)", "min(", "Minimum of values"),
    ("max(a, b)", "max(", "Maximum of values"),
    ("pow(x, y)", "pow(", "x raised to power y: pow(2, 3) -> 8"),
    ("pi", "pi", "Mathematical constant π ≈ 3.14159"),
    ("e", "e", "Mathematical constant e ≈ 2.71828"),
]


class AdvancedExpressionDialog(QDialog):
    """Rich equation editor dialog with parameter autocomplete, variable inserter, and live preview."""

    def __init__(
        self,
        api: StudioAPI,
        initial_expression: str = "",
        title: str = "Equation Editor",
        is_boolean_constraint: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 480)

        self._api = api
        self._is_constraint = is_boolean_constraint
        self._evaluator = ExpressionEvaluator()
        self._resolver = ParameterResolver(self._evaluator)
        self._checker = ConstraintChecker(self._evaluator, self._resolver)

        # Context gathering
        project_data = api.current_project.data if api.current_project else {}
        self._context = self._checker.extract_context(project_data)

        layout = QVBoxLayout(self)

        # Expression Input Area
        input_group = QGroupBox("Expression", self)
        input_layout = QVBoxLayout(input_group)

        self.expr_edit = QLineEdit(self)
        self.expr_edit.setText(initial_expression)
        placeholder = (
            "e.g. mtow / wing_area <= 50"
            if self._is_constraint
            else "e.g. =2 * span + root_chord / 2"
        )
        self.expr_edit.setPlaceholderText(placeholder)
        self.expr_edit.textChanged.connect(self._on_expression_changed)
        input_layout.addWidget(self.expr_edit)

        # Setup autocompleter
        self._setup_completer()

        # Quick Math Operator Bar
        op_bar = QHBoxLayout()
        for op in ("+", "-", "*", "/", "^", "(", ")", "<=", ">=", "==", "!="):
            btn = QPushButton(op, self)
            btn.setMaximumWidth(36)
            btn.clicked.connect(lambda _, text=op: self._insert_text(f" {text} "))
            op_bar.addWidget(btn)
        op_bar.addStretch()
        input_layout.addLayout(op_bar)

        layout.addWidget(input_group)

        # Middle Splitter: Variable & Function Picker Tabs
        picker_group = QGroupBox("Insert Variables & Functions", self)
        picker_layout = QVBoxLayout(picker_group)

        self.tabs = QTabWidget(self)

        # Tab 1: Project Parameters
        self.params_table = QTableWidget(0, 3, self)
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Current Value", "Unit"])
        self.params_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.params_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.params_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.params_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.params_table.doubleClicked.connect(self._insert_selected_parameter)
        self._populate_parameters_table(project_data)
        self.tabs.addTab(self.params_table, "Project Parameters")

        # Tab 2: Math Functions
        self.funcs_table = QTableWidget(0, 2, self)
        self.funcs_table.setHorizontalHeaderLabels(["Function / Constant", "Description"])
        self.funcs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.funcs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.funcs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.funcs_table.doubleClicked.connect(self._insert_selected_function)
        self._populate_functions_table()
        self.tabs.addTab(self.funcs_table, "Math Functions")

        picker_layout.addWidget(self.tabs)
        layout.addWidget(picker_group, 1)

        # Live Evaluation Result Box
        preview_group = QGroupBox("Live Evaluation Result", self)
        preview_layout = QVBoxLayout(preview_group)

        self.preview_label = QLabel(self)
        self.preview_label.setTextFormat(Qt.TextFormat.RichText)
        self.preview_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_label)

        self.breakdown_label = QLabel(self)
        self.breakdown_label.setTextFormat(Qt.TextFormat.RichText)
        self.breakdown_label.setWordWrap(True)
        preview_layout.addWidget(self.breakdown_label)

        layout.addWidget(preview_group)

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        # Initial evaluate
        self._on_expression_changed()

    def _setup_completer(self) -> None:
        completions: list[str] = []
        for name, insert_txt, _ in MATH_FUNCTIONS:
            completions.append(insert_txt.rstrip("("))
        for key in self._context:
            completions.append(key)

        model = QStringListModel(completions, self)
        completer = QCompleter(model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.expr_edit.setCompleter(completer)

    def _populate_parameters_table(self, project_data: dict[str, Any]) -> None:
        raw_params = project_data.get("parameters", {})
        self.params_table.setRowCount(0)
        for row, (k, v) in enumerate(raw_params.items()):
            self.params_table.insertRow(row)
            item_name = QTableWidgetItem(str(k))
            item_name.setFlags(item_name.flags() & ~Qt.ItemFlag.ItemIsEditable)

            resolved_val = self._context.get(k, v)
            val_str = f"{resolved_val:.4g}" if isinstance(resolved_val, (int, float)) else str(resolved_val)
            item_val = QTableWidgetItem(val_str)
            item_val.setFlags(item_val.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_unit = QTableWidgetItem("")
            item_unit.setFlags(item_unit.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.params_table.setItem(row, 0, item_name)
            self.params_table.setItem(row, 1, item_val)
            self.params_table.setItem(row, 2, item_unit)

    def _populate_functions_table(self) -> None:
        self.funcs_table.setRowCount(len(MATH_FUNCTIONS))
        for row, (sig, _, desc) in enumerate(MATH_FUNCTIONS):
            sig_item = QTableWidgetItem(sig)
            sig_item.setFlags(sig_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            desc_item = QTableWidgetItem(desc)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.funcs_table.setItem(row, 0, sig_item)
            self.funcs_table.setItem(row, 1, desc_item)

    def _insert_text(self, text: str) -> None:
        cursor_pos = self.expr_edit.cursorPosition()
        current_text = self.expr_edit.text()
        new_text = current_text[:cursor_pos] + text + current_text[cursor_pos:]
        self.expr_edit.setText(new_text)
        self.expr_edit.setCursorPosition(cursor_pos + len(text))
        self.expr_edit.setFocus()

    def _insert_selected_parameter(self) -> None:
        row = self.params_table.currentRow()
        if row >= 0:
            item = self.params_table.item(row, 0)
            if item:
                self._insert_text(item.text())

    def _insert_selected_function(self) -> None:
        row = self.funcs_table.currentRow()
        if 0 <= row < len(MATH_FUNCTIONS):
            _, insert_txt, _ = MATH_FUNCTIONS[row]
            self._insert_text(insert_txt)

    def _on_expression_changed(self) -> None:
        raw_expr = self.expr_edit.text().strip()
        if not raw_expr:
            self.preview_label.setText("<i>Enter an equation or formula to evaluate</i>")
            self.breakdown_label.setText("")
            return

        eval_expr = raw_expr.lstrip("=").strip()

        try:
            val = self._evaluator.evaluate(eval_expr, self._context)
            used_symbols = self._evaluator.extract_symbols(eval_expr)

            breakdowns: list[str] = []
            for sym in used_symbols:
                if sym in self._context:
                    sym_val = self._context[sym]
                    sym_str = f"{sym_val:.4g}" if isinstance(sym_val, (int, float)) else str(sym_val)
                    breakdowns.append(f"<b>{sym}</b> = {sym_str}")

            if breakdowns:
                self.breakdown_label.setText("<b>Variables:</b> " + ", ".join(breakdowns))
            else:
                self.breakdown_label.setText("")

            if self._is_constraint or isinstance(val, bool):
                if val:
                    self.preview_label.setText(
                        f"<span style='color: {status_color('success')}; font-weight: bold;'>✔ Condition Passed (True)</span>"
                    )
                else:
                    self.preview_label.setText(
                        f"<span style='color: {status_color('warning')}; font-weight: bold;'>⚠ Condition Violated (False)</span>"
                    )
            else:
                val_str = f"{val:.6g}" if isinstance(val, (int, float)) else str(val)
                self.preview_label.setText(
                    f"<b>Result:</b> <span style='color: {status_color('success')}; font-weight: bold;'>{val_str}</span>"
                )
        except Exception as exc:
            self.preview_label.setText(
                f"<span style='color: {status_color('error')}; font-weight: bold;'>❌ Syntax Error: {exc}</span>"
            )
            self.breakdown_label.setText("")

    def get_expression(self) -> str:
        """Return the cleaned expression string."""
        return self.expr_edit.text().strip()
