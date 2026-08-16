"""Propulsion Analysis Results dock widget."""

from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import StudioAPI


class PropulsionResultsDock(QWidget):
    """Clean summary metrics and performance results dock for Propulsion Analysis."""

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

        self._create_summary_section()
        self._create_operating_point_section()

        self._content_layout.addStretch()
        self.clear_results()

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

    def _create_summary_section(self) -> None:
        layout = self._create_section("Summary Metrics", "fa6s.chart-simple")
        self.summary_table = self._property_table([
            ("static_thrust", "Static Thrust"),
            ("peak_power", "Peak Electrical Power"),
            ("peak_current", "Peak Current"),
            ("max_rpm", "Max Motor Speed"),
            ("cruise_thrust", "Cruise Thrust"),
            ("cruise_efficiency", "Cruise Efficiency"),
            ("endurance", "Est. Flight Endurance"),
        ])
        layout.addWidget(self.summary_table)

    def _create_operating_point_section(self) -> None:
        layout = self._create_section("Operating Point", "fa6s.gauge-high")
        self.operating_table = self._property_table([
            ("advance_ratio", "Advance Ratio (J)"),
            ("prop_efficiency", "Propeller Efficiency (ηp)"),
            ("motor_efficiency", "Motor Efficiency (ηm)"),
            ("voltage_loaded", "Battery Loaded Voltage"),
        ])
        layout.addWidget(self.operating_table)

    def set_results(self, data: dict[str, Any]) -> None:
        if "static_thrust" in data:
            self._set_property_value(self.summary_table, "static_thrust", f"{data['static_thrust']:.2f} N")
        if "peak_power" in data:
            self._set_property_value(self.summary_table, "peak_power", f"{data['peak_power']:.1f} W")
        if "peak_current" in data:
            self._set_property_value(self.summary_table, "peak_current", f"{data['peak_current']:.1f} A")
        if "max_rpm" in data:
            self._set_property_value(self.summary_table, "max_rpm", f"{data['max_rpm']:.0f} RPM")
        if "cruise_thrust" in data:
            self._set_property_value(self.summary_table, "cruise_thrust", f"{data['cruise_thrust']:.2f} N")
        if "cruise_efficiency" in data:
            self._set_property_value(self.summary_table, "cruise_efficiency", f"{data['cruise_efficiency'] * 100:.1f} %")
        if "endurance_min" in data:
            self._set_property_value(self.summary_table, "endurance", f"{data['endurance_min']:.1f} min")

        if "advance_ratio" in data:
            self._set_property_value(self.operating_table, "advance_ratio", f"{data['advance_ratio']:.3f}")
        if "prop_efficiency" in data:
            self._set_property_value(self.operating_table, "prop_efficiency", f"{data['prop_efficiency'] * 100:.1f} %")
        if "motor_efficiency" in data:
            self._set_property_value(self.operating_table, "motor_efficiency", f"{data['motor_efficiency'] * 100:.1f} %")
        if "voltage_loaded" in data:
            self._set_property_value(self.operating_table, "voltage_loaded", f"{data['voltage_loaded']:.2f} V")

    def clear_results(self) -> None:
        for key in ["static_thrust", "peak_power", "peak_current", "max_rpm", "cruise_thrust", "cruise_efficiency", "endurance"]:
            self._set_property_value(self.summary_table, key, "-", editable=False)
        for key in ["advance_ratio", "prop_efficiency", "motor_efficiency", "voltage_loaded"]:
            self._set_property_value(self.operating_table, key, "-", editable=False)

    @classmethod
    def _property_table(
        cls,
        definitions: list[tuple[str, str]],
    ) -> QTableWidget:
        table = cls._table(["Metric", "Value"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        cls._configure_property_table(table, definitions)
        return table

    @classmethod
    def _configure_property_table(
        cls,
        table: QTableWidget,
        definitions: list[tuple[str, str]],
    ) -> None:
        table.clearContents()
        table.setRowCount(len(definitions))
        for row, (key, label) in enumerate(definitions):
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.ItemDataRole.UserRole, key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, label_item)
            val_item = QTableWidgetItem("-")
            val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 1, val_item)
        cls._fit_table_height(table, len(definitions))

    @staticmethod
    def _set_property_value(
        table: QTableWidget,
        key: str,
        value: object,
        *,
        editable: bool = False,
    ) -> None:
        for row in range(table.rowCount()):
            if PropulsionResultsDock._property_key(table, row) != key:
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
