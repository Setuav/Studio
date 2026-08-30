"""Propulsion Analysis Results dock widget."""

import csv
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.buttons import refresh_button_role, set_native_button
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.property_tables import ContentFitTableWidget, PropertyTableMixin
from setuav_studio.ui.theme import tokens
from setuav_studio_sdk import StudioAPI


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
        self._last_data: dict[str, Any] | None = None

        if self._api is not None:
            self._api.subscribe("propulsion.results_updated", self.set_results)

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

        self.summary_table = self._property_table(
            [
                ("static_thrust", "Static Thrust"),
                ("peak_power", "Peak Electrical Power"),
                ("peak_current", "Peak Current"),
                ("max_rpm", "Max Motor Speed"),
                ("cruise_thrust", "Cruise Thrust"),
                ("cruise_efficiency", "Cruise Efficiency"),
                ("endurance", "Est. Flight Endurance"),
            ]
        )
        summary_layout.addWidget(self.summary_table)
        summary_layout.addStretch(1)

        self.tabs.addTab(summary_tab, get_icon("fa6s.chart-simple"), "Summary")

        # Tab 2: Detailed Sweep Table (Styled like Aero Polar Table)
        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        detail_layout.setSpacing(4)

        self.detail_table = self._create_detail_table()
        detail_layout.addWidget(self.detail_table)

        self.tabs.addTab(detail_tab, get_icon("fa6s.table"), "Detailed Table")

        layout.addWidget(self.tabs, 1)

        # Bottom Bar with Export CSV Button (Bottom-Right)
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 2, 4, 2)
        bottom_bar.addStretch(1)

        self.btn_export_csv = QPushButton(" Export CSV", self)
        set_native_button(self.btn_export_csv, "export_csv")
        self.btn_export_csv.setToolTip("Export propulsion summary and detailed sweep table to CSV")
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_csv.setEnabled(False)
        bottom_bar.addWidget(self.btn_export_csv)

        layout.addLayout(bottom_bar)
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
        table = ContentFitTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(20)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setTextElideMode(Qt.TextElideMode.ElideNone)
        table.setWordWrap(False)
        table.setAlternatingRowColors(True)
        font = QFont(table.font().family())
        font.setPointSizeF(8.5)
        table.setFont(font)
        return table

    def set_results(self, data: dict[str, Any]) -> None:
        self._update_summary(data)
        sweep_rows: list[dict[str, Any]] = data.get("sweep_table", [])
        self.detail_table.setRowCount(0)
        if not sweep_rows:
            return

        max_curr_limit = float(data.get("motor_max_current") or 9999.0)
        self.detail_table.setRowCount(len(sweep_rows))
        best_eff_idx = self._best_efficiency_row(sweep_rows)
        for r_idx, row in enumerate(sweep_rows):
            self._populate_detail_row(r_idx, row, best_eff_idx, max_curr_limit)

        self.detail_table.fit_columns_to_viewport()
        self._last_data = data
        if hasattr(self, "btn_export_csv"):
            self.btn_export_csv.setEnabled(bool(sweep_rows))

        from setuav_studio.units import get_unit_manager

        get_unit_manager().units_changed.connect(self._on_units_changed)

    def _on_units_changed(self) -> None:
        if self._last_data is not None:
            self.set_results(self._last_data)

    def _update_summary(self, data: dict[str, Any]) -> None:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        force_sym = um.get_unit_symbol("force")
        power_sym = um.get_unit_symbol("power")
        current_sym = um.get_unit_symbol("current")

        if "static_thrust" in data:
            st = um.to_display(float(data["static_thrust"]), "force")
            self._set_property_value(self.summary_table, "static_thrust", f"{st:.2f} {force_sym}")
        if "peak_power" in data:
            pp = um.to_display(float(data["peak_power"]), "power")
            self._set_property_value(self.summary_table, "peak_power", f"{pp:.1f} {power_sym}")
        if "peak_current" in data:
            pc = um.to_display(float(data["peak_current"]), "current")
            self._set_property_value(self.summary_table, "peak_current", f"{pc:.1f} {current_sym}")
        if "max_rpm" in data:
            self._set_property_value(self.summary_table, "max_rpm", f"{float(data['max_rpm']):.0f} RPM")
        if "cruise_thrust" in data:
            ct = um.to_display(float(data["cruise_thrust"]), "force")
            self._set_property_value(self.summary_table, "cruise_thrust", f"{ct:.2f} {force_sym}")
        if "cruise_efficiency" in data:
            self._set_property_value(self.summary_table, "cruise_efficiency", f"{float(data['cruise_efficiency']) * 100:.1f} %")
        if "endurance_min" in data:
            self._set_property_value(self.summary_table, "endurance", f"{float(data['endurance_min']):.1f} min")

    @staticmethod
    def _best_efficiency_row(rows: list[dict[str, Any]]) -> int:
        return max(range(len(rows)), key=lambda index: float(rows[index].get("eta_sys", 0.0)))

    def _populate_detail_row(
        self,
        row_index: int,
        row: dict[str, Any],
        best_efficiency_index: int,
        max_current: float,
    ) -> None:
        current = float(row.get("current", 0.0))
        is_best = row_index == best_efficiency_index
        is_overcurrent = current > max_current or not bool(row.get("feasible", True))
        over_fg, best_fg, safe_fg = self._detail_colors()
        values = self._detail_values(row, is_best, is_overcurrent)

        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if column == 4 and is_overcurrent:
                item.setForeground(QBrush(over_fg))
            elif column == 5 and is_best:
                item.setForeground(QBrush(best_fg))
            elif column == 9:
                item.setForeground(QBrush(over_fg if is_overcurrent else safe_fg))
            self.detail_table.setItem(row_index, column, item)

    @staticmethod
    def _detail_values(row: dict[str, Any], is_best: bool, is_overcurrent: bool) -> tuple[str, ...]:
        x_value = float(row.get("x_val", 0.0))
        is_throttle = "Throttle" in str(row.get("x_label", ""))
        operation = f"{x_value:.0f}%" if is_throttle else f"{x_value:.1f} m/s"
        efficiency = f"{float(row.get('eta_sys', 0.0)) * 100:.1f}%"
        return (
            operation,
            f"{float(row.get('rpm', 0.0)):,.0f}",
            f"{float(row.get('thrust', 0.0)):.2f}",
            f"{float(row.get('power', 0.0)):.1f}",
            f"{float(row.get('current', 0.0)):.1f}",
            f"★ {efficiency}" if is_best else efficiency,
            f"{float(row.get('eta_p', 0.0)) * 100:.1f}%",
            f"{float(row.get('eta_m', 0.0)) * 100:.1f}%",
            f"{float(row.get('j', 0.0)):.3f}",
            "⚠️ Overload" if is_overcurrent else "✓ Safe",
        )

    @staticmethod
    def _detail_colors() -> tuple[QColor, QColor, QColor]:
        from setuav_studio.ui.theme import is_light_theme

        if is_light_theme():
            return QColor("#cf222e"), QColor("#0e8a5b"), QColor("#1a7f37")
        return QColor("#f85149"), QColor("#4ec9b0"), QColor("#3fb950")

    def clear_results(self) -> None:
        self._last_data = None
        for key in [
            "static_thrust",
            "peak_power",
            "peak_current",
            "max_rpm",
            "cruise_thrust",
            "cruise_efficiency",
            "endurance",
        ]:
            self._set_property_value(self.summary_table, key, "-", editable=False)
        if hasattr(self, "detail_table"):
            self.detail_table.setRowCount(0)
        if hasattr(self, "btn_export_csv"):
            self.btn_export_csv.setEnabled(False)

    def _export_csv(self) -> None:
        if not self._last_data:
            return

        is_summary = self.tabs.currentIndex() == 0
        default_name = "propulsion_summary.csv" if is_summary else "propulsion_sweep.csv"
        dialog_title = (
            "Export Propulsion Summary to CSV"
            if is_summary
            else "Export Propulsion Sweep Table to CSV"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            dialog_title,
            default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                if is_summary:
                    writer.writerow(["Metric", "Value"])
                    for row in range(self.summary_table.rowCount()):
                        k_item = self.summary_table.item(row, 0)
                        v_item = self.summary_table.item(row, 1)
                        if k_item and v_item:
                            writer.writerow([k_item.text(), v_item.text()])
                else:
                    headers = [
                        "Operating_Point",
                        "RPM",
                        "Thrust_N",
                        "Power_W",
                        "Current_A",
                        "Total_Efficiency",
                        "Prop_Efficiency",
                        "Motor_Efficiency",
                        "Advance_Ratio_J",
                        "Status",
                    ]
                    writer.writerow(headers)
                    sweep_rows: list[dict[str, Any]] = self._last_data.get("sweep_table", [])
                    for row in sweep_rows:
                        x_val = row.get("x_val", "")
                        x_lbl = row.get("x_label", "")
                        unit = "%" if "Throttle" in x_lbl else "m/s"
                        op_text = f"{x_val:.1f} {unit}" if unit == "m/s" else f"{x_val:.0f}%"
                        writer.writerow(
                            [
                                op_text,
                                row.get("rpm", ""),
                                f"{row.get('thrust', 0.0):.4f}",
                                f"{row.get('power', 0.0):.2f}",
                                f"{row.get('current', 0.0):.3f}",
                                f"{row.get('eta_sys', 0.0):.4f}",
                                f"{row.get('eta_p', 0.0):.4f}",
                                f"{row.get('eta_m', 0.0):.4f}",
                                f"{row.get('j', 0.0):.4f}",
                                "Safe" if row.get("feasible", True) else "Overload",
                            ]
                        )

            self._api.show_status(f"Exported {default_name} to {file_path}", "success")
        except Exception as err:
            self._api.show_status(f"CSV Export failed: {err}", "error")

    def update_theme_style(self) -> None:
        self.tabs.setTabIcon(0, get_icon("fa6s.chart-simple"))
        self.tabs.setTabIcon(1, get_icon("fa6s.table"))
        if hasattr(self, "btn_export_csv"):
            refresh_button_role(self.btn_export_csv)
        if self._last_data is not None:
            self.set_results(self._last_data)
