"""Dialogs for editing and managing project design constraints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugins.core.constraints import ConstraintChecker, ConstraintResult
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ConstraintEditDialog(QDialog):
    """Dialog for creating or editing a single design constraint rule."""

    def __init__(
        self,
        parent: QWidget | None = None,
        initial_data: dict[str, Any] | None = None,
        checker: ConstraintChecker | None = None,
        project_data: dict[str, Any] | None = None,
        api: StudioAPI | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Constraint" if initial_data else "New Constraint")
        self.resize(520, 360)

        self._api = api
        self._checker = checker or ConstraintChecker()
        self._project_data = project_data or {}
        self._initial = initial_data or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(self)
        self.name_edit.setText(self._initial.get("name", ""))
        self.name_edit.setPlaceholderText("e.g. Wing Loading Limit")
        form.addRow("Name:", self.name_edit)

        expr_layout = QHBoxLayout()
        self.expr_edit = QLineEdit(self)
        self.expr_edit.setText(self._initial.get("expression", ""))
        self.expr_edit.setPlaceholderText("e.g. mtow / 1000 / wing_area <= 50")
        self.expr_edit.textChanged.connect(self._test_expression)
        expr_layout.addWidget(self.expr_edit)

        self.btn_expr_fx = QPushButton("fx", self)
        self.btn_expr_fx.setToolTip("Open Equation / Expression Assistant")
        self.btn_expr_fx.setFixedWidth(32)
        self.btn_expr_fx.clicked.connect(self._open_expression_assistant)
        expr_layout.addWidget(self.btn_expr_fx)
        form.addRow("Expression:", expr_layout)

        self.severity_combo = QComboBox(self)
        self.severity_combo.addItems(["warning", "error", "info"])
        curr_sev = self._initial.get("severity", "warning")
        idx = self.severity_combo.findText(curr_sev)
        if idx >= 0:
            self.severity_combo.setCurrentIndex(idx)
        form.addRow("Severity:", self.severity_combo)

        self.message_edit = QLineEdit(self)
        self.message_edit.setText(self._initial.get("message", ""))
        self.message_edit.setPlaceholderText("Message when violated (optional)")
        form.addRow("Violation Message:", self.message_edit)

        self.desc_edit = QTextEdit(self)
        self.desc_edit.setPlainText(self._initial.get("description", ""))
        self.desc_edit.setPlaceholderText("Explanation / rationale for this constraint...")
        self.desc_edit.setMaximumHeight(80)
        form.addRow("Description:", self.desc_edit)

        self.enabled_check = QCheckBox("Enable constraint", self)
        self.enabled_check.setChecked(self._initial.get("enabled", True))
        form.addRow("", self.enabled_check)

        layout.addLayout(form)

        # Live Evaluation Result Label
        self.preview_label = QLabel(self)
        self.preview_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.preview_label)

        self._test_expression()

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _open_expression_assistant(self) -> None:
        if self._api is None:
            return
        from setuav_studio.plugins.core.ui.expression_dialog import AdvancedExpressionDialog

        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=self.expr_edit.text(),
            title="Constraint Expression Assistant",
            is_boolean_constraint=True,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.expr_edit.setText(dlg.get_expression())

    def _test_expression(self) -> None:
        expr = self.expr_edit.text().strip()
        if not expr:
            self.preview_label.setText("<i>Enter an expression to evaluate</i>")
            return

        mock_constraint = {
            "id": "preview",
            "name": "preview",
            "expression": expr,
            "enabled": True,
        }
        res = self._checker.check_constraint(mock_constraint, self._project_data)
        if res.error:
            self.preview_label.setText(
                f"<span style='color: {status_color('error')}'>❌ Error: {res.error}</span>"
            )
        elif res.passed:
            self.preview_label.setText(
                f"<span style='color: {status_color('success')}'>✔ Condition Passed</span>"
            )
        else:
            self.preview_label.setText(
                f"<span style='color: {status_color('warning')}'>⚠ Condition Violated (Evaluates to False)</span>"
            )

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        expr = self.expr_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Constraint name is required.")
            self.name_edit.setFocus()
            return
        if not expr:
            QMessageBox.warning(self, "Validation Error", "Expression is required.")
            self.expr_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict[str, Any]:
        cid = self._initial.get("id", "")
        if not cid:
            cid = self.name_edit.text().strip().lower().replace(" ", "_")
        return {
            "id": cid,
            "name": self.name_edit.text().strip(),
            "expression": self.expr_edit.text().strip(),
            "severity": self.severity_combo.currentText(),
            "message": self.message_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
            "enabled": self.enabled_check.isChecked(),
        }


class ManageConstraintsDialog(QDialog):
    """Dialog for viewing, adding, editing, and deleting project constraints."""

    def __init__(
        self,
        api: StudioAPI,
        checker: ConstraintChecker | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Design Constraints")
        self.resize(750, 420)

        self._api = api
        self._checker = checker or ConstraintChecker()

        layout = QVBoxLayout(self)

        # Table
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(
            ["Status", "Name", "Expression", "Severity", "Enabled"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self._on_edit)
        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Constraint…", self)
        self.btn_add.setIcon(get_icon("file_new"))
        self.btn_add.clicked.connect(self._on_add)
        btn_layout.addWidget(self.btn_add)

        self.btn_edit = QPushButton("Edit…", self)
        self.btn_edit.setIcon(get_icon("settings"))
        self.btn_edit.clicked.connect(self._on_edit)
        btn_layout.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Delete", self)
        self.btn_delete.setIcon(get_icon("delete"))
        self.btn_delete.clicked.connect(self._on_delete)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close", self)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        self._refresh_table()

    def _get_project_data(self) -> dict[str, Any]:
        return self._api.current_project.data if self._api.current_project else {}

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        project_data = self._get_project_data()
        constraints = project_data.get("constraints", [])
        if not isinstance(constraints, list):
            return

        results = self._checker.check_all(project_data)
        res_map: dict[str, ConstraintResult] = {r.id: r for r in results}

        for row, c in enumerate(constraints):
            if not isinstance(c, dict):
                continue
            cid = c.get("id", "")
            name = c.get("name", "")
            expr = c.get("expression", "")
            severity = c.get("severity", "warning")
            enabled = c.get("enabled", True)

            self.table.insertRow(row)

            # Status Icon/Text
            res = res_map.get(cid)
            if not enabled:
                status_text = "⚪ Disabled"
                color = "#888888"
            elif res and res.error:
                status_text = "❌ Error"
                color = status_color("error")
            elif res and not res.passed:
                status_text = "⚠ Violated"
                color = status_color("warning")
            else:
                status_text = "✔ Passed"
                color = status_color("success")

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(
                Qt.GlobalColor.white if color == "" else Qt.GlobalColor.yellow
            )
            status_item.setData(Qt.ItemDataRole.UserRole, cid)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            expr_item = QTableWidgetItem(expr)
            expr_item.setFlags(expr_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            sev_item = QTableWidgetItem(severity.capitalize())
            sev_item.setFlags(sev_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            en_item = QTableWidgetItem("Yes" if enabled else "No")
            en_item.setFlags(en_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row, 0, status_item)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, expr_item)
            self.table.setItem(row, 3, sev_item)
            self.table.setItem(row, 4, en_item)

        self.table.resizeRowsToContents()

    def _on_add(self) -> None:
        dlg = ConstraintEditDialog(
            self,
            checker=self._checker,
            project_data=self._get_project_data(),
            api=self._api,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()

            def _apply() -> None:
                pdata = self._get_project_data()
                constraints = pdata.setdefault("constraints", [])
                constraints.append(data)

            self._api.edit_project(f"Add constraint '{data['name']}'", _apply)
            self._refresh_table()

    def _on_edit(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        status_item = self.table.item(row, 0)
        if not status_item:
            return
        cid = status_item.data(Qt.ItemDataRole.UserRole)
        pdata = self._get_project_data()
        constraints = pdata.get("constraints", [])
        idx = next((i for i, c in enumerate(constraints) if c.get("id") == cid), None)
        if idx is None:
            return

        target_c = dict(constraints[idx])
        dlg = ConstraintEditDialog(
            self,
            initial_data=target_c,
            checker=self._checker,
            project_data=pdata,
            api=self._api,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_data()

            def _apply() -> None:
                constraints[idx] = updated

            self._api.edit_project(f"Edit constraint '{updated['name']}'", _apply)
            self._refresh_table()

    def _on_delete(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        status_item = self.table.item(row, 0)
        if not status_item:
            return
        cid = status_item.data(Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(
            self,
            "Delete Constraint",
            f"Are you sure you want to delete constraint '{cid}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:

            def _apply() -> None:
                pdata = self._get_project_data()
                constraints = pdata.get("constraints", [])
                pdata["constraints"] = [c for c in constraints if c.get("id") != cid]

            self._api.edit_project(f"Delete constraint '{cid}'", _apply)
            self._refresh_table()
