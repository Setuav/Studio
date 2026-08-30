"""Properties panel editor for a selected Project Design Constraint styled as a property table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugins.core.constraints import ConstraintChecker
from setuav_studio.plugins.core.ui.expression_dialog import AdvancedExpressionDialog
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.property_tables import PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ConstraintPropertyEditor(PropertyTableMixin, QWidget):
    """Reusable property editor for design constraints matching the application style."""

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
        layout = self._create_section("Constraint Details", "fa6s.scale-balanced")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("expression", "Expression"),
                ("severity", "Severity"),
                ("enabled", "Enabled"),
                ("status", "Status"),
                ("description", "Description"),
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
        constraints = data.get("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c:
            return

        self._loading = True
        try:
            self._set_property_value(self.general_table, "name", c.get("name", ""))
            self._set_property_expression(
                self.general_table,
                "expression",
                c.get("expression", ""),
                on_changed=self._on_expression_changed,
                on_open_assistant=self._open_assistant,
            )
            self._set_property_combo(
                self.general_table,
                "severity",
                c.get("severity", "warning"),
                [("warning", "Warning"), ("error", "Error"), ("info", "Info")],
                self._on_severity_changed,
            )
            self._set_property_combo(
                self.general_table,
                "enabled",
                "true" if c.get("enabled", True) else "false",
                [("true", "Yes"), ("false", "No")],
                self._on_enabled_changed,
            )

            # Evaluate status
            res = self._checker.check_constraint(c, data)
            if not c.get("enabled", True):
                status_text = "⚪ Disabled"
            elif res.error:
                status_text = f"❌ Error: {res.error}"
            elif res.passed:
                status_text = "✔ Passed"
            else:
                status_text = f"⚠ Violated: {res.message or 'Condition evaluated to False'}"

            self._set_property_value(self.general_table, "status", status_text, editable=False)
            self._set_property_value(
                self.general_table, "description", c.get("description", "")
            )
        finally:
            self._loading = False

    def _open_assistant(self, current_val: str) -> None:
        from PySide6.QtWidgets import QDialog

        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=current_val,
            title=f"Constraint Assistant — {self._cid}",
            is_boolean_constraint=True,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_expr = dlg.get_expression()
            self._on_expression_changed(new_expr)
            self._load_data()

    def _on_expression_changed(self, new_expr: str) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        constraints = data.setdefault("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c:
            return

        c["expression"] = new_expr.strip()
        self._api.notify_project_content_changed()

    def _on_severity_changed(self, new_sev: str) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        constraints = data.setdefault("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c:
            return

        c["severity"] = new_sev
        self._api.notify_project_content_changed()

    def _on_enabled_changed(self, val: str) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        constraints = data.setdefault("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c:
            return

        c["enabled"] = val == "true"
        self._api.notify_project_content_changed()
        self._load_data()

    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_text = self._property_text(self.general_table, row)
        data = self._get_project_data()
        if not data:
            return

        constraints = data.setdefault("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c:
            return

        if key == "name":
            c["name"] = val_text.strip()
            self._api.notify_project_content_changed()
        elif key == "description":
            c["description"] = val_text.strip()
            self._api.notify_project_content_changed()
