"""Dialog for adding/editing project parameters and constants with physical quantity selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.parameters.expression_dialog import AdvancedExpressionDialog
from setuav_studio.units import get_quantity_choices, get_unit_manager

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


import re

PARAMETER_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class AddParameterDialog(QDialog):
    """Dialog to create a new project constant or parameter with a quantity type selector."""

    def __init__(
        self,
        api: StudioAPI,
        existing_names: set[str] | None = None,
        is_constant: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._existing_names = existing_names or set()
        self._is_constant = is_constant

        title = "Add Constant" if is_constant else "Add Parameter"
        self.setWindowTitle(title)
        self.setWindowIcon(get_icon("constant" if is_constant else "settings"))
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 1. Parameter Name
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("e.g. wingspan, payload_mass, cruise_speed")
        form.addRow("Name:", self.name_edit)

        # 2. Value / Expression with fx button
        val_container = QWidget(self)
        val_layout = QHBoxLayout(val_container)
        val_layout.setContentsMargins(0, 0, 0, 0)
        val_layout.setSpacing(4)

        self.val_edit = QLineEdit(val_container)
        self.val_edit.setPlaceholderText("0.0 or formula starting with =")
        val_layout.addWidget(self.val_edit, 1)

        self.btn_fx = QPushButton("fx", val_container)
        self.btn_fx.setFixedWidth(26)
        self.btn_fx.setFixedHeight(22)
        self.btn_fx.setStyleSheet("QPushButton { font-style: italic; font-weight: bold; }")
        self.btn_fx.clicked.connect(self._open_fx_dialog)
        val_layout.addWidget(self.btn_fx)

        form.addRow("Value / Formula:", val_container)

        # 3. Quantity Combo (Büyüklük Türü)
        self.quantity_combo = QComboBox(self)
        for q_id, q_label in get_quantity_choices():
            self.quantity_combo.addItem(q_label, q_id)
        self.quantity_combo.currentIndexChanged.connect(self._on_quantity_changed)
        form.addRow("Quantity (Büyüklük):", self.quantity_combo)

        # 4. Unit Info Label
        self.unit_info_label = QLabel(self)
        self.unit_info_label.setStyleSheet("color: #f0f0f0; font-weight: bold;")
        form.addRow("Active Unit:", self.unit_info_label)
        self._on_quantity_changed()

        # 5. Description (Optional)
        self.desc_edit = QLineEdit(self)
        self.desc_edit.setPlaceholderText("Optional description")
        form.addRow("Description:", self.desc_edit)

        layout.addLayout(form)

        # Dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _on_quantity_changed(self) -> None:
        q_id = str(self.quantity_combo.currentData() or "")
        if not q_id:
            self.unit_info_label.setText("None (Dimensionless)")
        else:
            um = get_unit_manager()
            sym = um.get_unit_symbol(q_id)
            u_id = um.get_display_unit(q_id)
            self.unit_info_label.setText(f"{u_id} ({sym})")

    def _open_fx_dialog(self) -> None:
        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=self.val_edit.text().strip(),
            title="Formula Assistant",
            is_boolean_constraint=False,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.val_edit.setText(dlg.get_expression())

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Parameter name cannot be empty.")
            return
        if not PARAMETER_NAME_PATTERN.match(name):
            QMessageBox.warning(
                self,
                "Invalid Name",
                "Parameter name must start with a letter or underscore and contain only "
                "letters, digits, underscores, or hyphens (e.g. 'wing_span', 'v_cruise').",
            )
            return
        if name in self._existing_names:
            QMessageBox.warning(self, "Duplicate Name", f"Parameter '{name}' already exists.")
            return

        self.accept()

    def get_data(self) -> tuple[str, Any]:
        """Return (param_name, param_value_or_dict)."""
        name = self.name_edit.text().strip()
        val_str = self.val_edit.text().strip() or "0.0"
        q_id = str(self.quantity_combo.currentData() or "")

        parsed: Any
        if val_str.startswith("=") or not val_str.replace(".", "", 1).replace("-", "", 1).isdigit():
            parsed = val_str
        else:
            try:
                parsed = float(val_str) if "." in val_str else int(val_str)
            except ValueError:
                parsed = val_str

        desc = self.desc_edit.text().strip()
        if q_id or desc:
            um = get_unit_manager()
            stored_val = parsed
            if q_id and isinstance(parsed, (int, float)):
                stored_val = um.to_base(float(parsed), q_id)
            res_dict: dict[str, Any] = {"value": stored_val}
            if q_id:
                res_dict["quantity"] = q_id
                res_dict["unit"] = um.get_unit_symbol(q_id)
            if desc:
                res_dict["description"] = desc
            return name, res_dict
        return name, parsed
