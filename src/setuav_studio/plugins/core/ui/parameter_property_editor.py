"""Properties panel editor for a selected Project Parameter / Constant."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugins.core.configurations import ConfigurationManager
from setuav_studio.plugins.core.parameters import ParameterResolver
from setuav_studio.plugins.core.ui.expression_dialog import AdvancedExpressionDialog
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ParameterPropertyEditor(QWidget):
    """Property editor widget displayed in Properties Panel when a Parameter is selected."""

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

        # Section Header
        self._create_header("Parameter Properties", "fa6s.sliders")

        # Form
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit(self._param_key)
        self.name_edit.textChanged.connect(self._on_name_changed)
        form.addRow("Name:", self.name_edit)

        expr_layout = QHBoxLayout()
        self.val_edit = QLineEdit()
        self.val_edit.textChanged.connect(self._on_value_changed)
        expr_layout.addWidget(self.val_edit)

        self.btn_fx = QPushButton("fx")
        self.btn_fx.setToolTip("Open Equation / Expression Assistant")
        self.btn_fx.setFixedWidth(28)
        self.btn_fx.clicked.connect(self._open_assistant)
        expr_layout.addWidget(self.btn_fx)
        form.addRow("Value / Formula:", expr_layout)

        self.resolved_label = QLabel()
        self.resolved_label.setStyleSheet(f"color: {status_color('success')}; font-weight: bold;")
        form.addRow("Resolved Value:", self.resolved_label)

        self._content_layout.addLayout(form)
        self._content_layout.addStretch()

        self._load_data()

    def _create_header(self, title: str, icon_name: str) -> None:
        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(5)

        icon_label = QLabel()
        set_label_icon(icon_label, icon_name)
        icon_label.setFixedSize(14, 14)
        h_layout.addWidget(icon_label)

        title_label = QLabel(title)
        h_layout.addWidget(title_label)
        h_layout.addStretch()

        self._content_layout.addWidget(header)

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
            self.val_edit.setText(str(curr_val) if curr_val is not None else "")

            cfg_mgr = ConfigurationManager(data, self._resolver)
            with contextlib.suppress(Exception):
                resolved = cfg_mgr.get_effective_project_parameters()
                res_val = resolved.get(self._param_key, "—")
                val_str = f"{res_val:.4g}" if isinstance(res_val, (int, float)) else str(res_val)
                self.resolved_label.setText(val_str)
        finally:
            self._loading = False

    def _open_assistant(self) -> None:
        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=self.val_edit.text(),
            title=f"Equation Assistant — {self._param_key}",
            is_boolean_constraint=False,
            parent=self,
        )
        from PySide6.QtWidgets import QDialog

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.val_edit.setText(dlg.get_expression())

    def _on_name_changed(self, new_name: str) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        clean_name = new_name.strip()
        if not clean_name or clean_name == self._param_key:
            return

        raw_params: dict[str, Any] = data.setdefault("parameters", {})
        val = raw_params.pop(self._param_key, 0.0)
        raw_params[clean_name] = val
        self._param_key = clean_name
        self._api.notify_project_content_changed()

    def _on_value_changed(self, new_val_str: str) -> None:
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

        def _apply() -> None:
            raw_params[self._param_key] = parsed

        self._api.edit_project(f"Set parameter '{self._param_key}'", _apply)
        self._load_data()
