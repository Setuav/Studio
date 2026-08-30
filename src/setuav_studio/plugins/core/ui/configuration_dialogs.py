"""Dialogs for creating, editing, and managing project configurations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
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
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.plugins.core.configurations import ConfigurationManager
    from setuav_studio_sdk import StudioAPI


class ConfigurationEditDialog(QDialog):
    """Dialog to create or edit a single configuration."""

    def __init__(
        self,
        parent: QWidget | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Configuration" if config else "New Configuration")
        self.resize(420, 260)

        self._config = config or {}
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit(self._config.get("name", ""))
        self.name_edit.setPlaceholderText("e.g. Cruise Configuration")
        form.addRow("Name:", self.name_edit)

        self.tag_edit = QLineEdit(self._config.get("tag", ""))
        self.tag_edit.setPlaceholderText("e.g. CRZ")
        self.tag_edit.setMaxLength(6)
        form.addRow("Tag:", self.tag_edit)

        self.desc_edit = QLineEdit(self._config.get("description", ""))
        self.desc_edit.setPlaceholderText("Optional description")
        form.addRow("Description:", self.desc_edit)

        # Color picker
        color_layout = QHBoxLayout()
        self._color = self._config.get("color", "#2196F3")
        self.color_preview = QPushButton()
        self.color_preview.setFixedSize(28, 24)
        self._update_color_preview()
        self.color_preview.clicked.connect(self._pick_color)

        self.color_label = QLabel(self._color)
        color_layout.addWidget(self.color_preview)
        color_layout.addWidget(self.color_label)
        color_layout.addStretch()
        form.addRow("Color:", color_layout)

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _update_color_preview(self) -> None:
        self.color_preview.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #555; border-radius: 3px;"
        )

    def _pick_color(self) -> None:
        col = QColorDialog.getColor(QColor(self._color), self, "Select Configuration Color")
        if col.isValid():
            self._color = col.name()
            self.color_label.setText(self._color)
            self._update_color_preview()

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        tag = self.tag_edit.text().strip().upper()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a configuration name.")
            self.name_edit.setFocus()
            return
        if not tag:
            QMessageBox.warning(self, "Invalid Tag", "Please enter a short tag (1-6 letters).")
            self.tag_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict[str, Any]:
        return {
            "name": self.name_edit.text().strip(),
            "tag": self.tag_edit.text().strip().upper(),
            "description": self.desc_edit.text().strip(),
            "color": self._color,
        }


class ManageConfigurationsDialog(QDialog):
    """Dialog to list, add, edit, delete, and inspect configurations and their overrides."""

    def __init__(
        self,
        manager: ConfigurationManager,
        api: StudioAPI,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.api = api
        self.setWindowTitle("Manage Configurations")
        self.resize(650, 420)

        layout = QVBoxLayout(self)

        # Table of configurations
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Tag", "Name", "Color", "Overrides"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._update_button_states)
        self.table.itemDoubleClicked.connect(self._edit_selected)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_new = QPushButton(get_icon("file_new"), "New…")
        self.btn_new.clicked.connect(self._create_new)
        btn_layout.addWidget(self.btn_new)

        self.btn_edit = QPushButton("Edit…")
        self.btn_edit.clicked.connect(self._edit_selected)
        btn_layout.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)
        self._refresh_table()

    def _refresh_table(self) -> None:
        configs = self.manager.get_configurations()
        self.table.setRowCount(len(configs))
        for row, cfg in enumerate(configs):
            tag_item = QTableWidgetItem(cfg.get("tag", ""))
            tag_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tag_item.setFlags(tag_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            name_item = QTableWidgetItem(cfg.get("name", ""))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            color_item = QTableWidgetItem(cfg.get("color", ""))
            color_item.setFlags(color_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            overrides_count = len(cfg.get("parameter_overrides", {}))
            overrides_item = QTableWidgetItem(f"{overrides_count} parameter(s)")
            overrides_item.setFlags(overrides_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row, 0, tag_item)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, color_item)
            self.table.setItem(row, 3, overrides_item)

        self._update_button_states()

    def _selected_config_id(self) -> str | None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        configs = self.manager.get_configurations()
        if 0 <= row < len(configs):
            return configs[row].get("id")
        return None

    def _update_button_states(self) -> None:
        has_sel = self._selected_config_id() is not None
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _create_new(self) -> None:
        dlg = ConfigurationEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()

            def _apply() -> None:
                self.manager.create_configuration(**data)

            self.api.edit_project(f"Create configuration '{data['name']}'", _apply)
            self._refresh_table()

    def _edit_selected(self) -> None:
        cid = self._selected_config_id()
        if not cid:
            return
        cfg = self.manager.get_configuration(cid)
        if not cfg:
            return

        dlg = ConfigurationEditDialog(self, cfg)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()

            def _apply() -> None:
                self.manager.update_configuration(cid, **data)

            self.api.edit_project(f"Update configuration '{data['name']}'", _apply)
            self._refresh_table()

    def _delete_selected(self) -> None:
        cid = self._selected_config_id()
        if not cid:
            return
        cfg = self.manager.get_configuration(cid)
        name = cfg.get("name", cid) if cfg else cid

        reply = QMessageBox.question(
            self,
            "Delete Configuration",
            f"Are you sure you want to delete configuration '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:

            def _apply() -> None:
                self.manager.delete_configuration(cid)

            self.api.edit_project(f"Delete configuration '{name}'", _apply)
            self._refresh_table()
