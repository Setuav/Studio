"""Base reusable property editor and parameter descriptors for Setuav components."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import ParameterField
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import ExpressionPropertyCell, PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


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
        if self._fields:
            self._create_parameters_section()

        self._content_layout.addStretch()
        params = self._component.get("parameters", {})
        self._committed_params: dict[str, Any] = dict(params) if isinstance(params, dict) else {}
        exprs = params.get("_expressions") if isinstance(params, dict) else None
        self._committed_expressions: dict[str, str] = dict(exprs) if isinstance(exprs, dict) else {}
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
        layout = self._create_section("Parameters", "fa6s.sliders")
        defs: list[tuple[str, str]] = []
        for f in self._fields:
            defs.append((f.key, f.label))

        self.parameters_table = self._property_table(defs)
        self.parameters_table.cellChanged.connect(self._update_parameter_cell)
        layout.addWidget(self.parameters_table)

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
            params = self._component.get("parameters", {})
            mass_val = self._component.get("mass_expression") or self._component.get(
                "mass", params.get("mass", 0.0)
            )
            self._set_property_expression(
                self.general_table,
                "mass",
                mass_val,
                on_changed=self._on_mass_changed,
                label="Mass",
                unit="g",
            )

            # Load Parameters
            if hasattr(self, "parameters_table") and self._fields:
                self.bind_parametric_properties(
                    self.parameters_table,
                    params,
                    self._fields,
                    on_changed=self._on_param_changed,
                    api=self._api,
                )
            params = self._component.get("parameters", {})
            self._committed_params = dict(params) if isinstance(params, dict) else {}
            exprs = params.get("_expressions") if isinstance(params, dict) else None
            self._committed_expressions = dict(exprs) if isinstance(exprs, dict) else {}
        finally:
            self._loading = False

    def _on_param_changed(self, key: str, value: Any) -> None:
        if self._loading:
            return

        old_val = self._committed_params.get(key)
        old_expr = self._committed_expressions.get(key)

        p = self._component.setdefault("parameters", {})
        curr_exprs = p.get("_expressions")
        new_expr = curr_exprs.get(key) if isinstance(curr_exprs, dict) else None

        if old_val == value and old_expr == new_expr:
            return

        # Restore component parameters and expressions to committed state before edit_component
        # so edit_component accurately captures both value and formula diffs for undo/redo.
        if key in self._committed_params:
            p[key] = old_val
        else:
            p.pop(key, None)

        if old_expr is not None:
            p.setdefault("_expressions", {})[key] = old_expr
        elif "_expressions" in p and isinstance(p["_expressions"], dict):
            p["_expressions"].pop(key, None)
            if not p["_expressions"]:
                p.pop("_expressions", None)

        def apply_param() -> None:
            params = self._component.setdefault("parameters", {})
            params[key] = value
            if new_expr is not None:
                params.setdefault("_expressions", {})[key] = new_expr
            elif "_expressions" in params and isinstance(params["_expressions"], dict):
                params["_expressions"].pop(key, None)
                if not params["_expressions"]:
                    params.pop("_expressions", None)

            self._committed_params[key] = value
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
        curr_exprs = curr_params.get("_expressions") if isinstance(curr_params, dict) else None
        if curr_params != self._committed_params or curr_exprs != self._committed_expressions:
            self._load_component()
            self.update_viewport()

    def _on_expression_cell_changed(self, key: str, val_text: Any) -> None:
        self._on_param_changed(key, val_text)

    def _on_mass_changed(self, val_text: Any) -> None:
        if self._loading:
            return
        clean = val_text.strip() if isinstance(val_text, str) else str(val_text).strip()
        num_val: float | None = None
        new_expr: str | None = None
        if clean.startswith("=") or (
            clean and not clean.replace(".", "", 1).replace("-", "", 1).isdigit()
        ):
            new_expr = clean
            if self._api is not None and getattr(self._api, "current_project", None) is not None:
                try:
                    from setuav_studio.model.expression import ExpressionEvaluator

                    evaluator = ExpressionEvaluator()
                    project = self._api.current_project
                    scope = project.get_scope(api=self._api) if project is not None else {}
                    expr = clean.lstrip("=").strip()
                    res = evaluator.evaluate(expr, scope)
                    if isinstance(res, (int, float)):
                        num_val = float(res)
                except Exception:
                    pass
        else:
            with contextlib.suppress(ValueError):
                num_val = float(clean)

        def change() -> None:
            if num_val is not None:
                self._component["mass"] = num_val
                if "parameters" in self._component and isinstance(
                    self._component["parameters"], dict
                ):
                    self._component["parameters"]["mass"] = num_val
            if new_expr is not None:
                self._component["mass_expression"] = new_expr
            else:
                self._component.pop("mass_expression", None)

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
                if "parameters" in self._component and "mass" in self._component["parameters"]:
                    self._component["parameters"]["mass"] = num

        self._api.edit_component(
            self._component,
            f"Edit {key} of {self._component.get('name', 'component')}",
            apply_edit,
        )

    def _update_parameter_cell(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return

        item = self.parameters_table.item(row, column)
        if item is None or not item.text():
            return
        cell_widget = self.parameters_table.cellWidget(row, column)
        if isinstance(cell_widget, ExpressionPropertyCell):
            cell_widget.setValue(item.text())
        elif cell_widget is not None:
            set_text = getattr(cell_widget, "setText", None)
            if callable(set_text):
                set_text(item.text())
        else:
            key = self._property_key(self.parameters_table, row)
            self._on_param_changed(key, item.text())
