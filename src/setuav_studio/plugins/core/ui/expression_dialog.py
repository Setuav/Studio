"""Advanced Equation and Expression Editor Dialog with component dot-notation autocompletion and live preview."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QKeyEvent
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
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugins.core.constraints import ConstraintChecker
from setuav_studio.plugins.core.expressions import ExpressionEvaluator
from setuav_studio.plugins.core.parameters import ParameterResolver
from setuav_studio.plugins.core.symbols import (
    get_available_symbols_metadata,
)
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


MATH_FUNCTIONS: list[tuple[str, str, str]] = [
    ("sqrt(x)", "sqrt(", "Square root: sqrt(16) -> 4"),
    ("sin(x)", "sin(", "Sine of angle in radians"),
    ("cos(x)", "cos(", "Cosine of angle in radians"),
    ("tan(x)", "tan(", "Tangent of angle in radians"),
    ("asin(x)", "asin(", "Arc sine in radians"),
    ("acos(x)", "acos(", "Arc cosine in radians"),
    ("atan(x)", "atan(", "Arc tangent in radians"),
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
    ("g", "9.80665", "Standard gravity constant (9.81 m/s²)"),
]


class ExpressionLineEdit(QLineEdit):
    """IDE-like expression input with intelligent dot-triggering and token-aware autocompletion."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._completer: QCompleter | None = None
        self._component_props: dict[str, list[str]] = {}
        self._all_symbols: list[str] = []

    def set_symbol_data(
        self,
        constants: list[str],
        components: list[dict[str, Any]],
        math_funcs: list[str],
    ) -> None:
        self._all_symbols = list(constants) + list(math_funcs)
        self._component_props = {}

        for comp in components:
            raw_cid = comp["id"]
            clean_cid = raw_cid.replace("-", "_")
            props = [p["key"] for p in comp.get("properties", [])]

            self._component_props[raw_cid] = props
            self._component_props[clean_cid] = props

            self._all_symbols.append(clean_cid)
            if raw_cid != clean_cid:
                self._all_symbols.append(raw_cid)

            for p in props:
                self._all_symbols.append(f"{clean_cid}.{p}")

        self._all_symbols = sorted(set(self._all_symbols))
        self._update_completer_model(self._all_symbols)

    def _update_completer_model(self, items: list[str]) -> None:
        model = QStringListModel(items, self)
        if self._completer is None:
            self._completer = QCompleter(model, self)
            self._completer.setWidget(self)
            self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self._completer.activated.connect(self._insert_completion)
        else:
            self._completer.setModel(model)

    def _get_current_token(self) -> tuple[str, int, int]:
        """Return (token_text, start_pos, end_pos) for token under cursor."""
        text = self.text()
        cursor_pos = self.cursorPosition()
        left_text = text[:cursor_pos]
        match = re.search(r"([A-Za-z_0-9\-\.]+)$", left_text)
        if not match:
            return "", cursor_pos, cursor_pos
        token = match.group(1)
        start_pos = cursor_pos - len(token)
        return token, start_pos, cursor_pos

    def _insert_completion(self, completion: str) -> None:
        token, start_pos, end_pos = self._get_current_token()
        text = self.text()

        # If user was typing e.g. main_wing.section_0.chord or main-wing.something
        if "." in token:
            parts = token.split(".")
            clean_parts = [p.replace("-", "_") for p in parts[:-1]]
            prefix = ".".join(clean_parts)
            if not completion.startswith(f"{prefix}."):
                completion = f"{prefix}.{completion}"
        elif completion.replace("-", "_") in self._component_props:
            completion = completion.replace("-", "_")

        new_text = text[:start_pos] + completion + text[end_pos:]
        self.setText(new_text)
        self.setCursorPosition(start_pos + len(completion))

    def _update_token_completions(self, token: str) -> None:
        if not self._completer:
            return
        if "." not in token:
            self._update_completer_model(self._all_symbols)
            self._completer.setCompletionPrefix(token)
            return

        parts = token.split(".")
        if len(parts) == 2:
            comp_part, prop_prefix = parts[0], parts[1]
            comp_clean = comp_part.replace("-", "_")
            props = self._component_props.get(comp_part) or self._component_props.get(comp_clean)
            if props:
                clean_props = []
                seen = set()
                for p in props:
                    if p.startswith("section_"):
                        sec_name = "_".join(p.split("_")[:2])
                        if sec_name not in seen:
                            clean_props.append(sec_name)
                            seen.add(sec_name)
                    else:
                        clean_props.append(p)
                self._update_completer_model(clean_props)
                self._completer.setCompletionPrefix(prop_prefix)
                return
        elif len(parts) == 3:
            comp_part, sec_part, prop_prefix = parts[0], parts[1], parts[2]
            comp_clean = comp_part.replace("-", "_")
            props = self._component_props.get(comp_part) or self._component_props.get(comp_clean)
            if props:
                prefix_match = f"{sec_part}_"
                sec_subprops = [p[len(prefix_match):] for p in props if p.startswith(prefix_match)]
                self._update_completer_model(sec_subprops)
                self._completer.setCompletionPrefix(prop_prefix)
                return

        self._update_completer_model(self._all_symbols)
        self._completer.setCompletionPrefix(token)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            self._completer
            and self._completer.popup()
            and self._completer.popup().isVisible()
            and event.key()
            in (
                Qt.Key.Key_Enter,
                Qt.Key.Key_Return,
                Qt.Key.Key_Escape,
                Qt.Key.Key_Tab,
                Qt.Key.Key_Backtab,
            )
        ):
            event.ignore()
            return

        super().keyPressEvent(event)

        if not self._completer:
            return

        token, _start_pos, _end_pos = self._get_current_token()
        if not token:
            if self._completer.popup():
                self._completer.popup().hide()
            return

        self._update_token_completions(token)

        popup = self._completer.popup()
        if self._completer.completionCount() > 0:
            cr = self.cursorRect()
            cr.setWidth(
                max(
                    220,
                    self._completer.popup().sizeHintForColumn(0)
                    + self._completer.popup().verticalScrollBar().sizeHint().width()
                    + 30,
                )
            )
            self._completer.complete(cr)
        else:
            if popup:
                popup.hide()


class AdvancedExpressionDialog(QDialog):
    """Rich equation editor dialog with component parameter autocomplete, variable inserter, and live preview."""

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
        self.resize(760, 520)

        self._api = api
        self._is_constraint = is_boolean_constraint
        self._evaluator = ExpressionEvaluator()
        self._resolver = ParameterResolver(self._evaluator)
        self._checker = ConstraintChecker(self._evaluator, self._resolver)

        project_data = api.current_project.data if api.current_project else {}
        self._metadata = get_available_symbols_metadata(project_data, api=api)
        self._context = self._metadata.get("context", {})

        layout = QVBoxLayout(self)

        # Expression Input Area
        input_group = QGroupBox("Expression", self)
        input_layout = QVBoxLayout(input_group)

        self.expr_edit = ExpressionLineEdit(self)
        self.expr_edit.setText(initial_expression)
        placeholder = (
            "e.g. main_wing.planform_area >= 0.25 and main_wing.aspect_ratio <= 10.0"
            if self._is_constraint
            else "e.g. =2 * main_wing.planform_area + root_chord / 2"
        )
        self.expr_edit.setPlaceholderText(placeholder)
        self.expr_edit.textChanged.connect(self._on_expression_changed)
        input_layout.addWidget(self.expr_edit)

        # Setup autocompleter
        self._setup_completer()

        # Quick Math Operator Bar
        op_bar = QHBoxLayout()
        for op in ("+", "-", "*", "/", "^", "(", ")", "<=", ">=", "==", "!=", "and", "or"):
            btn = QPushButton(op, self)
            btn.setMaximumWidth(40)
            btn.clicked.connect(lambda _, text=op: self._insert_text(f" {text} "))
            op_bar.addWidget(btn)
        op_bar.addStretch()
        input_layout.addLayout(op_bar)

        layout.addWidget(input_group)

        # Middle Splitter: Variable & Function Picker Tabs
        picker_group = QGroupBox("Insert Variables & Functions", self)
        picker_layout = QVBoxLayout(picker_group)

        self.tabs = QTabWidget(self)

        # Tab 1: Component Properties Tree (e.g. main_wing.planform_area)
        self.comp_tree = QTreeWidget(self)
        self.comp_tree.setHeaderLabels(["Component / Property", "Value", "Expression Tag"])
        self.comp_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.comp_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.comp_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.comp_tree.itemDoubleClicked.connect(self._on_comp_tree_double_clicked)
        self._populate_component_tree()
        self.tabs.addTab(self.comp_tree, "Component Properties")

        # Tab 2: Project Constants
        self.params_table = QTableWidget(0, 3, self)
        self.params_table.setHorizontalHeaderLabels(["Constant", "Current Value", "Unit"])
        self.params_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.params_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.params_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.params_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.params_table.doubleClicked.connect(self._insert_selected_parameter)
        self._populate_parameters_table()
        self.tabs.addTab(self.params_table, "Project Constants")

        # Tab 3: Math Functions
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
        math_funcs = [insert_txt.rstrip("(") for _, insert_txt, _ in MATH_FUNCTIONS]
        constants = [c["key"] for c in self._metadata.get("constants", [])]
        components = self._metadata.get("components", [])
        self.expr_edit.set_symbol_data(constants, components, math_funcs)

    def _populate_component_tree(self) -> None:
        self.comp_tree.clear()
        components = self._metadata.get("components", [])

        for comp in components:
            cid = comp["id"]
            cname = comp["name"]
            ctype = comp["type"]

            parent_item = QTreeWidgetItem([f"{cname} ({cid})", "", ""])
            self.comp_tree.addTopLevelItem(parent_item)

            sections_folder: QTreeWidgetItem | None = None
            section_items: dict[str, QTreeWidgetItem] = {}

            for prop in comp.get("properties", []):
                pkey = prop["key"]
                pval = prop["value"]
                val_str = f"{pval:.4g}" if isinstance(pval, (int, float)) else str(pval)
                expr_tag = prop["expression"]

                if pkey.startswith("section_"):
                    if sections_folder is None:
                        sec_label = (
                            "Stations / Sections"
                            if "lifting" in ctype or "wing" in cid or "tail" in cid
                            else "Cross Sections"
                        )
                        sections_folder = QTreeWidgetItem([sec_label, "", ""])
                        parent_item.addChild(sections_folder)

                    parts = pkey.split("_", 2)
                    if len(parts) >= 3:
                        sec_idx = parts[1]
                        subprop = parts[2]
                        sec_key = f"section_{sec_idx}"
                        if sec_key not in section_items:
                            sec_item = QTreeWidgetItem([f"Section {sec_idx}", "", ""])
                            sections_folder.addChild(sec_item)
                            section_items[sec_key] = sec_item

                        target_sec_item = section_items[sec_key]
                        sub_tag = f"{cid}.{sec_key}.{subprop}"
                        child_item = QTreeWidgetItem([subprop, val_str, sub_tag])
                        child_item.setData(0, Qt.ItemDataRole.UserRole, sub_tag)
                        target_sec_item.addChild(child_item)
                    else:
                        child_item = QTreeWidgetItem([pkey, val_str, expr_tag])
                        child_item.setData(0, Qt.ItemDataRole.UserRole, expr_tag)
                        parent_item.addChild(child_item)
                else:
                    child_item = QTreeWidgetItem([pkey, val_str, expr_tag])
                    child_item.setData(0, Qt.ItemDataRole.UserRole, expr_tag)
                    parent_item.addChild(child_item)

            parent_item.setExpanded(True)
            if sections_folder:
                sections_folder.setExpanded(False)

    def _populate_parameters_table(self) -> None:
        constants = self._metadata.get("constants", [])
        self.params_table.setRowCount(0)
        for row, c in enumerate(constants):
            self.params_table.insertRow(row)
            item_name = QTableWidgetItem(c["key"])
            item_name.setFlags(item_name.flags() & ~Qt.ItemFlag.ItemIsEditable)

            val = c["value"]
            val_str = f"{val:.4g}" if isinstance(val, (int, float)) else str(val)
            item_val = QTableWidgetItem(val_str)
            item_val.setFlags(item_val.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_unit = QTableWidgetItem(c.get("unit", ""))
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

    def _on_comp_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        expr_tag = item.data(0, Qt.ItemDataRole.UserRole)
        if expr_tag:
            self._insert_text(str(expr_tag))

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

    def _resolve_symbol_value(self, sym: str) -> Any:
        if "." in sym:
            parts = sym.split(".")
            curr: Any = self._context
            for p in parts:
                if isinstance(curr, dict) and p in curr:
                    curr = curr[p]
                elif hasattr(curr, p):
                    curr = getattr(curr, p)
                else:
                    return None
            return curr
        return self._context.get(sym)

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
            for sym in sorted(used_symbols):
                sym_val = self._resolve_symbol_value(sym)
                if sym_val is not None:
                    sym_str = (
                        f"{sym_val:.4g}"
                        if isinstance(sym_val, (int, float)) and not isinstance(sym_val, bool)
                        else str(sym_val)
                    )
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
