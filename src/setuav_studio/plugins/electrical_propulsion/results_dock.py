"""Propulsion Analysis Results dock widget."""

from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.theme import tokens

from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.property_tables import PropertyTableMixin


class PropulsionResultsDock(PropertyTableMixin, QWidget):
    """2-Tab propulsion analysis results dock featuring Summary and Detailed Sweep Tables."""

    table_headers = ("Metric", "Value")
    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("propulsion.results_widget")
        self._api = api
        self._tokens = tokens()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)

        # Tab 1: Summary Metrics
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(4, 4, 4, 4)
        summary_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        summary_layout.setSpacing(6)

        self.summary_table = self._property_table([
            ("static_thrust", "Static Thrust"),
            ("peak_power", "Peak Electrical Power"),
            ("peak_current", "Peak Current"),
            ("max_rpm", "Max Motor Speed"),
            ("cruise_thrust", "Cruise Thrust"),
            ("cruise_efficiency", "Cruise Efficiency"),
            ("endurance", "Est. Flight Endurance"),
        ])
        summary_layout.addWidget(self.summary_table)
        summary_layout.addStretch(1)

        self.tabs.addTab(summary_tab, get_icon("fa6s.chart-simple"), "Summary")

        # Tab 2: Detailed Sweep Table (Inspired by Setuav MotorDataTableWidget)
        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        detail_layout.setSpacing(4)

        self.detail_table = self._create_detail_table()
        detail_layout.addWidget(self.detail_table)

        self.tabs.addTab(detail_tab, get_icon("fa6s.table"), "Detailed Table")

        layout.addWidget(self.tabs)
        self.clear_results()

    def _create_detail_table(self) -> QTableWidget:
        headers = [
            "Operating Pt",
            "RPM",
            "Thrust (N)",
            "Power (W)",
            "Current (A)",
            "Total η",
            "Prop ηp",
            "Motor ηm",
            "Advance (J)",
            "Status",
        ]
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setFixedHeight(24)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self._tokens["elevated"]};
                alternate-background-color: {self._tokens["row_alt"]};
                gridline-color: {self._tokens["grid"]};
                font-size: 11.5px;
                border: 1px solid {self._tokens["border"]};
                border-radius: 4px;
            }}
            QHeaderView::section {{
                background-color: {self._tokens["surface_alt"]};
                color: #b0b0b0;
                padding: 4px 6px;
                border: none;
                border-bottom: 1px solid {self._tokens["border_strong"]};
                font-weight: 600;
                font-size: 11px;
            }}
        """)
        return table

    def set_results(self, data: dict[str, Any]) -> None:
        # 1. Update Summary Table
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

        # 2. Update Detailed Table
        sweep_rows: list[dict[str, Any]] = data.get("sweep_table", [])
        self.detail_table.setRowCount(0)
        if not sweep_rows:
            return

        max_curr_limit = float(data.get("motor_max_current") or 9999.0)
        self.detail_table.setRowCount(len(sweep_rows))

        # Find best efficiency index
        best_eff_idx = -1
        best_eff_val = -1.0
        for idx, row in enumerate(sweep_rows):
            eta_val = float(row.get("eta_sys", 0.0))
            if eta_val > best_eff_val:
                best_eff_val = eta_val
                best_eff_idx = idx

        for r_idx, row in enumerate(sweep_rows):
            x_val = row.get("x_val", 0.0)
            x_lbl = row.get("x_label", "")
            rpm = float(row.get("rpm", 0.0))
            thrust = float(row.get("thrust", 0.0))
            power = float(row.get("power", 0.0))
            curr = float(row.get("current", 0.0))
            eta_sys = float(row.get("eta_sys", 0.0))
            eta_p = float(row.get("eta_p", 0.0))
            eta_m = float(row.get("eta_m", 0.0))
            j_val = float(row.get("j", 0.0))
            feasible = bool(row.get("feasible", True))

            is_best_row = (r_idx == best_eff_idx)
            is_overcurrent = curr > max_curr_limit or not feasible

            # Col 0: Operating Point
            unit = "%" if "Throttle" in x_lbl else "m/s"
            op_text = f"{x_val:.1f} {unit}" if unit == "m/s" else f"{x_val:.0f}%"
            item_op = QTableWidgetItem(op_text)
            item_op.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(r_idx, 0, item_op)

            # Col 1: RPM
            item_rpm = QTableWidgetItem(f"{rpm:,.0f}")
            item_rpm.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(r_idx, 1, item_rpm)

            # Col 2: Thrust (N)
            item_thrust = QTableWidgetItem(f"{thrust:.2f}")
            item_thrust.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(r_idx, 2, item_thrust)

            # Col 3: Power (W)
            item_pwr = QTableWidgetItem(f"{power:.1f}")
            item_pwr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(r_idx, 3, item_pwr)

            # Col 4: Current (A)
            item_curr = QTableWidgetItem(f"{curr:.1f}")
            item_curr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_overcurrent:
                item_curr.setForeground(QBrush(QColor("#f85149")))
            self.detail_table.setItem(r_idx, 4, item_curr)

            # Col 5: Total Efficiency
            eff_str = f"{eta_sys * 100:.1f}%"
            if is_best_row:
                eff_str = f"★ {eff_str}"
            item_eff = QTableWidgetItem(eff_str)
            item_eff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_best_row:
                item_eff.setForeground(QBrush(QColor("#4ec9b0")))
            self.detail_table.setItem(r_idx, 5, item_eff)

            # Col 6: Prop Efficiency
            item_etap = QTableWidgetItem(f"{eta_p * 100:.1f}%")
            item_etap.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(r_idx, 6, item_etap)

            # Col 7: Motor Efficiency
            item_etam = QTableWidgetItem(f"{eta_m * 100:.1f}%")
            item_etam.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(r_idx, 7, item_etam)

            # Col 8: Advance Ratio (J)
            item_j = QTableWidgetItem(f"{j_val:.3f}")
            item_j.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(r_idx, 8, item_j)

            # Col 9: Status
            if is_overcurrent:
                status_item = QTableWidgetItem("⚠️ Overload")
                status_item.setForeground(QBrush(QColor("#f85149")))
            else:
                status_item = QTableWidgetItem("✓ Safe")
                status_item.setForeground(QBrush(QColor("#3fb950")))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(r_idx, 9, status_item)

            # Row background highlight
            if is_best_row and not is_overcurrent:
                bg = QBrush(QColor(25, 45, 35))
                for c in range(self.detail_table.columnCount()):
                    it = self.detail_table.item(r_idx, c)
                    if it:
                        it.setBackground(bg)
            elif is_overcurrent:
                bg = QBrush(QColor(40, 20, 22))
                for c in range(self.detail_table.columnCount()):
                    it = self.detail_table.item(r_idx, c)
                    if it:
                        it.setBackground(bg)

    def clear_results(self) -> None:
        for key in ["static_thrust", "peak_power", "peak_current", "max_rpm", "cruise_thrust", "cruise_efficiency", "endurance"]:
            self._set_property_value(self.summary_table, key, "-", editable=False)
        if hasattr(self, "detail_table"):
            self.detail_table.setRowCount(0)

