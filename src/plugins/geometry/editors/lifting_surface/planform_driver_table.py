"""Interactive 8-Variable 3-Driver Planform Table Widget (OpenVSP style).

Provides an 8-row table with:
- Column 0: Driver Checkbox (Enforces exactly max 3 active drivers; disables remaining when 3 are selected).
- Column 1: Parameter Name.
- Column 2: Value (Editable number or formula for active drivers, measured value for others).

The table reports an edited driver as its value and formula; the editor applies it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input
from setuav_studio.ui.widget.table import ExpressionPropertyCell

from ...engine.lifting_surface_driver_solver import (
    PLANFORM_PARAM_KEYS,
    PLANFORM_PARAM_LABELS,
    PLANFORM_PARAM_UNITS,
)


class DriverPlanformTable(QTableWidget):
    """8-row Planform Table with 3-Driver Checkbox column and real-time expression/numeric solving."""

    def __init__(
        self,
        active_drivers: list[str],
        on_driver_changed: Callable[[str, float, str | None], None],
        on_drivers_changed: Callable[[list[str]], None],
        api: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(8, 3, parent)
        self._api = api
        self._active_drivers = list(active_drivers)
        self._on_driver_changed = on_driver_changed
        self._on_drivers_changed = on_drivers_changed
        self._driver_expressions: dict[str, str] = {}
        self._current_values: dict[str, float] = {}
        self._updating = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setHorizontalHeaderLabels(["Driver", "Parameter", "Value"])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setFixedHeight(23)
        self.setAlternatingRowColors(True)

        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 52)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(23 + 24 * 8 + 2)

        for row, key in enumerate(PLANFORM_PARAM_KEYS):
            # 1. Driver Checkbox (Col 0)
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb = QCheckBox()
            cb.setChecked(key in self._active_drivers)
            cb.toggled.connect(lambda checked, k=key: self._on_driver_toggled(k, checked))
            cb_layout.addWidget(cb)
            self.setCellWidget(row, 0, cb_container)

            # 2. Parameter Label (Col 1)
            label_item = QTableWidgetItem(PLANFORM_PARAM_LABELS[key])
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.setItem(row, 1, label_item)

            # 3. Value Item placeholder (Col 2)
            val_item = QTableWidgetItem("")
            val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.setItem(row, 2, val_item)

        from setuav_studio.units import get_unit_manager

        get_unit_manager().units_changed.connect(self._refresh_table_widgets)
        self._update_checkbox_states()

    def set_parameters(
        self,
        values: dict[str, float],
        *,
        active_drivers: list[str],
        expressions: dict[str, str],
    ) -> None:
        """Show the 8 planform values, the active drivers and the drivers' formulas."""
        self._current_values = {key: values[key] for key in PLANFORM_PARAM_KEYS}
        self._active_drivers = list(active_drivers)
        self._driver_expressions = dict(expressions)
        self._refresh_table_widgets()

    def get_active_drivers(self) -> list[str]:
        return list(self._active_drivers)

    def _on_driver_toggled(self, key: str, checked: bool) -> None:
        if self._updating:
            return

        if checked:
            if key not in self._active_drivers:
                if len(self._active_drivers) < 3:
                    self._active_drivers.append(key)
                else:
                    self._update_checkbox_ui(key, False)
                    return
        else:
            if key in self._active_drivers:
                self._active_drivers.remove(key)

        self._refresh_table_widgets()
        self._on_drivers_changed(list(self._active_drivers))

    def _update_checkbox_ui(self, key: str, checked: bool) -> None:
        row = PLANFORM_PARAM_KEYS.index(key)
        container = self.cellWidget(row, 0)
        if container:
            cb = container.findChild(QCheckBox)
            if cb:
                was = self._updating
                self._updating = True
                cb.setChecked(checked)
                self._updating = was

    def _update_checkbox_states(self) -> None:
        """Enable checked boxes always; enable unchecked boxes ONLY if fewer than 3 drivers are selected."""
        count = len(self._active_drivers)
        for row, key in enumerate(PLANFORM_PARAM_KEYS):
            container = self.cellWidget(row, 0)
            if container:
                cb = container.findChild(QCheckBox)
                if cb:
                    is_active = key in self._active_drivers
                    was = self._updating
                    self._updating = True
                    cb.setChecked(is_active)
                    cb.setEnabled(is_active or count < 3)
                    self._updating = was

    def _refresh_table_widgets(self) -> None:
        was = self._updating
        self._updating = True
        try:
            self._update_checkbox_states()
            from setuav_studio.units import get_quantity_for_unit, get_unit_manager

            um = get_unit_manager()

            for row, key in enumerate(PLANFORM_PARAM_KEYS):
                is_driver = key in self._active_drivers
                unit = PLANFORM_PARAM_UNITS[key]
                val = self._current_values.get(key, 0.0)

                # Style parameter label
                label_item = self.item(row, 1)
                if label_item:
                    font = label_item.font()
                    font.setBold(is_driver)
                    label_item.setFont(font)

                if is_driver:
                    # Clear underlying item text to prevent ghosting behind the cell widget
                    item = self.item(row, 2)
                    if item:
                        item.setText("")
                    else:
                        self.setItem(row, 2, QTableWidgetItem(""))

                    raw_expr = self._driver_expressions.get(key)
                    dec = 3 if key in ("area", "taper_ratio", "aspect_ratio") else 2
                    if raw_expr:
                        init_str = raw_expr
                    else:
                        from setuav_studio.ui.widget.table import format_engineering_value

                        q_id = get_quantity_for_unit(unit)
                        disp_val = um.to_display(val, q_id) if q_id else val
                        init_str = format_engineering_value(disp_val, dec)

                    label_name = PLANFORM_PARAM_LABELS[key]
                    q_id = get_quantity_for_unit(unit)
                    cell = ExpressionPropertyCell(
                        initial_value=init_str,
                        on_changed=lambda s, k=key: self._on_expression_cell_changed(k, s),
                        api=self._api,
                        label=label_name,
                        decimals=dec,
                        quantity=q_id,
                        unit=unit,
                        parent=self,
                    )
                    self.setCellWidget(row, 2, cell)
                else:
                    self.removeCellWidget(row, 2)
                    dec = 3 if key in ("area", "taper_ratio", "aspect_ratio") else 2
                    q_id = get_quantity_for_unit(unit)
                    if q_id:
                        disp_val = um.to_display(val, q_id)
                        sym = um.get_unit_symbol(q_id)
                    else:
                        disp_val = val
                        sym = unit or ""

                    val_str = f"{disp_val:.{dec}f}"
                    if sym:
                        val_str += f" {sym}"
                    val_item = self.item(row, 2)
                    if not val_item:
                        val_item = QTableWidgetItem(val_str)
                        self.setItem(row, 2, val_item)
                    else:
                        val_item.setText(val_str)
                    val_item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
        finally:
            self._updating = was

    def _on_expression_cell_changed(self, edited_key: str, text: str) -> None:
        if self._updating:
            return
        clean = text.strip()
        if not clean:
            return

        row = PLANFORM_PARAM_KEYS.index(edited_key)
        cell = self.cellWidget(row, 2)
        parsed = evaluate_table_cell_input(
            clean,
            self._api,
            cell=cell if isinstance(cell, ExpressionPropertyCell) else None,
            label=PLANFORM_PARAM_LABELS[edited_key],
        )
        if parsed is None:
            return

        # The cell hands over typed numbers already converted to base units.
        num_val, expr_to_store = parsed
        self._on_driver_changed(edited_key, num_val, expr_to_store)
