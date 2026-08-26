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

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
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
        if cls.table_property_text_spinbox and isinstance(editor, QDoubleSpinBox):
            return str(editor.value())
        item = table.item(row, 1)
        return item.text() if item is not None else ""

    @staticmethod
    def _parse_number(value: str) -> float | None:
        try:
            return float(value)
        except ValueError:
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
