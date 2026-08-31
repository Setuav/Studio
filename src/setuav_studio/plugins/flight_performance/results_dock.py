"""Flight Performance Analysis Results dock widget."""

from __future__ import annotations

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
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.buttons import set_native_button
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.property_tables import ContentFitTableWidget, PropertyTableMixin
from setuav_studio.ui.theme import status_color, tokens
from setuav_studio_sdk import StudioAPI

from .engine.models import FlightEnvelopeResult


class PerformanceResultsDock(PropertyTableMixin, QWidget):
    """2-Tab flight performance results dock featuring Summary and Detailed Sweep Tables."""

    table_headers = ("Metric", "Value")
    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("flight_performance.results_widget")
        self._api = api
        self._tokens = tokens()
        self._last_result: FlightEnvelopeResult | None = None

        if self._api is not None:
            self._api.subscribe("flight_performance.analysis_completed", self.set_results)

        from setuav_studio.units import get_unit_manager

        get_unit_manager().units_changed.connect(self._on_units_changed)
        self.destroyed.connect(self._disconnect_units_changed)

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
                ("stall_speed", "Stall Speed"),
                ("best_range_speed", "Best Range Speed"),
                ("best_endurance_speed", "Best Endurance Speed"),
                ("best_climb_speed", "Best Climb Speed"),
                ("max_level_speed", "Max Level Flight Speed"),
                ("max_ld", "Maximum L/D Ratio"),
                ("max_roc", "Max Rate of Climb"),
                ("best_climb_angle", "Best Climb Angle"),
                ("max_range", "Estimated Max Range"),
                ("max_endurance", "Estimated Max Endurance"),
                ("min_power", "Min Aerodynamic Power Required"),
                ("cruise_power", "Cruise Electrical Power"),
                ("cruise_current", "Cruise Current Draw"),
                ("cruise_throttle", "Cruise Throttle"),
                ("propulsion_status", "Propulsion Status"),
            ]
        )
        summary_layout.addWidget(self.summary_table)
        summary_layout.addStretch(1)

        self.tabs.addTab(summary_tab, get_icon("fa6s.chart-simple"), "Summary")

        # Tab 2: Detailed Sweep Table
        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        detail_layout.setSpacing(4)

        self.detail_table = self._create_detail_table()
        detail_layout.addWidget(self.detail_table)

        self.tabs.addTab(detail_tab, get_icon("fa6s.table"), "Detailed Table")

        layout.addWidget(self.tabs, 1)

        # Bottom Bar with Export CSV Button
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 2, 4, 2)
        bottom_bar.addStretch(1)

        self.btn_export_csv = QPushButton(" Export CSV", self)
        set_native_button(self.btn_export_csv, "export_csv")
        self.btn_export_csv.setToolTip("Export flight performance envelope results to CSV")
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_csv.setEnabled(False)
        bottom_bar.addWidget(self.btn_export_csv)

        layout.addLayout(bottom_bar)
        self.clear_results()

    def _disconnect_units_changed(self) -> None:
        try:
            from setuav_studio.units import get_unit_manager

            get_unit_manager().units_changed.disconnect(self._on_units_changed)
        except (RuntimeError, TypeError):
            pass

    def closeEvent(self, event: Any) -> None:
        self._disconnect_units_changed()
        if self._api is not None:
            self._api.unsubscribe("flight_performance.analysis_completed", self.set_results)
        super().closeEvent(event)

    def _on_units_changed(self) -> None:
        self.detail_table.setHorizontalHeaderLabels(self._detail_headers())
        if self._last_result is not None:
            self.set_results(self._last_result)

    @staticmethod
    def _detail_headers() -> list[str]:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        speed_sym = um.get_unit_symbol("velocity")
        power_sym = um.get_unit_symbol("power")
        force_sym = um.get_unit_symbol("force")
        curr_sym = um.get_unit_symbol("current")
        return [
            f"Airspeed ({speed_sym})" if speed_sym else "Airspeed",
            f"P_req ({power_sym})" if power_sym else "P_req",
            f"P_avail ({power_sym})" if power_sym else "P_avail",
            f"T_req ({force_sym})" if force_sym else "T_req",
            f"T_avail ({force_sym})" if force_sym else "T_avail",
            f"ROC ({speed_sym})" if speed_sym else "ROC",
            "γ (°)",
            f"P_elec ({power_sym})" if power_sym else "P_elec",
            f"Current ({curr_sym})" if curr_sym else "Current",
            "Throttle (%)",
            "Range (km)",
            "Endurance (h)",
        ]

    def _create_detail_table(self) -> ContentFitTableWidget:
        headers = self._detail_headers()
        table = ContentFitTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setTextElideMode(Qt.TextElideMode.ElideNone)
        table.setWordWrap(False)
        table.verticalHeader().setDefaultSectionSize(20)
        table.verticalHeader().setVisible(False)
        font = QFont(table.font().family())
        font.setPointSizeF(8.5)
        table.setFont(font)
        return table

    def clear_results(self) -> None:
        self._last_result = None
        for key in (
            "stall_speed",
            "best_range_speed",
            "best_endurance_speed",
            "best_climb_speed",
            "max_level_speed",
            "max_ld",
            "max_roc",
            "best_climb_angle",
            "max_range",
            "max_endurance",
            "min_power",
            "cruise_power",
            "cruise_current",
            "cruise_throttle",
            "propulsion_status",
        ):
            self._set_property_value(self.summary_table, key, "-")

        self.detail_table.setRowCount(0)
        self.btn_export_csv.setEnabled(False)

    def set_results(self, result_obj: FlightEnvelopeResult | dict[str, Any] | None) -> None:
        if result_obj is None:
            self.clear_results()
            return

        if isinstance(result_obj, dict):
            res = FlightEnvelopeResult.from_dict(result_obj)
        else:
            res = result_obj

        self._last_result = res
        self._populate_summary_metrics(res)
        self._populate_detail_table(res)

    def _populate_summary_metrics(self, res: FlightEnvelopeResult) -> None:
        opt = res.optimal_speeds
        met = res.metrics
        cru = res.cruise

        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        v_sym = um.get_unit_symbol("velocity")

        def _fmt_v(v_m_s: float) -> str:
            disp_v = um.to_display(v_m_s, "velocity")
            return f"{disp_v:.1f} {v_sym}"

        # Format Summary Metrics
        self._set_property_value(
            self.summary_table,
            "stall_speed",
            _fmt_v(met.stall_speed),
        )
        if res.propulsion_available:
            self._set_property_value(
                self.summary_table,
                "best_range_speed",
                _fmt_v(opt.best_range),
            )
            self._set_property_value(
                self.summary_table,
                "best_endurance_speed",
                _fmt_v(opt.best_endurance),
            )
            self._set_property_value(
                self.summary_table,
                "best_climb_speed",
                _fmt_v(opt.best_climb),
            )
            self._set_property_value(
                self.summary_table,
                "max_level_speed",
                _fmt_v(met.max_speed),
            )
        else:
            for key in (
                "best_range_speed",
                "best_endurance_speed",
                "best_climb_speed",
                "max_level_speed",
            ):
                self._set_property_value(self.summary_table, key, "N/A (no propulsion data)")
        self._set_property_value(self.summary_table, "max_ld", f"{met.max_ld_ratio:.2f}")
        if res.propulsion_available:
            self._set_property_value(
                self.summary_table,
                "max_roc",
                f"{_fmt_v(met.max_rate_of_climb)}",
            )
            self._set_property_value(
                self.summary_table, "best_climb_angle", f"{met.best_climb_angle_deg:.1f}°"
            )
            self._set_property_value(
                self.summary_table,
                "max_range",
                f"{met.max_range_km:.1f} km" if met.max_range_km > 0 else "N/A",
            )
        else:
            for key in ("max_roc", "best_climb_angle", "max_range"):
                self._set_property_value(self.summary_table, key, "N/A (no propulsion data)")

        self._update_endurance(res)

        p_sym = um.get_unit_symbol("power")
        i_sym = um.get_unit_symbol("current")
        disp_min_p = um.to_display(met.min_power_required, "power")
        disp_cru_p = um.to_display(cru.power, "power")
        disp_cru_i = um.to_display(cru.current, "current")

        self._set_property_value(
            self.summary_table,
            "min_power",
            f"{disp_min_p:.1f} {p_sym}" if p_sym else f"{disp_min_p:.1f}",
        )
        self._set_property_value(
            self.summary_table,
            "cruise_power",
            (f"{disp_cru_p:.1f} {p_sym}" if p_sym else f"{disp_cru_p:.1f}")
            if res.propulsion_available and cru.power > 0
            else "N/A",
        )
        self._set_property_value(
            self.summary_table,
            "cruise_current",
            (f"{disp_cru_i:.2f} {i_sym}" if i_sym else f"{disp_cru_i:.2f}")
            if res.propulsion_available and cru.current > 0
            else "N/A",
        )
        self._set_property_value(
            self.summary_table,
            "cruise_throttle",
            f"{cru.throttle:.0f} %" if res.propulsion_available and cru.throttle > 0 else "N/A",
        )
        self._update_propulsion_status(res)

    def _populate_detail_table(self, res: FlightEnvelopeResult) -> None:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        self.detail_table.setHorizontalHeaderLabels(self._detail_headers())

        c = res.curves
        n_rows = len(c.velocities)
        self.detail_table.setRowCount(n_rows)

        for row in range(n_rows):
            v_val = c.velocities[row]
            p_req = c.power_required[row] if row < len(c.power_required) else 0.0
            p_av = (
                c.power_available[row]
                if res.propulsion_available and row < len(c.power_available)
                else None
            )
            t_req = c.thrust_required[row] if row < len(c.thrust_required) else 0.0
            t_av = (
                c.thrust_available[row]
                if res.propulsion_available and row < len(c.thrust_available)
                else None
            )
            roc_v = (
                c.rate_of_climb[row]
                if res.propulsion_available and row < len(c.rate_of_climb)
                else None
            )
            gamma_v = (
                c.climb_angle_deg[row]
                if res.propulsion_available and row < len(c.climb_angle_deg)
                else None
            )
            p_el = (
                c.electrical_power[row]
                if res.propulsion_available and row < len(c.electrical_power)
                else None
            )
            i_el = (
                c.current_draw[row]
                if res.propulsion_available and row < len(c.current_draw)
                else None
            )
            thr = (
                c.throttle_pct[row]
                if res.propulsion_available and row < len(c.throttle_pct)
                else None
            )
            rng = c.range_km[row] if res.propulsion_available and row < len(c.range_km) else None
            end = (
                c.endurance_hours[row]
                if res.propulsion_available and row < len(c.endurance_hours)
                else None
            )
            feas = c.feasible[row] if row < len(c.feasible) else True

            disp_v = um.to_display(v_val, "velocity")
            disp_p_req = um.to_display(p_req, "power")
            disp_p_av = um.to_display(p_av, "power") if p_av is not None else None
            disp_t_req = um.to_display(t_req, "force")
            disp_t_av = um.to_display(t_av, "force") if t_av is not None else None
            disp_roc = um.to_display(roc_v, "velocity") if roc_v is not None else None
            disp_p_el = um.to_display(p_el, "power") if p_el is not None else None
            disp_i_el = um.to_display(i_el, "current") if i_el is not None else None

            vals = [
                f"{disp_v:.1f}",
                f"{disp_p_req:.1f}",
                f"{disp_p_av:.1f}" if disp_p_av is not None else "—",
                f"{disp_t_req:.2f}",
                f"{disp_t_av:.2f}" if disp_t_av is not None else "—",
                f"{disp_roc:.2f}" if disp_roc is not None else "—",
                f"{gamma_v:.1f}" if gamma_v is not None else "—",
                f"{disp_p_el:.1f}" if disp_p_el is not None else "—",
                f"{disp_i_el:.2f}" if disp_i_el is not None else "—",
                f"{thr:.0f}" if thr is not None else "—",
                f"{rng:.1f}" if rng is not None else "—",
                f"{end:.2f}" if end is not None else "—",
            ]

            for col, val_str in enumerate(vals):
                item = QTableWidgetItem(val_str)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if not feas:
                    item.setForeground(QBrush(QColor(status_color("error"))))
                self.detail_table.setItem(row, col, item)

        self.btn_export_csv.setEnabled(n_rows > 0)

    def _update_endurance(self, result: FlightEnvelopeResult) -> None:
        hours = result.metrics.max_endurance_hours
        if result.propulsion_available and hours > 0:
            minutes = int(hours * 60)
            value = f"{hours:.2f} h ({minutes // 60}h {minutes % 60}m)"
        else:
            value = "N/A"
        self._set_property_value(self.summary_table, "max_endurance", value)

    def _update_propulsion_status(self, result: FlightEnvelopeResult) -> None:
        if not result.propulsion_available:
            value = "Unavailable — aerodynamic-only"
        elif result.propulsion_feasible is False:
            value = "Available — no feasible operating point"
        else:
            value = "Available"
        self._set_property_value(self.summary_table, "propulsion_status", value)

    def _export_csv(self) -> None:
        if not self._last_result:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Flight Performance CSV",
            "flight_performance_envelope.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not filename:
            return

        res = self._last_result
        try:
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["# Setuav Studio Flight Performance Envelope Export"])
                writer.writerow(["Aircraft Mass (kg)", f"{res.mass_kg:.3f}"])
                writer.writerow(["Wing Area (m2)", f"{res.area_m2:.4f}"])
                writer.writerow(["Air Density (kg/m3)", f"{res.air_density:.4f}"])
                writer.writerow(["Stall Speed (m/s)", f"{res.metrics.stall_speed:.2f}"])
                writer.writerow(["Best Range Speed (m/s)", f"{res.optimal_speeds.best_range:.2f}"])
                writer.writerow(
                    ["Best Endurance Speed (m/s)", f"{res.optimal_speeds.best_endurance:.2f}"]
                )
                writer.writerow(["Best Climb Speed (m/s)", f"{res.optimal_speeds.best_climb:.2f}"])
                writer.writerow(["Max Speed (m/s)", f"{res.metrics.max_speed:.2f}"])
                writer.writerow(["Max ROC (m/s)", f"{res.metrics.max_rate_of_climb:.2f}"])
                writer.writerow(["Max Range (km)", f"{res.metrics.max_range_km:.2f}"])
                writer.writerow(["Max Endurance (hours)", f"{res.metrics.max_endurance_hours:.2f}"])
                writer.writerow([])

                headers = [
                    "Velocity_mps",
                    "Power_Required_W",
                    "Power_Available_W",
                    "Thrust_Required_N",
                    "Thrust_Available_N",
                    "Rate_of_Climb_mps",
                    "Climb_Angle_deg",
                    "Electrical_Power_W",
                    "Current_Draw_A",
                    "Throttle_pct",
                    "Range_km",
                    "Endurance_hours",
                    "Feasible",
                ]
                writer.writerow(headers)

                c = res.curves
                for r in range(len(c.velocities)):
                    propulsion_values = res.propulsion_available
                    writer.writerow(
                        [
                            f"{c.velocities[r]:.2f}",
                            f"{c.power_required[r]:.2f}" if r < len(c.power_required) else "",
                            f"{c.power_available[r]:.2f}"
                            if propulsion_values and r < len(c.power_available)
                            else "",
                            f"{c.thrust_required[r]:.3f}" if r < len(c.thrust_required) else "",
                            f"{c.thrust_available[r]:.3f}"
                            if propulsion_values and r < len(c.thrust_available)
                            else "",
                            f"{c.rate_of_climb[r]:.3f}"
                            if propulsion_values and r < len(c.rate_of_climb)
                            else "",
                            f"{c.climb_angle_deg[r]:.2f}"
                            if propulsion_values and r < len(c.climb_angle_deg)
                            else "",
                            f"{c.electrical_power[r]:.2f}"
                            if propulsion_values and r < len(c.electrical_power)
                            else "",
                            f"{c.current_draw[r]:.3f}"
                            if propulsion_values and r < len(c.current_draw)
                            else "",
                            f"{c.throttle_pct[r]:.1f}"
                            if propulsion_values and r < len(c.throttle_pct)
                            else "",
                            f"{c.range_km[r]:.2f}"
                            if propulsion_values and r < len(c.range_km)
                            else "",
                            f"{c.endurance_hours[r]:.3f}"
                            if propulsion_values and r < len(c.endurance_hours)
                            else "",
                            str(c.feasible[r]),
                        ]
                    )

            if self._api:
                self._api.show_status(f"Exported performance data to {filename}", "success", 4000)
        except Exception as exc:
            if self._api:
                self._api.show_status(f"Failed to export CSV: {exc}", "error", 6000)
