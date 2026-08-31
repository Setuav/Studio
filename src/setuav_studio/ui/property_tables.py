"""Shared property-table helpers for editors, docks and dialogs.

`PropertyTableMixin` centralises the duplicate "Property / Value" table
building blocks that previously lived in every component editor, dock and
results panel. Subclasses tune behaviour via class attributes instead of
copying the implementation:

    table_headers                 column labels for _property_table
    table_edit_triggers           edit triggers enabled on the table
    table_value_placeholder       initial text for value cells
    table_value_editable_default  editable flag used when _set_property_value
                                  is called without an explicit editable
    table_combo_cls               widget class used for combo cells
    table_combo_strict_find       only select a combo entry when the value
                                  actually matches one of the options
    table_max_visible_rows        height cap for _fit_table_height (None = all)
    table_scroll_policy_off       disable horizontal/vertical scroll bars
    table_property_text_spinbox   _property_text also reads QDoubleSpinBox cells
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFocusEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class ContentFitTableWidget(QTableWidget):
    """Keep columns content-sized, then share any spare viewport width."""

    def __init__(self, rows: int, columns: int, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self._column_fit_pending = False
        self._fitting_columns = False

    def schedule_column_fit(self) -> None:
        if self._column_fit_pending:
            return
        self._column_fit_pending = True
        QTimer.singleShot(0, self._fit_columns_to_viewport)

    def fit_columns_to_viewport(self) -> None:
        self._fit_columns_to_viewport()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.schedule_column_fit()

    def _fit_columns_to_viewport(self) -> None:
        self._column_fit_pending = False
        if self._fitting_columns or self.columnCount() == 0:
            return

        self._fitting_columns = True
        try:
            # Reset expanded columns to their real header/data requirements.
            self.resizeColumnsToContents()
            visible_columns = [
                column for column in range(self.columnCount()) if not self.isColumnHidden(column)
            ]
            if not visible_columns:
                return

            natural_widths = {column: self.columnWidth(column) for column in visible_columns}
            spare_width = self.viewport().width() - sum(natural_widths.values())
            if spare_width <= 0:
                return

            share, remainder = divmod(spare_width, len(visible_columns))
            for index, column in enumerate(visible_columns):
                self.setColumnWidth(
                    column,
                    natural_widths[column] + share + (1 if index < remainder else 0),
                )
        finally:
            self._fitting_columns = False


class FocusAwareLineEdit(QLineEdit):
    """QLineEdit that emits focus signals to support dual-state evaluated/formula display."""

    focused_in = Signal()
    focused_out = Signal()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.focused_in.emit()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.focused_out.emit()


def format_engineering_value(val: Any, decimals: int | None = 2) -> str:
    """Cleanly formats numbers removing floating-point noise and keeping engineering precision."""
    if val is None or val == "":
        return ""
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return str(val)

    effective_decimals = 2 if decimals is None else decimals
    rounded = round(f_val, effective_decimals)
    if abs(rounded) < 1e-12:
        return "0.0"
    if abs(rounded - int(rounded)) < 1e-9:
        return f"{rounded:.1f}"
    formatted = f"{rounded:.{effective_decimals}f}".rstrip("0")
    if formatted.endswith("."):
        formatted += "0"
    return formatted


class ExpressionPropertyCell(QWidget):
    """Table cell editor widget with dual display (evaluated value when idle, formula when editing) and 'fx' assistant button."""

    def __init__(
        self,
        initial_value: str = "",
        on_changed: Callable[[str], None] | None = None,
        on_open_assistant: Callable[[str], None] | None = None,
        api: Any | None = None,
        label: str = "",
        decimals: int | None = None,
        quantity: str | None = None,
        unit: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if callable(on_changed):
            if hasattr(on_changed, "__self__"):
                self._on_changed = weakref.WeakMethod(on_changed)
            else:
                self._on_changed = on_changed
        else:
            self._on_changed = None
        self._on_open_assistant = on_open_assistant
        self._api = api
        self._label = label
        self._raw_expression = str(initial_value)
        self._is_focused = False

        from setuav_studio.units import get_quantity_for_unit, get_unit_manager

        self._quantity = quantity or get_quantity_for_unit(unit)
        self._suffix = unit or ""
        self._decimals = decimals
        if self._decimals is None:
            lbl = self._label.lower()
            if any(
                w in lbl
                for w in (
                    "eta",
                    "fraction",
                    "taper",
                    "aspect",
                    "ratio",
                    "area",
                    "dm2",
                    "m2",
                    "dm²",
                    "m²",
                )
            ):
                self._decimals = 3
            else:
                self._decimals = 2

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.line_edit = FocusAwareLineEdit(self)
        self.line_edit.focused_in.connect(self._on_focus_in)
        self.line_edit.focused_out.connect(self._on_focus_out)
        self.line_edit.returnPressed.connect(self._on_return_pressed)
        layout.addWidget(self.line_edit, 1)

        self.unit_label = QLabel(self)
        self.unit_label.setObjectName("cellUnitBadge")
        self.unit_label.setStyleSheet(
            "QLabel { color: #f0f0f0; font-size: 11px; font-weight: bold; padding-left: 2px; padding-right: 3px; }"
        )
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.unit_label)

        self.fx_button = QPushButton("fx", self)
        self.fx_button.setToolTip("Open Equation / Expression Assistant")
        self.fx_button.setFixedWidth(24)
        self.fx_button.setFixedHeight(20)
        self.fx_button.setStyleSheet(
            "QPushButton { font-style: italic; font-weight: bold; padding: 0px; font-size: 11px; }"
        )
        self.fx_button.clicked.connect(self._handle_button_clicked)
        layout.addWidget(self.fx_button)

        get_unit_manager().units_changed.connect(self._refresh_display)
        self.destroyed.connect(self._disconnect_units_changed)
        self._refresh_display()

    def _disconnect_units_changed(self) -> None:
        try:
            from setuav_studio.units import get_unit_manager

            get_unit_manager().units_changed.disconnect(self._refresh_display)
        except (RuntimeError, TypeError):
            pass

    def _is_formula(self, text: str) -> bool:
        clean = text.strip()
        return bool(
            clean.startswith("=")
            or (clean and not clean.replace(".", "", 1).replace("-", "", 1).isdigit())
        )

    def _evaluate_expression(self, expr_text: str) -> tuple[bool, Any]:
        """Evaluate expression against current project scope."""
        if self._api is not None and getattr(self._api, "current_project", None) is not None:
            try:
                from setuav_studio.plugins.core.expressions import ExpressionEvaluator

                evaluator = ExpressionEvaluator()
                scope = self._api.current_project.get_scope(api=self._api)
                expr = expr_text.lstrip("=").strip()
                val = evaluator.evaluate(expr, scope)
                return True, val
            except Exception:
                return False, None
        return False, None

    def _display_number(self, base_val: float) -> tuple[str, str]:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        if self._quantity:
            disp_num = um.to_display(base_val, self._quantity)
            sym = um.get_unit_symbol(self._quantity)
            return format_engineering_value(disp_num, self._decimals), sym
        return format_engineering_value(base_val, self._decimals), self._suffix

    def _refresh_display(self) -> None:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        active_sym = um.get_unit_symbol(self._quantity) if self._quantity else (self._suffix or "")
        self.unit_label.setText(active_sym)
        self.unit_label.setVisible(bool(active_sym))

        clean = self._raw_expression.strip()
        if not clean:
            self.line_edit.blockSignals(True)
            self.line_edit.setText("")
            self.line_edit.setStyleSheet("")
            self.line_edit.setToolTip("")
            self.line_edit.blockSignals(False)
            return

        if self._is_focused:
            # Editing mode: show raw formula or current display number
            self.line_edit.blockSignals(True)
            if self._is_formula(clean):
                self.line_edit.setText(self._raw_expression)
                if clean.startswith("="):
                    self.line_edit.setStyleSheet("color: #4CAF50; font-weight: bold;")
                else:
                    self.line_edit.setStyleSheet("")
            else:
                try:
                    num_val = float(clean)
                    disp_val, _ = self._display_number(num_val)
                    self.line_edit.setText(disp_val)
                except ValueError:
                    self.line_edit.setText(self._raw_expression)
                self.line_edit.setStyleSheet("")
            self.line_edit.blockSignals(False)
        else:
            # Idle / Display mode: show evaluated calculated value if it is a formula
            if self._is_formula(clean):
                ok, val = self._evaluate_expression(clean)
                self.line_edit.blockSignals(True)
                if ok and isinstance(val, (int, float)):
                    disp_val, sym = self._display_number(float(val))
                    self.line_edit.setText(disp_val)
                    self.line_edit.setStyleSheet(
                        "color: #4CAF50; font-style: italic; font-weight: bold;"
                    )
                    tip = f"Bound to: {self._raw_expression}\nCalculated value: {disp_val}"
                    if sym:
                        tip += f" {sym}"
                    self.line_edit.setToolTip(tip)
                else:
                    self.line_edit.setText(self._raw_expression)
                    self.line_edit.setStyleSheet("color: #4CAF50; font-weight: bold;")
                    self.line_edit.setToolTip(f"Formula: {self._raw_expression}")
                self.line_edit.blockSignals(False)
            else:
                self.line_edit.blockSignals(True)
                try:
                    num_val = float(clean)
                    disp_val, sym = self._display_number(num_val)
                    self.line_edit.setText(disp_val)
                    self.line_edit.setToolTip(f"{disp_val} {sym}" if sym else "")
                except ValueError:
                    self.line_edit.setText(self._raw_expression)
                    self.line_edit.setToolTip("")
                self.line_edit.setStyleSheet("")
                self.line_edit.blockSignals(False)

    def _on_focus_in(self) -> None:
        self._is_focused = True
        self._refresh_display()
        self.line_edit.selectAll()

    def _convert_input_to_raw_storage(self, text: str) -> str:
        from setuav_studio.units import get_unit_manager

        if not text or self._is_formula(text):
            return text
        try:
            disp_num = float(text)
            base_num = (
                get_unit_manager().to_base(disp_num, self._quantity) if self._quantity else disp_num
            )
            return str(base_num)
        except ValueError:
            return text

    def _call_on_changed(self, text: str) -> None:
        if self._on_changed is None:
            return
        if isinstance(self._on_changed, weakref.WeakMethod):
            cb = self._on_changed()
            if cb is not None:
                cb(text)
        else:
            self._on_changed(text)

    def _commit_line_edit(self) -> None:
        new_text = self.line_edit.text().strip()
        new_raw = self._convert_input_to_raw_storage(new_text)
        if new_raw != self._raw_expression:
            self._raw_expression = new_raw
            self._call_on_changed(self._raw_expression)

    def _on_focus_out(self) -> None:
        self._is_focused = False
        self._commit_line_edit()
        self._refresh_display()

    def _on_return_pressed(self) -> None:
        self._is_focused = False
        self._commit_line_edit()
        self._refresh_display()
        self.line_edit.clearFocus()

    def setDecimals(self, dec: int) -> None:
        self._decimals = dec
        self._refresh_display()

    def _handle_button_clicked(self) -> None:
        if self._on_open_assistant:
            self._on_open_assistant(self._raw_expression)
        elif self._api is not None:
            from setuav_studio.plugins.core.ui.expression_dialog import AdvancedExpressionDialog

            curr_text = self._raw_expression.strip()
            dlg = AdvancedExpressionDialog(
                api=self._api,
                initial_expression=curr_text,
                title=f"Equation Editor — {self._label}" if self._label else "Equation Editor",
                is_boolean_constraint=False,
                parent=self.window(),
            )
            if dlg.exec():
                new_expr = dlg.get_expression().strip()
                if (
                    new_expr
                    and not new_expr.startswith("=")
                    and not new_expr.replace(".", "", 1).isdigit()
                ):
                    new_expr = f"={new_expr}"
                self.setText(new_expr)
                self._call_on_changed(new_expr)

    def text(self) -> str:
        return self._raw_expression

    def setText(self, text: str) -> None:
        self._raw_expression = str(text)
        self._refresh_display()

    def value(self) -> float:
        clean = self._raw_expression.strip()
        if self._is_formula(clean):
            ok, val = self._evaluate_expression(clean)
            if ok and isinstance(val, (int, float)):
                return float(val)
        try:
            return float(clean)
        except ValueError:
            return 0.0

    def setValue(self, val: float | str) -> None:
        self.setText(str(val))
        self._call_on_changed(str(val))

    def suffix(self) -> str:
        from setuav_studio.units import get_unit_manager

        if self._quantity:
            return f" {get_unit_manager().get_unit_symbol(self._quantity)}"
        return f" {self._suffix}" if self._suffix else ""

    def setSuffix(self, suffix: str) -> None:
        self._suffix = suffix.strip()
        self._refresh_display()

    def setRange(self, min_v: float, max_v: float) -> None:
        pass

    def setSingleStep(self, step: float) -> None:
        pass


class PropertyTableMixin:
    """Provides the standard property table helpers to QWidget subclasses."""

    table_headers: tuple[str, str] = ("Property", "Value")
    table_edit_triggers: QAbstractItemView.EditTrigger = (
        QAbstractItemView.EditTrigger.DoubleClicked
        | QAbstractItemView.EditTrigger.EditKeyPressed
        | QAbstractItemView.EditTrigger.SelectedClicked
    )
    table_value_placeholder: str = ""
    table_value_editable_default: bool = True
    table_combo_cls: type[QComboBox] = QComboBox
    table_combo_strict_find: bool = False
    table_max_visible_rows: int | None = 15
    table_scroll_policy_off: bool = False
    table_property_text_spinbox: bool = False

    @classmethod
    def _property_table(
        cls,
        definitions: list[tuple[str, str]],
    ) -> QTableWidget:
        table = cls._table(list(cls.table_headers))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        if cls.table_scroll_policy_off:
            table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setEditTriggers(cls.table_edit_triggers)
        cls._configure_property_table(table, definitions)
        return table

    @classmethod
    def _configure_property_table(
        cls,
        table: QTableWidget,
        definitions: list[tuple[str, str]],
    ) -> None:
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, 1)
            if widget is not None:
                table.removeCellWidget(row, 1)
                widget.deleteLater()
        table.clearContents()
        table.setRowCount(len(definitions))
        for row, (key, label) in enumerate(definitions):
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.ItemDataRole.UserRole, key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, label_item)
            val_item = QTableWidgetItem(cls.table_value_placeholder)
            if cls.table_value_editable_default:
                val_item.setFlags(val_item.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 1, val_item)
        cls._fit_table_height(table, len(definitions))

    def _set_property_combo(
        self,
        table: QTableWidget,
        key: str,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Callable[[str], None],
    ) -> None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            self._set_table_combo(
                table,
                row,
                1,
                value,
                options,
                on_changed,
            )
            return

    @classmethod
    def _set_table_combo(
        cls,
        table: QTableWidget,
        row: int,
        column: int,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Callable[[str], None],
    ) -> None:
        item = table.item(row, column)
        if item is not None:
            item.setText("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        combo = cls.table_combo_cls(table)
        combo.setFont(QApplication.font())
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        combo.view().setProperty("tableComboPopup", True)
        combo.view().setFont(QApplication.font())
        for option_value, label in options:
            combo.addItem(label, option_value)
        if cls.table_combo_strict_find:
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(max(combo.findData(value), 0))
        combo.currentIndexChanged.connect(
            lambda _index, editor=combo, callback=on_changed: callback(str(editor.currentData()))
        )
        table.setCellWidget(row, column, combo)

    @classmethod
    def _set_property_value(
        cls,
        table: QTableWidget,
        key: str,
        value: object,
        *,
        editable: bool | None = None,
    ) -> None:
        if editable is None:
            editable = cls.table_value_editable_default
        for row in range(table.rowCount()):
            if cls._property_key(table, row) != key:
                continue
            item = table.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, 1, item)
            item.setText(str(value))
            if editable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return

    def _set_property_spinbox(
        self,
        table: QTableWidget,
        key: str,
        value: float | str,
        *,
        min_val: float = -1e6,
        max_val: float = 1e6,
        step: float = 1.0,
        decimals: int = 2,
        suffix: str = "",
        on_changed: Callable[[Any], None] | None = None,
        api: Any | None = None,
        label: str = "",
    ) -> Any:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            from setuav_studio.ui.numeric_spinbox import set_table_spinbox

            resolved_label = label
            if not resolved_label:
                col0_item = table.item(row, 0)
                resolved_label = col0_item.text() if col0_item else key

            return set_table_spinbox(
                table,
                row,
                1,
                value,
                min_val=min_val,
                max_val=max_val,
                step=step,
                decimals=decimals,
                suffix=suffix,
                on_changed=on_changed,
                api=api or getattr(self, "_api", None),
                label=resolved_label,
            )
        return None

    def _set_property_expression(
        self,
        table: QTableWidget,
        key: str,
        value: object,
        on_changed: Callable[[str], None] | None = None,
        on_open_assistant: Callable[[str], None] | None = None,
        api: Any | None = None,
        label: str = "",
        decimals: int | None = None,
        quantity: str | None = None,
        unit: str | None = None,
    ) -> None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            item = table.item(row, 1)
            if item is not None:
                item.setText("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            resolved_label = label
            if not resolved_label:
                col0_item = table.item(row, 0)
                resolved_label = col0_item.text() if col0_item else key

            cell = ExpressionPropertyCell(
                initial_value=str(value) if value is not None else "",
                on_changed=on_changed,
                on_open_assistant=on_open_assistant,
                api=api or getattr(self, "_api", None),
                label=resolved_label,
                decimals=decimals,
                quantity=quantity,
                unit=unit,
                parent=table,
            )
            table.setCellWidget(row, 1, cell)
            return

    @staticmethod
    def _property_key(table: QTableWidget, row: int) -> str:
        item = table.item(row, 0)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    @classmethod
    def _property_text(cls, table: QTableWidget, row: int) -> str:
        editor = table.cellWidget(row, 1)
        if isinstance(editor, QComboBox):
            return str(editor.currentData())
        if isinstance(editor, ExpressionPropertyCell):
            return editor.text()
        if cls.table_property_text_spinbox and isinstance(editor, QDoubleSpinBox):
            return str(editor.value())
        item = table.item(row, 1)
        return item.text() if item is not None else ""

    @staticmethod
    def _parse_number(value: str) -> float | None:
        try:
            return float(value.strip())
        except ValueError:
            tokens = value.strip().split()
            if tokens:
                try:
                    return float(tokens[0])
                except ValueError:
                    pass
            return None

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setFixedHeight(23)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        return table

    @classmethod
    def _fit_table_height(
        cls,
        table: QTableWidget,
        row_count: int,
        maximum_visible_rows: int | None = None,
    ) -> None:
        if maximum_visible_rows is None:
            maximum_visible_rows = cls.table_max_visible_rows
        if maximum_visible_rows is None:
            visible_rows = max(row_count, 1)
        else:
            visible_rows = min(max(row_count, 1), maximum_visible_rows)
        height = (
            table.horizontalHeader().height()
            + table.verticalHeader().defaultSectionSize() * visible_rows
            + 2
        )
        table.setFixedHeight(height)
