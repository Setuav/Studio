"""Dialogs for creating, editing, and managing project configurations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
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
    from setuav_studio.model.configuration import ConfigurationManager
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
        self.resize(380, 200)

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

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

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
        }


class ManageConfigurationsDialog(QDialog):
    """Dialog to list, add, edit, and delete project configurations."""

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
        self.resize(560, 340)

        layout = QVBoxLayout(self)

        # Table of configurations
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tag", "Name", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(True)
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

            desc_item = QTableWidgetItem(cfg.get("description", ""))
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row, 0, tag_item)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, desc_item)

        self.table.resizeRowsToContents()
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
        has_selection = len(self.table.selectionModel().selectedRows()) > 0
        self.btn_edit.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)

    def _create_new(self) -> None:
        dlg = ConfigurationEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.manager.create_configuration(**data)
            self._refresh_table()
            self.api.notify_project_content_changed()

    def _edit_selected(self) -> None:
        cid = self._selected_config_id()
        if not cid:
            return
        cfg = self.manager.get_configuration(cid)
        if not cfg:
            return
        dlg = ConfigurationEditDialog(self, config=cfg)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.manager.update_configuration(cid, **data)
            self._refresh_table()
            self.api.notify_project_content_changed()

    def _delete_selected(self) -> None:
        cid = self._selected_config_id()
        if not cid:
            return
        cfg = self.manager.get_configuration(cid)
        name = cfg.get("name", cid) if cfg else cid

        ans = QMessageBox.question(
            self,
            "Delete Configuration",
            f"Are you sure you want to delete configuration '{name}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.manager.delete_configuration(cid)
            self._refresh_table()
            self.api.notify_project_content_changed()
