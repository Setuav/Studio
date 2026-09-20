"""Properties panel editor for a selected Project Design Constraint styled as a property table."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.model.constraint import ConstraintChecker
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


class ConstraintExpressionCell(QWidget):
    """Expression editor widget for boolean constraints with direct text editing and fx assistant."""

    def __init__(
        self,
        initial_value: str = "",
        on_changed: Callable[[str], None] | None = None,
        on_open_assistant: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_changed = on_changed
        self._on_open_assistant = on_open_assistant
        self._committed_text = initial_value

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.line_edit = QLineEdit(self)
        self.line_edit.setText(initial_value)
        self.line_edit.editingFinished.connect(self._on_editing_finished)
        self.line_edit.returnPressed.connect(self.line_edit.clearFocus)
        layout.addWidget(self.line_edit, 1)

        self.fx_button = QPushButton("fx", self)
        self.fx_button.setToolTip("Open Constraint Assistant")
        self.fx_button.setFixedWidth(24)
        self.fx_button.setFixedHeight(20)
        self.fx_button.setStyleSheet(
            "QPushButton { font-style: italic; font-weight: bold; padding: 0px; font-size: 11px; }"
        )
        self.fx_button.clicked.connect(self._on_fx_clicked)
        layout.addWidget(self.fx_button)

    def _on_editing_finished(self) -> None:
        text = self.line_edit.text().strip()
        if text != self._committed_text:
            self._committed_text = text
            if self._on_changed:
                self._on_changed(text)

    def _on_fx_clicked(self) -> None:
        self._on_editing_finished()
        if self._on_open_assistant:
            self._on_open_assistant(self.line_edit.text().strip())

    def setText(self, text: str) -> None:
        self._committed_text = text
        if self.line_edit.text() != text:
            self.line_edit.setText(text)

    def text(self) -> str:
        return self.line_edit.text()


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
        layout = self._create_section("Constraint Details", "constraint")
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

            expr_row = 1
            for r in range(self.general_table.rowCount()):
                if self._property_key(self.general_table, r) == "expression":
                    expr_row = r
                    break

            existing_w = self.general_table.cellWidget(expr_row, 1)
            if isinstance(existing_w, ConstraintExpressionCell):
                existing_w.setText(c.get("expression", ""))
            else:
                cell = ConstraintExpressionCell(
                    initial_value=c.get("expression", ""),
                    on_changed=self._on_expression_changed,
                    on_open_assistant=self._open_assistant,
                    parent=self.general_table,
                )
                self.general_table.setCellWidget(expr_row, 1, cell)

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
            self._set_property_value(self.general_table, "description", c.get("description", ""))
        finally:
            self._loading = False

    def _open_assistant(self, current_val: str) -> None:
        from PySide6.QtWidgets import QDialog

        from setuav_studio.ui.dialog.expression_dialog import AdvancedExpressionDialog

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

    def _on_expression_changed(self, new_expr: str) -> None:
        if self._loading:
            return
        clean_expr = new_expr.strip()
        data = self._get_project_data()
        if not data:
            return
        constraints = data.setdefault("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c or c.get("expression") == clean_expr:
            return

        def _apply() -> None:
            c["expression"] = clean_expr

        self._api.edit_project(
            f"Edit constraint '{c.get('name') or self._cid}' expression",
            _apply,
        )
        self._load_data()

    def _on_severity_changed(self, new_sev: str) -> None:
        if self._loading:
            return
        data = self._get_project_data()
        if not data:
            return
        constraints = data.setdefault("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c or c.get("severity") == new_sev:
            return

        def _apply() -> None:
            c["severity"] = new_sev

        self._api.edit_project(
            f"Set constraint '{c.get('name') or self._cid}' severity to {new_sev}",
            _apply,
        )
        self._load_data()

    def _on_enabled_changed(self, val: str) -> None:
        if self._loading:
            return
        is_enabled = val == "true"
        data = self._get_project_data()
        if not data:
            return
        constraints = data.setdefault("constraints", [])
        c = next((item for item in constraints if item.get("id") == self._cid), None)
        if not c or c.get("enabled") == is_enabled:
            return

        def _apply() -> None:
            c["enabled"] = is_enabled

        self._api.edit_project(
            f"{'Enable' if is_enabled else 'Disable'} constraint '{c.get('name') or self._cid}'",
            _apply,
        )
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
            clean_name = val_text.strip()
            if clean_name and clean_name != c.get("name"):

                def _apply() -> None:
                    c["name"] = clean_name

                self._api.edit_project(f"Rename constraint to '{clean_name}'", _apply)
        elif key == "description":
            clean_desc = val_text.strip()
            if clean_desc != c.get("description"):

                def _apply() -> None:
                    c["description"] = clean_desc

                self._api.edit_project(
                    f"Edit constraint '{c.get('name') or self._cid}' description",
                    _apply,
                )
