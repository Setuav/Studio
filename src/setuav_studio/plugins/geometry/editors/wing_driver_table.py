"""Interactive 8-Variable 3-Driver Planform Table Widget (OpenVSP style).

Provides an 8-row table with:
- Column 0: Driver Checkbox (Enforces exactly max 3 active drivers; disables remaining when 3 are selected).
- Column 1: Parameter Name.
- Column 2: Value (Editable spinbox for active drivers, calculated display for others).
"""

from __future__ import annotations

import contextlib
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

from setuav_studio.ui.property_tables import ExpressionPropertyCell

from ..engine.wing_driver_solver import (
    PLANFORM_PARAM_KEYS,
    PLANFORM_PARAM_LABELS,
    PLANFORM_PARAM_UNITS,
    solve_8_parameter_driver,
)


class DriverPlanformTable(QTableWidget):
    """8-row Planform Table with 3-Driver Checkbox column and real-time expression/numeric solving."""

    def __init__(
        self,
        default_drivers: list[str] | None = None,
        on_values_changed: Callable[[dict[str, float]], None] | None = None,
        api: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(8, 3, parent)
        self._api = api
        self._active_drivers: list[str] = list(
            default_drivers or ["span", "root_chord", "tip_chord"]
        )
        self._on_values_changed = on_values_changed
        self._driver_expressions: dict[str, str] = {}
        self._current_values: dict[str, float] = {
            "area": 200000.0,
            "span": 1200.0,
            "aspect_ratio": 7.2,
            "taper_ratio": 0.5,
            "root_chord": 222.2,
            "tip_chord": 111.1,
            "ave_chord": 166.7,
            "mac": 172.8,
        }
        self._is_symmetric = True
        self._y_offset = 0.0
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
        expressions: dict[str, str] | None = None,
        is_symmetric: bool = True,
        y_offset: float = 0.0,
    ) -> None:
        """Update table with full 8 parameters and refresh input cells/labels."""
        self._is_symmetric = is_symmetric
        self._y_offset = y_offset
        self._current_values.update(values)
        if expressions is not None:
            self._driver_expressions.update(expressions)
        self._refresh_table_widgets()

    def get_active_drivers(self) -> list[str]:
        return list(self._active_drivers)

    def get_driver_expressions(self) -> dict[str, str]:
        return dict(self._driver_expressions)

    def get_current_values(self) -> dict[str, float]:
        return dict(self._current_values)

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
                    init_str = raw_expr or str(val)

                    dec = 3 if key in ("area", "taper_ratio", "aspect_ratio") else 2
                    label_name = PLANFORM_PARAM_LABELS[key]
                    cell = ExpressionPropertyCell(
                        initial_value=init_str,
                        on_changed=lambda s, k=key: self._on_expression_cell_changed(k, s),
                        api=self._api,
                        label=label_name,
                        decimals=dec,
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

        eval_val: float | None = None
        if clean.startswith("=") or not clean.replace(".", "", 1).replace("-", "", 1).isdigit():
            # Formula
            self._driver_expressions[edited_key] = clean
            if self._api is not None and getattr(self._api, "current_project", None) is not None:
                try:
                    from setuav_studio.plugins.core.expressions import ExpressionEvaluator

                    evaluator = ExpressionEvaluator()
                    scope = self._api.current_project.get_scope(api=self._api)
                    expr = clean.lstrip("=").strip()
                    res = evaluator.evaluate(expr, scope)
                    if isinstance(res, (int, float)):
                        eval_val = float(res)
                except Exception:
                    pass
        else:
            self._driver_expressions.pop(edited_key, None)
            with contextlib.suppress(ValueError):
                eval_val = float(clean)

        if eval_val is not None:
            self._on_spinbox_value_changed(edited_key, eval_val)

    def _on_spinbox_value_changed(self, edited_key: str, value: float) -> None:
        inputs = dict(self._current_values)
        inputs[edited_key] = float(value)

        # If exactly 3 drivers, solve for all 8; if fewer, solve with active drivers
        solved = solve_8_parameter_driver(
            self._active_drivers,
            inputs,
            self._current_values,
            is_symmetric=self._is_symmetric,
            y_offset=self._y_offset,
        )
        self._current_values = solved
        self._refresh_table_widgets()

        if self._on_values_changed:
            self._on_values_changed(self._current_values)
