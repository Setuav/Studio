"""Properties panel editor for a selected Project Parameter / Constant styled as a property table."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugins.core.configurations import ConfigurationManager
from setuav_studio.plugins.core.parameters import ParameterResolver
from setuav_studio.plugins.core.ui.expression_dialog import AdvancedExpressionDialog
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.property_tables import PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ParameterPropertyEditor(PropertyTableMixin, QWidget):
    """Reusable property editor for project constants and parameters matching the application style."""

    def __init__(
        self,
        api: StudioAPI,
        param_item: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._param_key = str(param_item.get("key") or param_item.get("id") or "")
        self._resolver = ParameterResolver()
        self._loading = False
        self._current_unit: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_general_section()
        self._content_layout.addStretch()
        self._load_data()

    def _create_section(
        self,
        title: str,
        icon_name: str | None = None,
        action_widget: QWidget | None = None,
    ) -> QVBoxLayout:
        section = QWidget()
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
        layout = self._create_section("Parameter Details", "constant")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("value", "Value / Formula"),
                ("resolved", "Resolved Value"),
                ("unit", "Unit"),
            ]
        )
        self.general_table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.general_table)

    def _get_project_data(self) -> dict[str, Any] | None:
        if self._api.current_project is None:
            return None
        return self._api.current_project.data

    def _load_data(self) -> None:
        data = self._get_project_data()
        if not data:
            return
        self._loading = True
        try:
            raw_params: dict[str, Any] = data.get("parameters", {})
            curr_val = raw_params.get(self._param_key, "")
            if isinstance(curr_val, dict):
                val_raw = curr_val.get("value", "")
                self._current_unit = str(curr_val.get("unit", ""))
            else:
                val_raw = curr_val
                self._current_unit = ""

            self._set_property_value(self.general_table, "name", self._param_key)
            self._set_property_expression(
                self.general_table,
                "value",
                str(val_raw) if val_raw is not None else "",
                on_changed=self._on_value_expression_changed,
                on_open_assistant=self._open_assistant,
            )

            cfg_mgr = ConfigurationManager(data, self._resolver)
            res_str = "—"
            with contextlib.suppress(Exception):
                resolved = cfg_mgr.get_effective_project_parameters()
                res_val = resolved.get(self._param_key, "—")
                unit_suffix = f" {self._current_unit}" if self._current_unit else ""
                res_str = (
                    f"{res_val:.4g}{unit_suffix}"
                    if isinstance(res_val, (int, float))
                    else f"{res_val}{unit_suffix}"
                )

            self._set_property_value(self.general_table, "resolved", res_str, editable=False)
            self._set_property_value(self.general_table, "unit", self._current_unit)
        finally:
            self._loading = False

    def _open_assistant(self, current_val: str) -> None:
        from PySide6.QtWidgets import QDialog

        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=current_val,
            title=f"Equation Assistant — {self._param_key}",
            is_boolean_constraint=False,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_expr = dlg.get_expression()
            self._on_value_expression_changed(new_expr)
            self._load_data()

    def _on_value_expression_changed(self, new_val_str: str) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        raw_params: dict[str, Any] = data.setdefault("parameters", {})

        parsed: Any
        if self._resolver.evaluator.is_expression(new_val_str):
            parsed = new_val_str
        else:
            try:
                parsed = float(new_val_str) if "." in new_val_str else int(new_val_str)
            except ValueError:
                parsed = new_val_str

        final_val: Any = (
            {"value": parsed, "unit": self._current_unit} if self._current_unit else parsed
        )

        def _apply() -> None:
            raw_params[self._param_key] = final_val

        self._api.edit_project(f"Set parameter '{self._param_key}'", _apply)
        self._load_data()

    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_text = self._property_text(self.general_table, row)
        data = self._get_project_data()
        if not data:
            return

        raw_params: dict[str, Any] = data.setdefault("parameters", {})

        if key == "name":
            clean_name = val_text.strip()
            if clean_name and clean_name != self._param_key:
                val = raw_params.pop(self._param_key, 0.0)
                raw_params[clean_name] = val
                self._param_key = clean_name
                self._api.notify_project_content_changed()
        elif key == "unit":
            self._current_unit = val_text.strip()
            curr = raw_params.get(self._param_key, 0.0)
            val = curr.get("value", curr) if isinstance(curr, dict) else curr
            raw_params[self._param_key] = (
                {"value": val, "unit": self._current_unit} if self._current_unit else val
            )
            self._api.notify_project_content_changed()
            self._load_data()
