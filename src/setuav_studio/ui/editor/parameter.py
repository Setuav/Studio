"""Properties panel editor for a selected Project Parameter / Constant styled as a property table."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api.events import StudioEvents
from setuav_studio.model.expression import (
    ExpressionEvaluator,
    normalize_equation_input,
    rewrite_project_expression_identifiers,
)
from setuav_studio.model.parameter import ParameterResolution, ParameterResolver
from setuav_studio.model.scope import build_project_base_scope
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


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
        self._param_key = str(param_item["key"])
        self._key_history: list[str] = [self._param_key]
        self._resolver = ParameterResolver()
        self._loading = False
        self._current_quantity: str = ""

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
        if self._api is not None:
            self._api.on_project_content_changed(self._on_project_content_changed)
            unsub = self._api.subscribe(
                StudioEvents.UNITS_CHANGED, self._on_project_content_changed
            )
            self.destroyed.connect(lambda *_: unsub())

    def _selection_payload(self, value: Any) -> dict[str, Any]:
        return {
            "kind": "parameter",
            "id": f"param_{self._param_key}",
            "key": self._param_key,
            "value": value,
        }

    def _on_project_content_changed(self, _payload: Any = None) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        params = data.get("parameters", {})
        if self._param_key in params:
            self._load_data()
            return
        for candidate in reversed(self._key_history):
            if candidate in params:
                self._param_key = candidate
                self._load_data()
                sel = self._api.current_selection
                if (
                    self._api is not None
                    and isinstance(sel, dict)
                    and sel.get("kind") == "parameter"
                    and sel.get("key") in self._key_history
                ):
                    self._api.set_selection(self._selection_payload(params.get(candidate)))
                return

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
                ("quantity", "Quantity"),
                ("unit", "Active Unit"),
                ("resolved", "Resolved Value"),
            ]
        )
        self.general_table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.general_table)

    def _get_project_data(self) -> dict[str, Any] | None:
        if self._api.project is None:
            return None
        return self._api.project.data

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
                self._current_quantity = str(curr_val.get("quantity") or "")
                if not self._current_quantity and curr_val.get("unit"):
                    from setuav_studio.units import get_quantity_for_unit

                    self._current_quantity = get_quantity_for_unit(str(curr_val["unit"])) or ""
            else:
                val_raw = curr_val
                self._current_quantity = ""

            from setuav_studio.units import get_quantity_choices, get_unit_manager

            um = get_unit_manager()
            self._set_property_value(self.general_table, "name", self._param_key)
            self._set_property_expression(
                self.general_table,
                "value",
                str(val_raw) if val_raw is not None else "",
                quantity=self._current_quantity or None,
                on_changed=self._on_value_expression_changed,
                on_open_assistant=self._open_assistant,
                raw_callback=True,
            )

            self._set_property_combo(
                self.general_table,
                "quantity",
                self._current_quantity,
                get_quantity_choices(),
                self._on_quantity_changed,
            )

            active_sym = (
                um.get_unit_symbol(self._current_quantity) if self._current_quantity else "—"
            )
            self._set_property_value(self.general_table, "unit", active_sym, editable=False)

            raw_params = data.get("parameters", {}) if isinstance(data, dict) else {}
            resolution = self._resolve_parameters(raw_params)
            error = self._parameter_error(resolution)
            res_val = resolution.values.get(self._param_key, "—")
            if error is not None:
                res_str = f"#ERR! {error}"
            elif isinstance(res_val, (int, float)) and not isinstance(res_val, bool):
                res_str = um.format_value(float(res_val), self._current_quantity or None, 2)
            else:
                res_str = str(res_val)

            self._set_property_value(self.general_table, "resolved", res_str, editable=False)
        finally:
            self._loading = False

    def _resolve_parameters(self, params: dict[str, Any]) -> ParameterResolution:
        data = self._get_project_data()
        base_scope = build_project_base_scope(data, api=self._api) if data is not None else None
        return self._resolver.resolve_all(params, base_scope=base_scope)

    def _validated_value(self, new_val: Any, raw_params: dict[str, Any]) -> Any:
        """Parse editor input and check that it resolves; raise ValueError otherwise."""
        if isinstance(new_val, bool):
            raise ValueError("Boolean value is not numeric")
        if isinstance(new_val, (int, float)):
            parsed: Any = new_val
            if not math.isfinite(float(parsed)):
                raise ValueError("Numeric value must be finite")
        else:
            parsed = str(new_val).strip()
            if not ExpressionEvaluator.is_expression(parsed):
                parsed = float(parsed)
                if not math.isfinite(parsed):
                    raise ValueError("Numeric value must be finite")
        error = self._parameter_error(
            self._resolve_parameters({**raw_params, self._param_key: parsed})
        )
        if error is not None:
            raise ValueError(error)
        return parsed

    def _parameter_error(self, resolution: ParameterResolution) -> str | None:
        """Return the resolution error message for this editor's parameter, if any."""
        path = f"parameters.{self._param_key}"
        return next((d["message"] for d in resolution.diagnostics if d["path"] == path), None)

    def _open_assistant(self, current_val: str) -> None:
        from PySide6.QtWidgets import QDialog

        from setuav_studio.ui.dialog.expression_dialog import AdvancedExpressionDialog

        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=current_val,
            title=f"Equation Assistant — {self._param_key}",
            is_boolean_constraint=False,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_expr = normalize_equation_input(dlg.get_expression())
            self._on_value_expression_changed(new_expr)
            self._load_data()

    def _on_value_expression_changed(self, new_val: Any) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        raw_params: dict[str, Any] = data.setdefault("parameters", {})
        cell = self._property_cell(self.general_table, "value")

        try:
            parsed = self._validated_value(new_val, raw_params)
        except ValueError as exc:
            msg = f"Invalid parameter value: {exc}"
            if cell is not None:
                cell.set_error(msg)
            if self._api is not None:
                self._api.show_status(msg, "error")
            return

        if cell is not None:
            cell.clear_error()

        curr_entry = raw_params.get(self._param_key)
        curr_val = curr_entry.get("value") if isinstance(curr_entry, dict) else curr_entry
        if curr_val == parsed:
            return

        if self._current_quantity:
            final_val: Any = {
                "value": parsed,
                "quantity": self._current_quantity,
            }
        else:
            final_val = parsed

        def _apply() -> None:
            raw_params[self._param_key] = final_val

        self._api.edit_project(f"Set parameter '{self._param_key}'", _apply)
        self._load_data()

    def _on_quantity_changed(self, new_quantity: str) -> None:
        if self._loading:
            return
        new_q = new_quantity.strip()

        data = self._get_project_data()
        if not data:
            return
        raw_params = data.setdefault("parameters", {})
        curr = raw_params.get(self._param_key, 0.0)
        val = curr.get("value", curr) if isinstance(curr, dict) else curr

        def _apply() -> None:
            if new_q:
                raw_params[self._param_key] = {
                    "value": val,
                    "quantity": new_q,
                }
            else:
                raw_params[self._param_key] = val

        self._current_quantity = new_q
        self._api.edit_project(f"Change quantity of '{self._param_key}'", _apply)
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
            if not clean_name:
                if self._api is not None:
                    self._api.show_status("Parameter name cannot be empty.", "warning", 3000)
                self._load_data()
                return
            if clean_name != self._param_key:
                if clean_name in raw_params:
                    self._api.show_status(
                        f"Parameter '{clean_name}' already exists.", "warning", 3000
                    )
                    self._load_data()
                    return
                old_key = self._param_key
                if clean_name not in self._key_history:
                    self._key_history.append(clean_name)

                def _apply() -> None:
                    val = raw_params.pop(old_key, 0.0)
                    raw_params[clean_name] = val
                    rename_map = {
                        old_key: clean_name,
                        old_key.replace("-", "_"): clean_name.replace("-", "_"),
                    }
                    rewrite_project_expression_identifiers(data, rename_map)

                self._param_key = clean_name
                self._api.edit_project(f"Rename parameter '{old_key}' to '{clean_name}'", _apply)
                sel = self._api.current_selection
                if (
                    self._api is not None
                    and isinstance(sel, dict)
                    and sel.get("kind") == "parameter"
                    and sel.get("key") == old_key
                ):
                    self._api.set_selection(self._selection_payload(raw_params.get(clean_name)))
