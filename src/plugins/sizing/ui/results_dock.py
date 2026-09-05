"""Sizing Results and Recommendations Dock Widget using Property Tables."""

from __future__ import annotations

import contextlib

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from plugins.sizing.engine.recommender import (
    MotorRecommendation,
    PropellerRecommendation,
    recommend_motors,
    recommend_propellers,
)
from plugins.sizing.engine.weight import SizingResult
from setuav_studio.ui.widget.button import set_button_role
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio.units import get_unit_manager
from setuav_studio_sdk import StudioAPI


class SizingResultsDock(PropertyTableMixin, QWidget):
    """Multi-tab sizing results dock featuring summary geometry, battery, and COTS recommendations."""

    table_headers = ("Metric", "Value")
    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False

    apply_to_project_requested = Signal(object)  # SizingResult

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sizing.results_widget")
        self._api = api
        self._current_result: SizingResult | None = None
        self._motor_recs: list[MotorRecommendation] = []
        self._prop_recs: list[PropellerRecommendation] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)

        # Tab 1: Sizing Summary & Geometry
        tab_summary = QWidget()
        summary_layout = QVBoxLayout(tab_summary)
        summary_layout.setContentsMargins(4, 4, 4, 4)
        summary_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.summary_table = self._property_table(
            [
                ("mtow", "Takeoff Gross Weight (MTOW)"),
                ("empty_mass", "Empty Airframe Mass"),
                ("payload_mass", "Payload Mass"),
                ("battery_mass", "Battery Pack Mass"),
                ("wing_area", "Wing Reference Area (S)"),
                ("wingspan", "Wingspan (b)"),
                ("mean_chord", "Mean Chord (MAC)"),
                ("wing_loading", "Design Wing Loading (W/S)"),
                ("power_loading", "Power Loading (P/W)"),
                ("max_power", "Max Shaft Power (P_max)"),
                ("cruise_power", "Cruise Power (P_cruise)"),
                ("cruise_ld", "Cruise L/D Efficiency"),
                ("max_ld", "Max Aerodynamic L/D"),
            ]
        )
        summary_layout.addWidget(self.summary_table)
        self.tabs.addTab(tab_summary, "Summary")

        # Tab 2: Battery & Energy Pack
        tab_battery = QWidget()
        bat_layout = QVBoxLayout(tab_battery)
        bat_layout.setContentsMargins(4, 4, 4, 4)
        bat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.battery_table = self._property_table(
            [
                ("pack_energy", "Total Pack Energy"),
                ("usable_energy", "Usable Energy (DoD)"),
                ("voltage", "Nominal Pack Voltage"),
                ("cells", "Cell Configuration"),
                ("capacity", "Battery Capacity"),
                ("peak_current", "Peak Discharge Current"),
                ("c_rate", "Discharge C-Rate"),
                ("c_status", "C-Rate Feasibility"),
            ]
        )
        bat_layout.addWidget(self.battery_table)
        self.tabs.addTab(tab_battery, "Battery")

        # Tab 3: COTS Propulsion Matching (PyThrust)
        tab_cots = QWidget()
        cots_layout = QVBoxLayout(tab_cots)
        cots_layout.setContentsMargins(4, 4, 4, 4)
        cots_layout.setSpacing(6)

        cots_layout.addWidget(QLabel("<b>Recommended Motors (PyThrust Catalog):</b>"))
        self.motor_table = QTableWidget(0, 5)
        self.motor_table.setHorizontalHeaderLabels(["Name", "KV", "Max Power", "Mass", "Match"])
        self.motor_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.motor_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        cots_layout.addWidget(self.motor_table)

        cots_layout.addWidget(QLabel("<b>Recommended Propellers (APC Catalog):</b>"))
        self.prop_table = QTableWidget(0, 4)
        self.prop_table.setHorizontalHeaderLabels(["Model", "Diameter", "Pitch", "Blades"])
        self.prop_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.prop_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        cots_layout.addWidget(self.prop_table)

        self.tabs.addTab(tab_cots, "Propulsion")

        layout.addWidget(self.tabs)

        # Bottom Action: Apply to Project
        action_bar = QWidget()
        act_layout = QHBoxLayout(action_bar)
        act_layout.setContentsMargins(0, 4, 0, 0)

        self.btn_apply = QPushButton("Apply to Project")
        set_button_role(self.btn_apply, "primary")
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        act_layout.addWidget(self.btn_apply)

        layout.addWidget(action_bar)

        get_unit_manager().units_changed.connect(self._on_units_changed)
        self.destroyed.connect(self._disconnect_units_changed)

    def _disconnect_units_changed(self) -> None:
        with contextlib.suppress(RuntimeError, TypeError):
            get_unit_manager().units_changed.disconnect(self._on_units_changed)

    def _on_units_changed(self) -> None:
        if self._current_result is not None:
            self.set_results(self._current_result)

    def set_results(self, result: SizingResult) -> None:
        """Populate all property tables with computed sizing solution in active units."""
        self._current_result = result
        w = result.weights
        b = result.battery
        um = get_unit_manager()

        # Mass formatting
        mass_sym = um.get_unit_symbol("mass")
        mass_dec = 3 if mass_sym in ("kg", "lb") else 1

        disp_mtow = um.to_display(w.mtow_kg * 1000.0, "mass")
        disp_empty = um.to_display(w.empty_mass_kg * 1000.0, "mass")
        disp_payload = um.to_display(w.payload_mass_kg * 1000.0, "mass")
        disp_bat = um.to_display(w.battery_mass_kg * 1000.0, "mass")

        # Dimensions formatting
        len_sym = um.get_unit_symbol("length")
        len_dec = 3 if len_sym in ("m", "ft") else 1

        disp_span = um.to_display(result.wingspan_m * 1000.0, "length")
        disp_mac = um.to_display(result.mean_chord_m * 1000.0, "length")

        # Area formatting
        area_sym = um.get_unit_symbol("area")
        area_dec = 4 if area_sym in ("m²", "m2", "ft²", "ft2") else 2
        disp_area = um.to_display(result.wing_area_m2 * 100.0, "area")

        # Wing loading formatting
        wl_g_dm2 = (w.mtow_kg * 1000.0) / (result.wing_area_m2 * 100.0)
        disp_wl, wl_sym = um.get_wing_loading_display(wl_g_dm2)

        # Power formatting
        pwr_sym = um.get_unit_symbol("power")
        pwr_dec = 2 if pwr_sym in ("kW", "hp") else 0
        disp_pmax = um.to_display(result.max_shaft_power_w, "power")
        disp_pcruise = um.to_display(result.cruise_shaft_power_w, "power")

        # Summary Tab
        self._set_property_value(self.summary_table, "mtow", f"{disp_mtow:.{mass_dec}f} {mass_sym}")
        self._set_property_value(self.summary_table, "empty_mass", f"{disp_empty:.{mass_dec}f} {mass_sym}")
        self._set_property_value(self.summary_table, "payload_mass", f"{disp_payload:.{mass_dec}f} {mass_sym}")
        self._set_property_value(self.summary_table, "battery_mass", f"{disp_bat:.{mass_dec}f} {mass_sym}")
        self._set_property_value(self.summary_table, "wing_area", f"{disp_area:.{area_dec}f} {area_sym}")
        self._set_property_value(self.summary_table, "wingspan", f"{disp_span:.{len_dec}f} {len_sym}")
        self._set_property_value(self.summary_table, "mean_chord", f"{disp_mac:.{len_dec}f} {len_sym}")
        self._set_property_value(self.summary_table, "wing_loading", f"{disp_wl:.1f} {wl_sym}")
        self._set_property_value(self.summary_table, "power_loading", f"{result.power_loading_wn:.1f} W/N")
        self._set_property_value(self.summary_table, "max_power", f"{disp_pmax:.{pwr_dec}f} {pwr_sym}")
        self._set_property_value(self.summary_table, "cruise_power", f"{disp_pcruise:.{pwr_dec}f} {pwr_sym}")
        self._set_property_value(self.summary_table, "cruise_ld", f"{result.cruise_lift_to_drag:.1f}")
        self._set_property_value(self.summary_table, "max_ld", f"{result.max_lift_to_drag:.1f}")

        # Battery Tab
        v_sym = um.get_unit_symbol("voltage")
        disp_v = um.to_display(b.nominal_voltage_v, "voltage")
        cap_sym = um.get_unit_symbol("capacity")
        cap_dec = 2 if cap_sym == "Ah" else 0
        disp_cap = um.to_display(b.capacity_mah, "capacity")
        curr_sym = um.get_unit_symbol("current")
        disp_curr = um.to_display(b.max_continuous_current_a, "current")

        energy_sym = um.get_unit_symbol("energy")
        energy_dec = 2 if energy_sym in ("kWh", "MJ") else 1
        disp_pack_energy = um.to_display(b.energy_wh, "energy")
        disp_usable_energy = um.to_display(b.usable_energy_wh, "energy")

        self._set_property_value(
            self.battery_table, "pack_energy", f"{disp_pack_energy:.{energy_dec}f} {energy_sym}"
        )
        self._set_property_value(
            self.battery_table, "usable_energy", f"{disp_usable_energy:.{energy_dec}f} {energy_sym}"
        )
        self._set_property_value(self.battery_table, "voltage", f"{disp_v:.1f} {v_sym}")
        self._set_property_value(self.battery_table, "cells", f"{b.cell_count_s}S LiPo")
        self._set_property_value(self.battery_table, "capacity", f"{disp_cap:.{cap_dec}f} {cap_sym}")
        self._set_property_value(self.battery_table, "peak_current", f"{disp_curr:.1f} {curr_sym}")
        self._set_property_value(self.battery_table, "c_rate", f"{b.discharge_c_rate:.1f} C")
        c_status_str = "Feasible" if b.is_c_rate_feasible else "Warning: Exceeds C-Rating"
        self._set_property_value(self.battery_table, "c_status", c_status_str)

        # Recommendations Tab
        self._update_recommendations(result.max_shaft_power_w)

    def _update_recommendations(self, max_power_w: float) -> None:
        """Query PyThrust and display recommended components in active units."""
        um = get_unit_manager()
        pwr_sym = um.get_unit_symbol("power")
        mass_sym = um.get_unit_symbol("mass")
        mass_dec = 3 if mass_sym in ("kg", "lb") else 0
        pwr_dec = 1 if pwr_sym in ("kW", "hp") else 0

        self._motor_recs = recommend_motors(target_power_w=max_power_w, limit=5)
        self.motor_table.setRowCount(len(self._motor_recs))
        self.motor_table.setHorizontalHeaderLabels([
            "Name",
            "KV",
            f"Max ({pwr_sym})",
            f"Mass ({mass_sym})",
            "Match",
        ])
        for row, m in enumerate(self._motor_recs):
            p_disp = um.to_display(m.max_power_w, "power")
            m_disp = um.to_display(m.weight_g, "mass")
            self.motor_table.setItem(row, 0, QTableWidgetItem(f"{m.manufacturer} {m.name}"))
            self.motor_table.setItem(row, 1, QTableWidgetItem(f"{m.kv:.0f}"))
            self.motor_table.setItem(row, 2, QTableWidgetItem(f"{p_disp:.{pwr_dec}f} {pwr_sym}"))
            self.motor_table.setItem(row, 3, QTableWidgetItem(f"{m_disp:.{mass_dec}f} {mass_sym}"))
            match_pct = max(0, 100 - int(m.power_match_score * 100))
            self.motor_table.setItem(row, 4, QTableWidgetItem(f"{match_pct}%"))

        self._prop_recs = recommend_propellers(target_power_w=max_power_w, v_cruise_mps=18.0, limit=5)
        self.prop_table.setRowCount(len(self._prop_recs))
        for row, p in enumerate(self._prop_recs):
            self.prop_table.setItem(row, 0, QTableWidgetItem(p.model))
            self.prop_table.setItem(row, 1, QTableWidgetItem(f"{p.diameter_in:.1f}″"))
            self.prop_table.setItem(row, 2, QTableWidgetItem(f"{p.pitch_in:.1f}″"))
            self.prop_table.setItem(row, 3, QTableWidgetItem(str(p.blade_count)))

    def _on_apply_clicked(self) -> None:
        if self._current_result is None:
            QMessageBox.information(self, "Apply to Project", "No sizing result available to apply.")
            return

        um = get_unit_manager()
        mass_sym = um.get_unit_symbol("mass")
        mass_dec = 3 if mass_sym in ("kg", "lb") else 1
        disp_mtow = um.to_display(self._current_result.weights.mtow_kg * 1000.0, "mass")

        len_sym = um.get_unit_symbol("length")
        len_dec = 3 if len_sym in ("m", "ft") else 1
        disp_span = um.to_display(self._current_result.wingspan_m * 1000.0, "length")

        area_sym = um.get_unit_symbol("area")
        area_dec = 4 if area_sym in ("m²", "m2", "ft²", "ft2") else 2
        disp_area = um.to_display(self._current_result.wing_area_m2 * 100.0, "area")

        pwr_sym = um.get_unit_symbol("power")
        pwr_dec = 2 if pwr_sym in ("kW", "hp") else 0
        disp_pwr = um.to_display(self._current_result.max_shaft_power_w, "power")

        self.apply_to_project_requested.emit(self._current_result)
        QMessageBox.information(
            self,
            "Sizing Applied",
            f"Preliminary sizing applied successfully:\n"
            f"- MTOW: {disp_mtow:.{mass_dec}f} {mass_sym}\n"
            f"- Wing Area: {disp_area:.{area_dec}f} {area_sym}\n"
            f"- Wingspan: {disp_span:.{len_dec}f} {len_sym}\n"
            f"- Max Power: {disp_pwr:.{pwr_dec}f} {pwr_sym}\n"
            f"- Battery: {self._current_result.battery.capacity_mah:.0f} mAh ({self._current_result.battery.cell_count_s}S)",
        )


__all__ = ["SizingResultsDock"]
