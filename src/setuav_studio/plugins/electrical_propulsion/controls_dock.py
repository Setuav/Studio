"""Propulsion Analysis Controls dock widget."""

from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import StudioAPI


class PropulsionControlsDock(QWidget):
    """Controls and configuration dock for Propulsion Analysis."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_system_section()
        self._create_conditions_section()
        self._create_actions_section()

        self._content_layout.addStretch()

        self._api.on_project_changed(lambda _p: self._refresh_assemblies())
        self._api.on_project_content_changed(lambda _p: self._refresh_assemblies())
        self._refresh_assemblies()

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = QWidget()
        header.setProperty("sectionHeader", True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 4, 0, 2)
        header_layout.setSpacing(6)

        if icon_name:
            icon_label = QLabel()
            pixmap = get_icon(icon_name).pixmap(14, 14)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_system_section(self) -> None:
        layout = self._create_section("System", "fa6s.bolt")
        self.assembly_table = self._property_table([
            ("assembly", "Assembly"),
        ])
        layout.addWidget(self.assembly_table)

    def _create_conditions_section(self) -> None:
        layout = self._create_section("Conditions", "fa6s.cloud")
        self.conditions_table = self._property_table([
            ("airspeed_min", "Min Airspeed (m/s)"),
            ("airspeed_max", "Max Airspeed (m/s)"),
            ("altitude", "Altitude (m)"),
            ("throttle", "Throttle (%)"),
        ])
        self._set_property_value(self.conditions_table, "airspeed_min", "0.0")
        self._set_property_value(self.conditions_table, "airspeed_max", "35.0")
        self._set_property_value(self.conditions_table, "altitude", "0.0")
        self._set_property_value(self.conditions_table, "throttle", "100")
        layout.addWidget(self.conditions_table)

    def _create_actions_section(self) -> None:
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 4, 0, 2)
        actions_layout.setSpacing(4)

        self.run_button = QPushButton("Run Analysis", self)
        self.run_button.setProperty("accent", True)
        self.run_button.setIcon(get_icon("fa6s.play"))
        actions_layout.addWidget(self.run_button)

        self._content_layout.addLayout(actions_layout)

    def _refresh_assemblies(self) -> None:
        proj = self._api.current_project
        if proj is None:
            self._set_property_value(self.assembly_table, "assembly", "No Project", editable=False)
            self.run_button.setEnabled(False)
            return

        assemblies = proj.data.get("assemblies", [])
        prop_assemblies = [
            a for a in assemblies
            if a.get("type") == "org.setuav.core:electric-propulsion-system"
        ]

        if not prop_assemblies:
            self._set_property_value(self.assembly_table, "assembly", "None", editable=False)
            self.run_button.setEnabled(False)
            return

        options = [
            (str(a.get("id")), str(a.get("name") or a.get("id")))
            for a in prop_assemblies
        ]
        self._set_property_combo(
            self.assembly_table,
            "assembly",
            options[0][0],
            options,
            lambda _val: None,
        )
        self.run_button.setEnabled(True)

    @classmethod
    def _property_table(
        cls,
        definitions: list[tuple[str, str]],
    ) -> QTableWidget:
        table = cls._table(["Property", "Value"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        cls._configure_property_table(table, definitions)
        return table

    @classmethod
    def _configure_property_table(
        cls,
        table: QTableWidget,
        definitions: list[tuple[str, str]],
    ) -> None:
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, 1)
            if widget is not None:
                table.removeCellWidget(row, 1)
                widget.deleteLater()
        table.clearContents()
        table.setRowCount(len(definitions))
        for row, (key, label) in enumerate(definitions):
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.ItemDataRole.UserRole, key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, label_item)
            table.setItem(row, 1, QTableWidgetItem())
        cls._fit_table_height(table, len(definitions))

    def _set_property_combo(
        self,
        table: QTableWidget,
        key: str,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Any,
    ) -> None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            self._set_table_combo(table, row, 1, value, options, on_changed)
            return

    @staticmethod
    def _set_table_combo(
        table: QTableWidget,
        row: int,
        column: int,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Any,
    ) -> None:
        item = table.item(row, column)
        if item is not None:
            item.setText("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        combo = QComboBox(table)
        combo.setProperty("tableEditor", True)
        combo.setFont(QApplication.font())
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        combo.view().setProperty("tableComboPopup", True)
        combo.view().setFont(QApplication.font())
        for option_value, label in options:
            combo.addItem(label, option_value)
        combo.setCurrentIndex(max(combo.findData(value), 0))
        combo.currentIndexChanged.connect(
            lambda _index, editor=combo, callback=on_changed: callback(
                str(editor.currentData())
            )
        )
        table.setCellWidget(row, column, combo)

    @staticmethod
    def _set_property_value(
        table: QTableWidget,
        key: str,
        value: object,
        *,
        editable: bool = True,
    ) -> None:
        for row in range(table.rowCount()):
            if PropulsionControlsDock._property_key(table, row) != key:
                continue
            item = table.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, 1, item)
            item.setText(str(value))
            if editable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return

    @staticmethod
    def _property_key(table: QTableWidget, row: int) -> str:
        item = table.item(row, 0)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setFixedHeight(23)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        return table

    @staticmethod
    def _fit_table_height(
        table: QTableWidget,
        row_count: int,
        maximum_visible_rows: int = 15,
    ) -> None:
        visible_rows = min(max(row_count, 1), maximum_visible_rows)
        height = (
            table.horizontalHeader().height()
            + table.verticalHeader().defaultSectionSize() * visible_rows
            + 2
        )
        table.setFixedHeight(height)
