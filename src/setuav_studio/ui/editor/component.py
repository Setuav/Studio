"""Base reusable property editor and parameter descriptors for Setuav components."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QPersistentModelIndex, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import ParameterField, TableParameterField
from setuav_studio.model.expression import (
    ExpressionEvaluator,
    get_expression,
    normalize_equation_input,
    set_expression,
)
from setuav_studio.ui.style.icons import get_icon, set_label_icon
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input
from setuav_studio.ui.widget.table import (
    ContentFitTableWidget,
    ExpressionFocusTracker,
    FocusAwareLineEdit,
    PropertyTableMixin,
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


class _TableCellAssistantAdapter:
    """Adapts table cell editor to Equation Assistant dialog."""

    def __init__(
        self,
        edit: FocusAwareLineEdit,
        label: str,
        api: Any,
        table: QTableWidget | None,
        row: int,
        col: int,
    ) -> None:
        self._edit = edit
        self._label = label
        self._api = api
        self._table = table
        self._row = row
        self._col = col

    def get_expression(self) -> str:
        try:
            return self._edit.text().strip()
        except RuntimeError:
            if self._table is not None:
                item = self._table.item(self._row, self._col)
                if item is not None:
                    user_val = item.data(Qt.ItemDataRole.UserRole)
                    return str(user_val if user_val is not None else item.text()).strip()
            return ""

    def set_expression(self, expr: str) -> None:
        with contextlib.suppress(RuntimeError):
            self._edit.setText(expr)
        if self._table is not None:
            item = self._table.item(self._row, self._col)
            if item is not None:
                item.setData(Qt.ItemDataRole.UserRole, expr)
                item.setText(expr)

    def get_label(self) -> str:
        return self._label

    def open_assistant(self) -> None:
        from setuav_studio.ui.dialog.expression_dialog import AdvancedExpressionDialog

        parent_win = self._table.window() if self._table else None
        dlg = AdvancedExpressionDialog(
            api=self._api,
            initial_expression=self.get_expression(),
            title=f"Equation Editor — {self._label}",
            is_boolean_constraint=False,
            parent=parent_win,
        )
        if dlg.exec():
            new_expr = normalize_equation_input(dlg.get_expression())
            self.set_expression(new_expr)


class TableExpressionDelegate(QStyledItemDelegate):
    """Item delegate for TableParameterField tables providing autocomplete and Formula Assistant integration."""

    def __init__(
        self,
        api: StudioAPI | None,
        table_field: TableParameterField,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._tf = table_field

    def createEditor(
        self,
        parent: QWidget,
        option: Any,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        # Only editable value cells reach the delegate: the unit row, the index
        # column and read-only columns are created without ItemIsEditable.
        col_field = self._tf.columns[index.column() - 1]
        line_edit = FocusAwareLineEdit(parent, api=self._api)
        table_widget = parent if isinstance(parent, QTableWidget) else None

        adapter = _TableCellAssistantAdapter(
            line_edit,
            f"{self._tf.label} {col_field.label}",
            self._api,
            table_widget,
            index.row(),
            index.column(),
        )
        line_edit.focused_in.connect(lambda: ExpressionFocusTracker.set_active_editor(adapter))
        line_edit.focused_out.connect(
            lambda: QTimer.singleShot(
                400,
                lambda: (
                    ExpressionFocusTracker.set_active_editor(None)
                    if ExpressionFocusTracker.get_active_editor() is adapter
                    else None
                ),
            )
        )
        return line_edit

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:
        if isinstance(editor, QLineEdit):
            raw = index.data(Qt.ItemDataRole.UserRole)
            if raw is not None and ExpressionEvaluator.is_expression(str(raw)):
                editor.setText(str(raw))
            else:
                editor.setText(str(index.data(Qt.ItemDataRole.DisplayRole) or ""))

    def setModelData(
        self,
        editor: QWidget,
        model: QAbstractItemModel,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        if isinstance(editor, QLineEdit):
            text = editor.text().strip()
            model.setData(index, text, Qt.ItemDataRole.EditRole)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_table_cell_value(val: Any, col_field: ParameterField) -> str:
    """Display text of a stored table cell value."""
    if col_field.field_type is float and _is_number(val):
        return f"{float(val):.{col_field.decimals}f}"
    if col_field.field_type is int and _is_number(val):
        return str(int(val))
    return str(val if val is not None else "")


class BaseComponentEditor(PropertyTableMixin, QWidget):
    """Reusable base property editor for Setuav project components styled after Fuselage/Wing editors."""

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        parameter_fields: Sequence[ParameterField] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._component = component
        self._fields = list(parameter_fields)
        self._scalar_fields = [f for f in self._fields if not isinstance(f, TableParameterField)]
        self._table_fields = [f for f in self._fields if isinstance(f, TableParameterField)]
        self._table_widgets: dict[str, ContentFitTableWidget] = {}
        self._committed_table_params: dict[str, list[dict[str, Any]]] = {}
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_general_section()
        if self._scalar_fields:
            self._create_parameters_section()
        if self._table_fields:
            self._create_table_parameters_sections()
        self._create_custom_sections()

        self._content_layout.addStretch()
        params = self._component.get("parameters", {})
        self._committed_params: dict[str, Any] = dict(params) if isinstance(params, dict) else {}
        exprs = params.get("_expressions") if isinstance(params, dict) else None
        self._committed_expressions: dict[str, str] = dict(exprs) if isinstance(exprs, dict) else {}
        self._committed_mass: Any = self._component.get("mass")
        self._committed_mass_expr: str | None = get_expression(self._component, "mass")
        self._committed_name: str = str(self._component.get("name") or "")
        self._committed_attach_to: str = str(self._component.get("attach_to") or "")
        self._load_component()
        if self._api is not None:
            self._api.on_project_content_changed(self._on_external_content_changed)

    def closeEvent(self, event: Any) -> None:
        if self._api is not None:
            with contextlib.suppress(Exception):
                self._api.remove_project_content_listener(self._on_external_content_changed)
        super().closeEvent(event)

    def _create_section(
        self,
        title: str,
        icon_name: str | None = None,
        action_widget: QWidget | None = None,
    ) -> QVBoxLayout:
        section = QWidget()
        # Tables already calculate and fix their content height. Prevent the
        # scroll area's spare vertical space from being distributed into the
        # section and separating its header from its table.
        section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        if icon_name:
            icon_label = QLabel()
            set_label_icon(icon_label, icon_name)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        if action_widget is not None:
            header_layout.addWidget(action_widget)

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mass", "Mass"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_parameters_section(self) -> None:
        if not self._scalar_fields:
            return
        layout = self._create_section("Parameters", "fa6s.sliders")
        defs: list[tuple[str, str]] = []
        for f in self._scalar_fields:
            defs.append((f.key, f.label))

        self.parameters_table = self._property_table(defs)
        self.parameters_table.cellChanged.connect(self._update_parameter_cell)
        layout.addWidget(self.parameters_table)

    def _create_table_parameters_sections(self) -> None:
        for tf in self._table_fields:
            action_bar = QWidget()
            ab_layout = QHBoxLayout(action_bar)
            ab_layout.setContentsMargins(0, 0, 0, 0)
            ab_layout.setSpacing(4)

            add_btn = QToolButton()
            add_btn.setIcon(get_icon("add"))
            add_btn.setToolTip(f"Add row to {tf.label}")
            add_btn.setAutoRaise(True)
            add_btn.setFixedSize(20, 20)
            add_btn.clicked.connect(lambda checked=False, k=tf.key: self._on_add_table_row(k))
            ab_layout.addWidget(add_btn)

            remove_btn = QToolButton()
            remove_btn.setIcon(get_icon("remove"))
            remove_btn.setToolTip(f"Remove selected row from {tf.label}")
            remove_btn.setAutoRaise(True)
            remove_btn.setFixedSize(20, 20)
            remove_btn.clicked.connect(lambda checked=False, k=tf.key: self._on_remove_table_row(k))
            ab_layout.addWidget(remove_btn)

            layout = self._create_section(tf.label, "mdi6.table-large", action_widget=action_bar)

            headers = ["#"] + [col.label for col in tf.columns]
            table = ContentFitTableWidget(0, len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(22)
            table.horizontalHeader().setFixedHeight(23)
            table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.ResizeToContents
            )
            for c_idx in range(1, len(headers)):
                table.horizontalHeader().setSectionResizeMode(c_idx, QHeaderView.ResizeMode.Stretch)
            table.setAlternatingRowColors(True)
            table.setItemDelegate(TableExpressionDelegate(self._api, tf, parent=table))

            table.cellChanged.connect(
                lambda row, col, k=tf.key: self._on_table_cell_changed(k, row, col)
            )
            self._table_widgets[tf.key] = table
            layout.addWidget(table)

    def _create_custom_sections(self) -> None:
        """Hook for subclasses to add custom property sections."""
        pass

    def _load_component(self) -> None:
        self._loading = True
        try:
            # Load General
            self._set_property_value(
                self.general_table, "name", str(self._component.get("name") or "")
            )
            self._set_property_value(
                self.general_table,
                "type",
                str(self._component.get("type") or ""),
                editable=False,
            )
            mass_val = get_expression(self._component, "mass") or self._component.get("mass", 0.0)
            self._set_property_expression(
                self.general_table,
                "mass",
                mass_val,
                target_data=self._component,
                raw_callback=True,
                on_changed=self._on_mass_changed,
                label="Mass",
                unit="g",
            )

            # Load Scalar Parameters
            params = self._component.get("parameters", {})
            if hasattr(self, "parameters_table") and self._scalar_fields:
                self.bind_parametric_properties(
                    self.parameters_table,
                    params,
                    self._scalar_fields,
                    on_changed=self._on_param_changed,
                    api=self._api,
                )

            # Load Table Parameters
            for tf in self._table_fields:
                rows = params.get(tf.key)
                if not isinstance(rows, list):
                    rows = [dict(r) if isinstance(r, dict) else r for r in (tf.default or ())]
                    params[tf.key] = rows
                self._populate_table_widget(tf, rows)
                self._committed_table_params[tf.key] = deepcopy(rows)

            self._load_custom_data()
            params = self._component.get("parameters", {})
            self._committed_params = dict(params) if isinstance(params, dict) else {}
            exprs = params.get("_expressions") if isinstance(params, dict) else None
            self._committed_expressions = dict(exprs) if isinstance(exprs, dict) else {}
            self._committed_mass = self._component.get("mass")
            self._committed_mass_expr = get_expression(self._component, "mass")
            self._committed_name = str(self._component.get("name") or "")
            self._committed_attach_to = str(self._component.get("attach_to") or "")
        finally:
            self._loading = False

    def _populate_table_widget(self, tf: TableParameterField, rows: list[dict[str, Any]]) -> None:
        table = self._table_widgets.get(tf.key)
        if table is None:
            return
        table.blockSignals(True)
        try:
            table.setRowCount(len(rows) + 1)

            # Row 0: Dedicated Unit row (matching Result Table style)
            italic_font = QFont()
            italic_font.setItalic(True)
            unit_color = QColor("#888888")

            unit_hdr = QTableWidgetItem("Unit")
            unit_hdr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            unit_hdr.setFont(italic_font)
            unit_hdr.setForeground(unit_color)
            unit_hdr.setFlags(
                unit_hdr.flags() & ~Qt.ItemFlag.ItemIsEditable & ~Qt.ItemFlag.ItemIsSelectable
            )
            table.setItem(0, 0, unit_hdr)

            for c_idx, col_field in enumerate(tf.columns):
                u = col_field.unit
                unit_text = f"[{u}]" if u else "[-]"
                u_item = QTableWidgetItem(unit_text)
                u_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                u_item.setFont(italic_font)
                u_item.setForeground(unit_color)
                u_item.setFlags(
                    u_item.flags() & ~Qt.ItemFlag.ItemIsEditable & ~Qt.ItemFlag.ItemIsSelectable
                )
                table.setItem(0, c_idx + 1, u_item)

            for r_idx, row_data in enumerate(rows):
                table_row = r_idx + 1
                idx_item = QTableWidgetItem(str(r_idx + 1))
                idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                idx_item.setFlags(idx_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(table_row, 0, idx_item)

                for c_idx, col_field in enumerate(tf.columns):
                    val = row_data.get(col_field.key, col_field.default)
                    display_text = _format_table_cell_value(val, col_field)
                    formula = get_expression(row_data, col_field.key)

                    cell_item = QTableWidgetItem(display_text)
                    # The delegate edits the formula when the cell has one.
                    cell_item.setData(Qt.ItemDataRole.UserRole, formula or val)
                    if formula:
                        cell_item.setToolTip(f"Formula: {formula}\nCalculated: {display_text}")
                    if col_field.field_type in (float, int):
                        cell_item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        )
                    else:
                        cell_item.setTextAlignment(
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                        )
                    if tf.readonly or col_field.readonly:
                        cell_item.setFlags(cell_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    table.setItem(table_row, c_idx + 1, cell_item)
            self._fit_table_height(table, len(rows) + 1, maximum_visible_rows=10)
            table.schedule_column_fit()
        finally:
            table.blockSignals(False)

    def _on_add_table_row(self, key: str) -> None:
        if self._loading:
            return
        tf = next((f for f in self._table_fields if f.key == key), None)
        if tf is None or tf.readonly:
            return
        params = self._component.setdefault("parameters", {})
        rows = params.get(key)
        if not isinstance(rows, list):
            rows = []
            params[key] = rows
        if tf.max_rows is not None and len(rows) >= tf.max_rows:
            return

        new_row = {col.key: col.default for col in tf.columns}
        # Continue the spacing of numeric offsets; an expression offset leaves the default.
        offsets = [row.get("offset") for row in rows[-2:]]
        if "offset" in new_row and offsets and all(_is_number(o) for o in offsets):
            prev_offset = float(offsets[-1])
            delta = prev_offset - float(offsets[0]) if len(offsets) == 2 else 100.0
            new_row["offset"] = prev_offset + max(delta, 10.0)
        new_rows = deepcopy(rows)
        new_rows.append(new_row)
        self._commit_table_param(key, new_rows)

    def _on_remove_table_row(self, key: str) -> None:
        if self._loading:
            return
        tf = next((f for f in self._table_fields if f.key == key), None)
        table = self._table_widgets.get(key)
        if tf is None or table is None or tf.readonly:
            return
        params = self._component.setdefault("parameters", {})
        rows = params.get(key)
        if not isinstance(rows, list) or len(rows) <= tf.min_rows:
            return

        selected_data_rows = sorted(
            {idx.row() - 1 for idx in table.selectedIndexes() if idx.row() > 0}, reverse=True
        )
        target_idx = selected_data_rows[0] if selected_data_rows else len(rows) - 1
        if 0 <= target_idx < len(rows):
            new_rows = deepcopy(rows)
            new_rows.pop(target_idx)
            self._commit_table_param(key, new_rows)

    def _on_table_cell_changed(self, key: str, row: int, col: int) -> None:
        if self._loading or row == 0 or col == 0:
            return
        tf = next((f for f in self._table_fields if f.key == key), None)
        table = self._table_widgets.get(key)
        if tf is None or table is None or tf.readonly:
            return
        col_idx = col - 1
        if not (0 <= col_idx < len(tf.columns)):
            return
        col_field = tf.columns[col_idx]
        item = table.item(row, col)
        if item is None:
            return
        raw_text = item.text().strip()

        params = self._component.setdefault("parameters", {})
        rows = params.get(key)
        data_row = row - 1
        if not isinstance(rows, list) or not (0 <= data_row < len(rows)):
            return
        row_data = rows[data_row]

        value: Any = raw_text
        expression: str | None = None
        if col_field.field_type in (float, int):
            parsed = evaluate_table_cell_input(
                raw_text,
                self._api,
                label=f"{tf.label} {col_field.label}",
                min_val=col_field.min_value,
                max_val=col_field.max_value,
            )
            if parsed is None:
                # Put the stored value back; the status bar names the error.
                self._populate_table_widget(tf, rows)
                return
            value, expression = parsed
            if col_field.field_type is int:
                value = round(value)
        if row_data.get(col_field.key) == value and (
            get_expression(row_data, col_field.key) == expression
        ):
            return

        new_rows = deepcopy(rows)
        new_rows[data_row][col_field.key] = value
        set_expression(new_rows[data_row], col_field.key, expression)
        self._commit_table_param(key, new_rows)

    def _commit_table_param(self, key: str, new_rows: list[dict[str, Any]]) -> None:
        tf = next((f for f in self._table_fields if f.key == key), None)

        def change() -> None:
            self._component.setdefault("parameters", {})[key] = new_rows

        if self._api is not None:
            self._api.edit_component(
                self._component,
                f"Edit {tf.label if tf else key}",
                change,
            )
        else:
            change()
        self._committed_table_params[key] = deepcopy(new_rows)
        if tf is not None:
            self._populate_table_widget(tf, new_rows)
        self.update_viewport()

    def _load_custom_data(self) -> None:
        """Hook for subclasses to populate data in custom sections."""
        pass

    def _on_param_changed(self, key: str, final_val: Any, new_expr: str | None) -> None:
        if self._loading:
            return

        old_val = self._committed_params.get(key)
        old_expr = self._committed_expressions.get(key)
        if old_val == final_val and old_expr == new_expr:
            return

        def apply_param() -> None:
            params = self._component.setdefault("parameters", {})
            params[key] = final_val
            set_expression(params, key, new_expr)

            self._committed_params[key] = final_val
            if new_expr is not None:
                self._committed_expressions[key] = new_expr
            else:
                self._committed_expressions.pop(key, None)

        self._api.edit_component(
            self._component,
            f"Set {key} of {self._component.get('name', 'component')}",
            apply_param,
        )
        self.update_viewport()

    def update_viewport(self) -> None:
        """Hook called when parameters change, allowing the editor to update its 3D object directly."""
        pass

    def _on_external_content_changed(self, project: Any = None) -> None:
        if self._loading:
            return
        curr_params = self._component.get("parameters", {})
        curr_exprs_raw = curr_params.get("_expressions") if isinstance(curr_params, dict) else None
        curr_exprs = dict(curr_exprs_raw) if isinstance(curr_exprs_raw, dict) else {}
        curr_mass = self._component.get("mass")
        curr_mass_expr = get_expression(self._component, "mass")
        curr_name = str(self._component.get("name") or "")
        curr_attach_to = str(self._component.get("attach_to") or "")
        if (
            curr_params != self._committed_params
            or curr_exprs != self._committed_expressions
            or curr_mass != self._committed_mass
            or curr_mass_expr != self._committed_mass_expr
            or curr_name != self._committed_name
            or curr_attach_to != self._committed_attach_to
        ):
            self._load_component()
            self.update_viewport()
        else:
            self._load_custom_data()

    def _on_mass_changed(self, val_text: Any) -> None:
        if self._loading:
            return
        cell = self._property_cell(self.general_table, "mass")
        parsed = evaluate_table_cell_input(
            val_text,
            self._api,
            cell=cell,
            label="Mass",
        )
        if parsed is None:
            return
        num_val, new_expr = parsed
        if (
            self._component.get("mass") == num_val
            and get_expression(self._component, "mass") == new_expr
        ):
            return

        def change() -> None:
            self._component["mass"] = num_val
            set_expression(self._component, "mass", new_expr)
            self._committed_mass = num_val
            self._committed_mass_expr = new_expr

        self._api.edit_component(self._component, "Change component mass", change)

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return

        key = self._property_key(self.general_table, row)
        val_text = self._property_text(self.general_table, row)

        def apply_edit() -> None:
            if key == "name":
                self._component["name"] = val_text
            elif key == "mass":
                num = self._parse_number(val_text) or 0.0
                self._component["mass"] = num

        self._api.edit_component(
            self._component,
            f"Edit {key} of {self._component.get('name', 'component')}",
            apply_edit,
        )

    def _update_parameter_cell(self, row: int, column: int) -> None:
        """Commit a user edit of a plain-text parameter item.

        Numeric, choice and color parameters commit through their cell widget;
        read-only parameters are displayed only and never written back.
        """
        if (
            self._loading
            or column != 1
            or self.parameters_table.cellWidget(row, column) is not None
        ):
            return
        key = self._property_key(self.parameters_table, row)
        field = next((f for f in self._scalar_fields if f.key == key), None)
        item = self.parameters_table.item(row, column)
        if field is None or field.readonly or item is None or not item.text():
            return
        self._on_param_changed(key, item.text(), None)
