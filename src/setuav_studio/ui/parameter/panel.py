"""Panel for managing project-level constants, variables, and derived formulas."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.model.configuration import ConfigurationManager
from setuav_studio.model.parameter import ParameterResolver
from setuav_studio.ui.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ProjectParametersPanel(QWidget):
    """Panel displaying and editing project parameters and formulas."""

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._resolver = ParameterResolver()
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Toolbar / buttons
        btn_bar = QHBoxLayout()
        self.btn_add = QPushButton(get_icon("fa6s.plus"), "Add Parameter")
        self.btn_add.clicked.connect(self._add_parameter)
        btn_bar.addWidget(self.btn_add)

        self.btn_fx = QPushButton("fx Equation Assistant…")
        self.btn_fx.clicked.connect(self._edit_with_fx_assistant)
        btn_bar.addWidget(self.btn_fx)

        self.btn_remove = QPushButton("Remove")
        self.btn_remove.clicked.connect(self._remove_parameter)
        btn_bar.addWidget(self.btn_remove)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # Parameters Table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Value / Formula", "Resolved"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.verticalHeader().setMinimumSectionSize(20)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
        layout.addWidget(self.table)

        # Connect API listeners
        api.on_project_changed(self._on_project_changed)
        api.on_project_content_changed(self._on_project_content_changed)

    def _on_project_changed(self, project) -> None:
        self._refresh()

    def _on_project_content_changed(self, project) -> None:
        self._refresh()

    def _get_project_data(self) -> dict[str, Any] | None:
        if self._api.current_project is None:
            return None
        return self._api.current_project.data

    def _get_active_cfg_manager(self, data: dict[str, Any]) -> ConfigurationManager:
        proj = self._api.current_project
        if proj is not None and hasattr(proj, "get_configuration_manager"):
            getter = getattr(proj, "get_configuration_manager", None)
            if callable(getter):
                mgr = getter()
                if isinstance(mgr, ConfigurationManager):
                    return mgr
        return ConfigurationManager(data, self._resolver)

    def _format_resolved(self, res_val: Any, param_def: Any) -> str:
        """Format resolved value with its unit symbol from the active unit system."""
        if not isinstance(res_val, (float, int)) or isinstance(res_val, bool):
            return str(res_val)

        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()

        # Determine quantity from parameter definition
        quantity = ""
        if isinstance(param_def, dict):
            quantity = param_def.get("quantity") or ""

        if quantity:
            display_val = um.to_display(float(res_val), quantity)
            sym = um.get_unit_symbol(quantity)
            formatted = f"{display_val:.4g}"
            return f"{formatted} {sym}" if sym else formatted

        formatted = f"{res_val:.4g}"
        return formatted

    def _refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        try:
            data = self._get_project_data()
            if data is None:
                self.table.setRowCount(0)
                self.btn_add.setEnabled(False)
                self.btn_remove.setEnabled(False)
                return

            self.btn_add.setEnabled(True)
            self.btn_remove.setEnabled(True)

            raw_params: dict[str, Any] = data.setdefault("parameters", {})
            cfg_mgr = self._get_active_cfg_manager(data)
            try:
                resolved_params = cfg_mgr.get_effective_project_parameters()
            except Exception:
                resolved_params = {}

            self.table.setRowCount(len(raw_params))
            for row, (k, val) in enumerate(raw_params.items()):
                # Col 0: Key
                key_item = QTableWidgetItem(str(k))
                key_item.setData(Qt.ItemDataRole.UserRole, k)

                # Col 1: Formula / Raw Value
                if isinstance(val, dict) and "value" in val:
                    val_str = str(val.get("value", ""))
                else:
                    val_str = str(val) if val is not None else ""
                val_item = QTableWidgetItem(val_str)
                if self._resolver.evaluator.is_expression(val_str):
                    val_item.setToolTip("Formula expression")
                elif isinstance(val, dict):
                    q_info = val.get("quantity") or val.get("unit") or ""
                    if q_info:
                        val_item.setToolTip(f"Quantity: {q_info}")

                # Col 2: Resolved Value (with unit)
                res_val = resolved_params.get(k, "Error")
                if res_val is None or res_val == "Error":
                    res_str = "#REF!"
                    res_item = QTableWidgetItem(res_str)
                    res_item.setForeground(QColor(229, 57, 53))
                    res_item.setToolTip("Formula evaluation failed (#REF!)")
                else:
                    res_str = self._format_resolved(res_val, val)
                    res_item = QTableWidgetItem(res_str)
                res_item.setFlags(res_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                # Check if overridden in active config
                if cfg_mgr.is_overridden(f"project.parameters.{k}"):
                    res_item.setText(f"{res_str} ◆")
                    res_item.setToolTip("Overridden in active configuration")

                self.table.setItem(row, 0, key_item)
                self.table.setItem(row, 1, val_item)
                self.table.setItem(row, 2, res_item)
        finally:
            self._loading = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self._api.current_project is None:
            return

        row = item.row()
        data = self._get_project_data()
        if not data:
            return

        raw_params: dict[str, Any] = data.setdefault("parameters", {})
        key_item = self.table.item(row, 0)
        val_item = self.table.item(row, 1)

        if not key_item or not val_item:
            return

        old_key = key_item.data(Qt.ItemDataRole.UserRole)
        new_key = key_item.text().strip()
        val_text = val_item.text().strip()

        # Parse numeric value if possible and not expression
        parsed_val: Any
        if self._resolver.evaluator.is_expression(val_text):
            parsed_val = val_text
        else:
            try:
                parsed_val = float(val_text) if "." in val_text else int(val_text)
            except ValueError:
                parsed_val = val_text

        existing_val = raw_params.get(old_key or new_key)
        if isinstance(existing_val, dict):
            target_val: Any = copy.deepcopy(existing_val)
            target_val["value"] = parsed_val
        else:
            target_val = parsed_val

        renamed_count = 0

        def _apply() -> None:
            nonlocal renamed_count
            if old_key and old_key != new_key and old_key in raw_params:
                del raw_params[old_key]
                from setuav_studio.model.expression import rename_symbol_in_project

                renamed_count = rename_symbol_in_project(data, old_key, new_key)
            if new_key:
                raw_params[new_key] = target_val

        desc = (
            f"Rename parameter '{old_key}' to '{new_key}'"
            if old_key and old_key != new_key
            else f"Edit parameter '{new_key}'"
        )
        self._api.edit_project(desc, _apply)
        if hasattr(self._api.current_project, "recompute_expressions"):
            self._api.current_project.recompute_expressions(self._api)

        if old_key and old_key != new_key:
            msg = f'Renamed parameter "{old_key}" to "{new_key}"'
            if renamed_count > 0:
                msg += f" (updated {renamed_count} dependent expression{'s' if renamed_count > 1 else ''})"
            self._api.show_status(msg, "success", 4000)

        self._refresh()

    def _add_parameter(self) -> None:
        data = self._get_project_data()
        if not data:
            return

        from PySide6.QtWidgets import QDialog

        from setuav_studio.ui.parameter.parameters_dialog import AddParameterDialog

        raw_params: dict[str, Any] = data.setdefault("parameters", {})
        dlg = AddParameterDialog(
            api=self._api,
            existing_names=set(raw_params.keys()),
            is_constant=False,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            param_name, param_val = dlg.get_data()

            def _apply() -> None:
                pdata = self._api.current_project.data if self._api.current_project else {}
                pdata.setdefault("parameters", {})[param_name] = param_val

            self._api.edit_project(f"Add parameter '{param_name}'", _apply)
            self._refresh()

    def _remove_parameter(self) -> None:
        data = self._get_project_data()
        if not data:
            return
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        key_item = self.table.item(row, 0)
        if not key_item:
            return
        param_name = key_item.text().strip()

        from setuav_studio.model.expression import find_symbol_usages_in_project

        usages = find_symbol_usages_in_project(data, param_name)
        if usages:
            usages_preview = "\n".join(f"• {loc}: {expr}" for loc, expr in usages[:5])
            if len(usages) > 5:
                usages_preview += f"\n... and {len(usages) - 5} more"
            reply = QMessageBox.warning(
                self,
                "Confirm Parameter Deletion",
                f"Parameter '{param_name}' is referenced in {len(usages)} expression(s):\n\n"
                f"{usages_preview}\n\n"
                f"Deleting this parameter will break these expressions (#REF!).\n"
                f"Are you sure you want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            reply = QMessageBox.question(
                self,
                "Remove Parameter",
                f"Are you sure you want to remove parameter '{param_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

        if reply == QMessageBox.StandardButton.Yes:
            raw_params: dict[str, Any] = data.setdefault("parameters", {})

            def _apply() -> None:
                raw_params.pop(param_name, None)

            self._api.edit_project(f"Remove parameter '{param_name}'", _apply)
            if hasattr(self._api.current_project, "recompute_expressions"):
                self._api.current_project.recompute_expressions(self._api)
            self._refresh()

    def _on_table_double_clicked(self, index) -> None:
        if index.column() == 1:
            self._edit_with_fx_assistant()

    def _edit_with_fx_assistant(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        key_item = self.table.item(row, 0)
        val_item = self.table.item(row, 1)
        if not key_item or not val_item:
            return

        param_name = key_item.text().strip()
        curr_val = val_item.text().strip()

        from setuav_studio.ui.parameter.expression_dialog import AdvancedExpressionDialog

        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=curr_val,
            title=f"Equation Assistant — {param_name}",
            is_boolean_constraint=False,
            parent=self,
        )
        from PySide6.QtWidgets import QDialog

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_expr = dlg.get_expression()
            data = self._get_project_data()
            if not data:
                return
            raw_params: dict[str, Any] = data.setdefault("parameters", {})

            parsed: Any
            if self._resolver.evaluator.is_expression(new_expr):
                parsed = new_expr
            else:
                try:
                    parsed = float(new_expr) if "." in new_expr else int(new_expr)
                except ValueError:
                    parsed = new_expr

            existing_val = raw_params.get(param_name)
            def _apply() -> None:
                if isinstance(existing_val, dict):
                    target_val: Any = copy.deepcopy(existing_val)
                    target_val["value"] = parsed
                else:
                    target_val = parsed
                raw_params[param_name] = target_val

            self._api.edit_project(f"Edit parameter '{param_name}'", _apply)
            self._refresh()
