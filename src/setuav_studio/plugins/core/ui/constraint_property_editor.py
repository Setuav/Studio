"""Properties panel editor for a selected Project Design Constraint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugins.core.constraints import ConstraintChecker
from setuav_studio.plugins.core.ui.expression_dialog import AdvancedExpressionDialog
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ConstraintPropertyEditor(QWidget):
    """Property editor widget displayed in Properties Panel when a Constraint is selected."""

    def __init__(
        self,
        api: StudioAPI,
        constraint_item: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._cid = str(constraint_item.get("id") or "")
        self._checker = ConstraintChecker()
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
        self._create_header("Constraint Properties", "fa6s.scale-balanced")

        # Form
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_field_changed)
        form.addRow("Name:", self.name_edit)

        expr_layout = QHBoxLayout()
        self.expr_edit = QLineEdit()
        self.expr_edit.textChanged.connect(self._on_field_changed)
        expr_layout.addWidget(self.expr_edit)

        self.btn_fx = QPushButton("fx")
        self.btn_fx.setToolTip("Open Constraint Expression Assistant")
        self.btn_fx.setFixedWidth(28)
        self.btn_fx.clicked.connect(self._open_assistant)
        expr_layout.addWidget(self.btn_fx)
        form.addRow("Expression:", expr_layout)

        self.sev_combo = QComboBox()
        self.sev_combo.addItems(["warning", "error", "info"])
        self.sev_combo.currentIndexChanged.connect(self._on_field_changed)
        form.addRow("Severity:", self.sev_combo)

        self.enabled_check = QCheckBox("Enable Constraint")
        self.enabled_check.toggled.connect(self._on_field_changed)
        form.addRow("", self.enabled_check)

        self.desc_edit = QTextEdit()
        self.desc_edit.setMaximumHeight(60)
        self.desc_edit.textChanged.connect(self._on_field_changed)
        form.addRow("Description:", self.desc_edit)

        self._content_layout.addLayout(form)

        # Live Status Box
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self._content_layout.addWidget(self.status_label)

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
        constraints = data.get("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c:
            return

        self._loading = True
        try:
            self.name_edit.setText(c.get("name", ""))
            self.expr_edit.setText(c.get("expression", ""))
            sev = c.get("severity", "warning")
            idx = self.sev_combo.findText(sev)
            if idx >= 0:
                self.sev_combo.setCurrentIndex(idx)
            self.enabled_check.setChecked(c.get("enabled", True))
            self.desc_edit.setPlainText(c.get("description", ""))

            # Evaluate status
            res = self._checker.check_constraint(c, data)
            if not c.get("enabled", True):
                self.status_label.setText("⚪ <b>Status:</b> Disabled")
            elif res.error:
                self.status_label.setText(
                    f"<span style='color: {status_color('error')}'>❌ <b>Error:</b> {res.error}</span>"
                )
            elif res.passed:
                self.status_label.setText(
                    f"<span style='color: {status_color('success')}'>✔ <b>Passed:</b> Satisfied</span>"
                )
            else:
                self.status_label.setText(
                    f"<span style='color: {status_color('warning')}'>⚠ <b>Violated:</b> Condition evaluated to False</span>"
                )
        finally:
            self._loading = False

    def _open_assistant(self) -> None:
        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=self.expr_edit.text(),
            title=f"Constraint Assistant — {self.name_edit.text()}",
            is_boolean_constraint=True,
            parent=self,
        )
        from PySide6.QtWidgets import QDialog

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.expr_edit.setText(dlg.get_expression())

    def _on_field_changed(self) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        constraints = data.setdefault("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c:
            return

        c["name"] = self.name_edit.text().strip()
        c["expression"] = self.expr_edit.text().strip()
        c["severity"] = self.sev_combo.currentText()
        c["enabled"] = self.enabled_check.isChecked()
        c["description"] = self.desc_edit.toPlainText().strip()

        self._api.notify_project_content_changed()
        self._load_data()
