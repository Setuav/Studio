"""Propulsion Analysis Controls dock widget."""

from __future__ import annotations

import logging
import math
from typing import Any, Callable
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

from scipy.optimize import root_scalar

from pythrust.propellers.database import PropellerDataPoint, PropellerEntry, PropellerMetadata
from pythrust.propulsion.models.battery import BatterySpec
from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec
from pythrust.propulsion.models.system import SystemSpec
from pythrust.propulsion.solver import PropulsionSolver, evaluate_propulsion_state

from .database import get_propeller_database
from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import StudioAPI

logger = logging.getLogger(__name__)


class PropulsionControlsDock(QWidget):
    """Clean controls and configuration dock for Propulsion Analysis."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._loading = False
        self._current_mode = "airspeed_sweep"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_system_section()
        self._create_mode_section()
        self._create_parameters_section()
        self._create_atmosphere_section()
        self._create_battery_state_section()
        self._create_actions_section()

        self._content_layout.addStretch(1)

        self._api.on_project_changed(lambda _p: self._refresh_assemblies())
        self._api.on_project_content_changed(lambda _p: self._refresh_assemblies())
        self._refresh_assemblies()

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(section)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

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
        layout = self._create_section("Target System", "fa6s.bolt")
        self.system_table = self._property_table([
            ("assembly", "Assembly"),
            ("motor_info", "Motor"),
            ("propeller_info", "Propeller"),
            ("battery_info", "Battery"),
        ])
        layout.addWidget(self.system_table)

    def _create_mode_section(self) -> None:
        layout = self._create_section("Analysis Mode", "fa6s.sliders")
        self.mode_table = self._property_table([
            ("mode", "Mode"),
        ])
        mode_options = [
            ("airspeed_sweep", "Airspeed Sweep"),
            ("throttle_sweep", "Throttle Sweep"),
            ("operating_point", "Single Operating Point"),
        ]
        self._set_property_combo(
            self.mode_table,
            "mode",
            "airspeed_sweep",
            mode_options,
            self._on_mode_changed,
        )
        layout.addWidget(self.mode_table)

    def _create_parameters_section(self) -> None:
        self.params_section_layout = self._create_section("Parameters", "fa6s.list-check")
        self.parameters_table = self._property_table([])
        self.parameters_table.cellChanged.connect(self._on_parameter_cell_changed)
        self.params_section_layout.addWidget(self.parameters_table)
        self._rebuild_parameters_table("airspeed_sweep")

    def _create_atmosphere_section(self) -> None:
        layout = self._create_section("Atmosphere", "fa6s.cloud")
        self.atmosphere_table = self._property_table([
            ("altitude", "Altitude (m)"),
            ("temperature", "Temperature (°C)"),
            ("density", "Air Density (kg/m³)"),
        ])
        self.atmosphere_table.cellChanged.connect(self._on_atmosphere_cell_changed)
        self._set_property_value(self.atmosphere_table, "altitude", "0.0")
        self._set_property_value(self.atmosphere_table, "temperature", "15.0")
        self._set_property_value(self.atmosphere_table, "density", "1.225", editable=False)
        layout.addWidget(self.atmosphere_table)

    def _create_battery_state_section(self) -> None:
        layout = self._create_section("Battery State", "fa6s.battery-half")
        self.battery_state_table = self._property_table([
            ("soc", "State of Charge"),
        ])
        soc_options = [
            ("full", "Full (4.20 V / cell)"),
            ("nominal", "Nominal (3.70 V / cell)"),
            ("discharged", "Discharged (3.50 V / cell)"),
        ]
        self._set_property_combo(
            self.battery_state_table,
            "soc",
            "full",
            soc_options,
            lambda _val: None,
        )
        layout.addWidget(self.battery_state_table)

    def _create_actions_section(self) -> None:
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        actions_layout = QHBoxLayout(container)
        actions_layout.setContentsMargins(0, 8, 0, 2)
        actions_layout.setSpacing(6)

        self.run_button = QPushButton("Run Analysis", self)
        self.run_button.setProperty("accent", True)
        self.run_button.setIcon(get_icon("fa6s.play"))
        self.run_button.setFixedHeight(28)
        self.run_button.clicked.connect(self._on_run_analysis)
        actions_layout.addWidget(self.run_button, 2)

        self.reset_button = QPushButton("Reset", self)
        self.reset_button.setIcon(get_icon("fa6s.arrow-rotate-left"))
        self.reset_button.setFixedHeight(28)
        self.reset_button.clicked.connect(self._reset_defaults)
        actions_layout.addWidget(self.reset_button, 1)

        self._content_layout.addWidget(container)
        self._create_alert_box()

    def _create_alert_box(self) -> None:
        self.alert_box = QWidget(self)
        self.alert_box.setObjectName("propulsionAlertBox")
        self.alert_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.alert_box.hide()

        alert_layout = QHBoxLayout(self.alert_box)
        alert_layout.setContentsMargins(10, 8, 10, 8)
        alert_layout.setSpacing(8)

        self.alert_icon = QLabel(self.alert_box)
        self.alert_icon.setFixedSize(16, 16)
        self.alert_icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        alert_layout.addWidget(self.alert_icon, 0, Qt.AlignmentFlag.AlignTop)

        text_container = QWidget(self.alert_box)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.alert_title = QLabel(text_container)
        self.alert_title.setStyleSheet("font-weight: bold; font-size: 11px;")
        text_layout.addWidget(self.alert_title)

        self.alert_message = QLabel(text_container)
        self.alert_message.setWordWrap(True)
        self.alert_message.setStyleSheet("font-size: 10.5px; line-height: 1.3;")
        text_layout.addWidget(self.alert_message)

        alert_layout.addWidget(text_container, 1)
        self._content_layout.addWidget(self.alert_box)

    def show_alert(self, severity: str, title: str, message: str) -> None:
        if severity in ("warning", "danger", "error"):
            self.alert_box.setStyleSheet(
                "#propulsionAlertBox {"
                "  background-color: #2b1819;"
                "  border: 1px solid #da3633;"
                "  border-radius: 6px;"
                "}"
            )
            self.alert_title.setStyleSheet("color: #f85149; font-weight: bold; font-size: 11px;")
            self.alert_message.setStyleSheet("color: #e6edf3; font-size: 10.5px;")
            self.alert_icon.setPixmap(get_icon("fa6s.triangle-exclamation").pixmap(16, 16))
        else:
            self.alert_box.setStyleSheet(
                "#propulsionAlertBox {"
                "  background-color: #122619;"
                "  border: 1px solid #238636;"
                "  border-radius: 6px;"
                "}"
            )
            self.alert_title.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 11px;")
            self.alert_message.setStyleSheet("color: #e6edf3; font-size: 10.5px;")
            self.alert_icon.setPixmap(get_icon("fa6s.circle-check").pixmap(16, 16))

        self.alert_title.setText(title)
        self.alert_message.setText(message)
        self.alert_box.show()

    def hide_alert(self) -> None:
        if hasattr(self, "alert_box"):
            self.alert_box.hide()

    def _on_mode_changed(self, mode: str) -> None:
        self._current_mode = mode
        self._rebuild_parameters_table(mode)

    def _rebuild_parameters_table(self, mode: str) -> None:
        self._loading = True
        if mode == "airspeed_sweep":
            defs = [
                ("throttle", "Throttle (%)"),
                ("v_min", "Min Airspeed (m/s)"),
                ("v_max", "Max Airspeed (m/s)"),
                ("v_step", "Airspeed Step (m/s)"),
            ]
            self._configure_property_table(self.parameters_table, defs)
            self._set_property_value(self.parameters_table, "throttle", "100")
            self._set_property_value(self.parameters_table, "v_min", "0.0")
            self._set_property_value(self.parameters_table, "v_max", "35.0")
            self._set_property_value(self.parameters_table, "v_step", "1.0")
        elif mode == "throttle_sweep":
            defs = [
                ("airspeed", "Airspeed (m/s)"),
                ("t_min", "Min Throttle (%)"),
                ("t_max", "Max Throttle (%)"),
                ("t_step", "Throttle Step (%)"),
            ]
            self._configure_property_table(self.parameters_table, defs)
            self._set_property_value(self.parameters_table, "airspeed", "0.0")
            self._set_property_value(self.parameters_table, "t_min", "10")
            self._set_property_value(self.parameters_table, "t_max", "100")
            self._set_property_value(self.parameters_table, "t_step", "5")
        elif mode == "operating_point":
            defs = [
                ("airspeed", "Airspeed (m/s)"),
                ("throttle", "Throttle (%)"),
            ]
            self._configure_property_table(self.parameters_table, defs)
            self._set_property_value(self.parameters_table, "airspeed", "18.0")
            self._set_property_value(self.parameters_table, "throttle", "75")
        self._loading = False

    def _on_parameter_cell_changed(self, row: int, col: int) -> None:
        if self._loading or col != 1:
            return

    def _on_atmosphere_cell_changed(self, row: int, col: int) -> None:
        if self._loading or col != 1:
            return
        self._update_isa_density()

    def _update_isa_density(self) -> None:
        try:
            alt_text = self._property_value(self.atmosphere_table, "altitude")
            temp_text = self._property_value(self.atmosphere_table, "temperature")
            alt = float(alt_text) if alt_text else 0.0
            temp_c = float(temp_text) if temp_text else 15.0
        except ValueError:
            return

        # Standard Atmosphere formula
        t_kelvin = temp_c + 273.15
        p0 = 101325.0
        r_air = 287.058
        if alt <= 11000:
            pressure = p0 * ((1 - 0.0065 * alt / 288.15) ** 5.25588)
        else:
            pressure = 22632.0 * math.exp(-9.80665 * (alt - 11000) / (r_air * 216.65))

        density = pressure / (r_air * max(t_kelvin, 1.0))
        self._loading = True
        self._set_property_value(
            self.atmosphere_table, "density", f"{density:.3f}", editable=False
        )
        self._loading = False

    def _reset_defaults(self) -> None:
        self.hide_alert()
        self._loading = True
        self._set_property_value(self.atmosphere_table, "altitude", "0.0")
        self._set_property_value(self.atmosphere_table, "temperature", "15.0")
        self._set_property_value(self.atmosphere_table, "density", "1.225", editable=False)
        self._set_table_combo_selection(self.mode_table, "mode", "airspeed_sweep")
        self._set_table_combo_selection(self.battery_state_table, "soc", "full")
        self._rebuild_parameters_table("airspeed_sweep")
        self._loading = False

    def _refresh_assemblies(self) -> None:
        proj = self._api.current_project
        if proj is None:
            self._set_property_value(self.system_table, "assembly", "No Project", editable=False)
            self._set_property_value(self.system_table, "motor_info", "-", editable=False)
            self._set_property_value(self.system_table, "propeller_info", "-", editable=False)
            self._set_property_value(self.system_table, "battery_info", "-", editable=False)
            self.run_button.setEnabled(False)
            return

        assemblies = proj.data.get("assemblies", [])
        prop_assemblies = [
            a for a in assemblies
            if a.get("type") == "org.setuav.core:electric-propulsion-system"
        ]

        if not prop_assemblies:
            self._set_property_value(self.system_table, "assembly", "None", editable=False)
            self._set_property_value(self.system_table, "motor_info", "-", editable=False)
            self._set_property_value(self.system_table, "propeller_info", "-", editable=False)
            self._set_property_value(self.system_table, "battery_info", "-", editable=False)
            self.run_button.setEnabled(False)
            return

        options = [
            (str(a.get("id")), str(a.get("name") or a.get("id")))
            for a in prop_assemblies
        ]
        self._set_property_combo(
            self.system_table,
            "assembly",
            options[0][0],
            options,
            self._on_assembly_selected,
        )
        self._on_assembly_selected(options[0][0])
        self.run_button.setEnabled(True)

    def _on_assembly_selected(self, assembly_id: str) -> None:
        proj = self._api.current_project
        if not proj:
            return

        assemblies = proj.data.get("assemblies", [])
        components = proj.data.get("components", [])
        assembly = next((a for a in assemblies if a.get("id") == assembly_id), None)
        if not assembly:
            return

        members = assembly.get("members", {})
        comp_map = {c.get("id"): c for c in components}

        # Motor Info
        motor_ids = members.get("motors", [])
        motor = comp_map.get(motor_ids[0]) if motor_ids else None
        motor_text = f"{motor.get('name') or motor.get('model') or motor.get('id')}" if motor else "-"
        self._set_property_value(self.system_table, "motor_info", motor_text, editable=False)

        # Propeller Info
        prop_ids = members.get("propulsors", [])
        prop = comp_map.get(prop_ids[0]) if prop_ids else None
        prop_text = f"{prop.get('name') or prop.get('model') or prop.get('id')}" if prop else "-"
        self._set_property_value(self.system_table, "propeller_info", prop_text, editable=False)

        # Battery Info
        bat_id = members.get("battery")
        battery = comp_map.get(bat_id) if bat_id else None
        if battery:
            params = battery.get("parameters", {})
            pack = params.get("pack", {})
            cell = params.get("cell", {})
            s = pack.get("series_count") or params.get("cell_count") or params.get("series_count", 1)
            cap = pack.get("capacity") or params.get("capacity", 0)
            chem = cell.get("chemistry") or params.get("chemistry", "LiPo")
            bat_text = f"{int(s)}S {chem} ({float(cap):.0f} mAh)"
        else:
            bat_text = "-"
        self._set_property_value(self.system_table, "battery_info", bat_text, editable=False)

    def get_configuration(self) -> dict[str, Any]:
        """Collect all configured parameters for the propulsion solver."""
        return {
            "assembly_id": self._get_table_combo_value(self.system_table, "assembly"),
            "mode": self._current_mode,
            "soc": self._get_table_combo_value(self.battery_state_table, "soc"),
            "altitude": float(self._property_value(self.atmosphere_table, "altitude") or 0.0),
            "temperature": float(self._property_value(self.atmosphere_table, "temperature") or 15.0),
            "density": float(self._property_value(self.atmosphere_table, "density") or 1.225),
            "parameters": {
                self._property_key(self.parameters_table, row): self._property_value_by_row(self.parameters_table, row)
                for row in range(self.parameters_table.rowCount())
            },
        }

    def _on_run_analysis(self) -> None:
        proj = self._api.current_project
        if not proj:
            return

        config = self.get_configuration()
        assembly_id = config["assembly_id"]
        assemblies = proj.data.get("assemblies", [])
        components = proj.data.get("components", [])
        assembly = next((a for a in assemblies if a.get("id") == assembly_id), None)
        comp_map = {c.get("id"): c for c in components}

        # Extract motor
        motor_comp = None
        if assembly:
            motor_ids = assembly.get("members", {}).get("motors", [])
            motor_comp = comp_map.get(motor_ids[0]) if motor_ids else None

        motor_params = motor_comp.get("parameters", {}) if motor_comp else {}
        kv = float(motor_params.get("kv") or motor_params.get("kv_rpm_per_v") or 900.0)
        r_motor = float(motor_params.get("resistance") or motor_params.get("resistance_ohm") or 0.035)
        i0 = float(motor_params.get("no_load_current") or motor_params.get("no_load_current_a") or 1.2)
        i_max = float(motor_params.get("max_current") or motor_params.get("current_max_a") or 45.0)
        motor_spec = MotorSpec(kv_rpm_per_v=kv, resistance_ohm=r_motor, no_load_current_a=i0, current_max_a=i_max)

        # Extract propeller
        prop_comp = None
        if assembly:
            prop_ids = assembly.get("members", {}).get("propulsors", [])
            prop_comp = comp_map.get(prop_ids[0]) if prop_ids else None

        prop_params = prop_comp.get("parameters", {}) if prop_comp else {}
        d_raw = float(prop_params.get("diameter_m") or prop_params.get("diameter") or 0.3302)
        p_raw = float(prop_params.get("pitch_m") or prop_params.get("pitch") or 0.1651)
        diameter_m = d_raw / 1000.0 if d_raw > 2.0 else d_raw
        pitch_m = p_raw / 1000.0 if p_raw > 2.0 else p_raw
        diameter_in = diameter_m / 0.0254
        pitch_in = pitch_m / 0.0254
        blades = int(prop_params.get("blades") or prop_params.get("blade_count") or 2)

        prop_spec = PropellerSpec(diameter_m=diameter_m, pitch_m=pitch_m, blade_count=blades)

        # Extract propeller from database or fallbacks
        prop_db = get_propeller_database()
        prop_name = str(prop_comp.get("name") or prop_comp.get("model") or "") if prop_comp else ""
        prop_entry = None
        if prop_name:
            prop_entry = prop_db.get(prop_name) or prop_db.get(prop_name.replace(" ", "_"))
        if prop_entry is None:
            prop_entry = (
                prop_db.get(f"APC_{diameter_in:.1f}x{pitch_in:.1f}E")
                or prop_db.get(f"APC_{int(diameter_in)}x{pitch_in:.1f}E")
                or prop_db.get(f"APC_{int(diameter_in)}x{int(pitch_in)}")
                or prop_db.find_by_size(diameter_in, pitch_in)
            )

        if prop_entry is None:
            prop_meta = PropellerMetadata(
                id=f"prop_{diameter_in:.1f}x{pitch_in:.1f}",
                manufacturer="APC",
                model=f"{diameter_in:.1f}x{pitch_in:.1f}",
                diameter_in=diameter_in,
                pitch_in=pitch_in,
                blade_count=blades,
                data_csv="",
            )
            prop_data: dict[int, list[PropellerDataPoint]] = {}
            p_d = pitch_in / max(diameter_in, 1e-3)
            j_max = p_d * 1.15
            for r in [2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 15000]:
                pts = []
                for j_i in range(30):
                    j_val = j_i * (j_max / 29.0)
                    ct = max(0.0, 0.095 * (1.0 - (j_val / max(j_max, 1e-3))**1.4))
                    cp = max(0.005, 0.039 * (1.0 - 0.70 * (j_val / max(j_max, 1e-3))**1.8))
                    pts.append(PropellerDataPoint(j=float(j_val), ct=float(ct), cp=float(cp)))
                prop_data[r] = pts
            prop_entry = PropellerEntry(metadata=prop_meta, data_by_rpm=prop_data)

        # Extract battery
        bat_comp = None
        if assembly:
            bat_id = assembly.get("members", {}).get("battery")
            bat_comp = comp_map.get(bat_id) if bat_id else None

        bat_params = bat_comp.get("parameters", {}) if bat_comp else {}
        pack = bat_params.get("pack", {})
        cell_count = int(pack.get("series_count") or bat_params.get("cell_count") or 6)
        capacity_mah = float(pack.get("capacity") or bat_params.get("capacity") or 6000.0)

        # State of charge factor
        soc_val = config.get("soc", "full")
        v_per_cell = 4.20 if soc_val == "full" else (3.70 if soc_val == "nominal" else 3.50)
        total_voltage = v_per_cell * cell_count

        rho = float(config.get("density", 1.225))
        mode = config.get("mode", "airspeed_sweep")
        params = config.get("parameters", {})

        # Find Results Dock and Charts Dock
        win = self.window()
        results_dock = win.findChild(QWidget, "propulsion.results_widget") or next(
            (d for d in win.findChildren(QWidget) if d.__class__.__name__ == "PropulsionResultsDock"), None
        )
        charts_dock = win.findChild(QWidget, "propulsion.charts_widget") or next(
            (d for d in win.findChildren(QWidget) if d.__class__.__name__ == "PropulsionChartsDock"), None
        )

        def solve_point(v_mps: float, throttle_val: float) -> dict[str, Any]:
            v_app = max(throttle_val * total_voltage, 0.1)
            rpm_max = motor_spec.kv_rpm_per_v * v_app * 1.05

            def g(rpm_val: float) -> float:
                if rpm_val <= 10.0:
                    return -v_app
                n_val = rpm_val / 60.0
                j_val = v_mps / (n_val * prop_spec.diameter_m) if prop_spec.diameter_m > 0 else 0.0
                ct_v, cp_v = prop_entry.get_coefficients(rpm_val, j_val)
                ct_v = max(ct_v, 0.0)
                cp_v = max(cp_v, 0.0)
                torque_nm = cp_v * rho * (n_val**2) * (prop_spec.diameter_m**5) / (2.0 * math.pi)
                kt = 30.0 / (math.pi * motor_spec.kv_rpm_per_v)
                i_a = torque_nm / kt + motor_spec.get_no_load_current(rpm_val)
                v_b = rpm_val / motor_spec.kv_rpm_per_v
                v_mot = v_b + i_a * motor_spec.get_winding_resistance(i_a)
                return v_mot + i_a * 0.01 - v_app

            try:
                res_root = root_scalar(g, bracket=[100.0, rpm_max], method="brentq")
                rpm_solved = res_root.root
            except Exception:
                logger.warning("RPM solver failed at v=%.1f m/s; falling back to rpm_max", v_mps)
                rpm_solved = rpm_max

            n = rpm_solved / 60.0
            j_solved = v_mps / (n * prop_spec.diameter_m) if (n * prop_spec.diameter_m) > 0 else 0.0
            ct_s, cp_s = prop_entry.get_coefficients(rpm_solved, j_solved)
            ct_s = max(ct_s, 0.0)
            cp_s = max(cp_s, 0.0)
            thrust = ct_s * rho * (n**2) * (prop_spec.diameter_m**4)
            p_shaft = cp_s * rho * (n**3) * (prop_spec.diameter_m**5)
            torque_nm = p_shaft / (2.0 * math.pi * n) if n > 0 else 0.0
            kt = 30.0 / (math.pi * motor_spec.kv_rpm_per_v)
            current_a = torque_nm / kt + motor_spec.get_no_load_current(rpm_solved)
            v_back = rpm_solved / motor_spec.kv_rpm_per_v
            v_motor = v_back + current_a * motor_spec.get_winding_resistance(current_a)
            p_elec = v_motor * current_a
            eta_p = (thrust * v_mps) / p_shaft if p_shaft > 0 else 0.0
            eta_m = p_shaft / p_elec if p_elec > 0 else 0.0
            eta_sys = (thrust * v_mps) / p_elec if p_elec > 0 else 0.0
            feasible = current_a <= motor_spec.current_max_a

            return {
                "rpm": rpm_solved,
                "thrust": max(thrust, 0.0),
                "power": max(p_elec, 0.0),
                "current": max(current_a, 0.0),
                "eta_p": min(max(eta_p, 0.0), 1.0),
                "eta_m": min(max(eta_m, 0.0), 1.0),
                "eta_sys": min(max(eta_sys, 0.0), 1.0),
                "j": j_solved,
                "feasible": feasible,
            }

        if mode == "airspeed_sweep":
            throttle_pct = float(params.get("throttle", 100.0))
            v_min = float(params.get("v_min", 0.0))
            v_max = float(params.get("v_max", 35.0))
            v_step = max(float(params.get("v_step", 1.0)), 0.1)

            x_vals: list[float] = []
            thrusts: list[float] = []
            powers: list[float] = []
            currents: list[float] = []
            rpms: list[float] = []
            eta_tots: list[float] = []
            eta_props: list[float] = []
            eta_mots: list[float] = []
            sweep_rows: list[dict[str, Any]] = []

            curr_v = v_min
            throttle_norm = max(min(throttle_pct / 100.0, 1.0), 0.01)
            while curr_v <= v_max + 1e-4:
                pt = solve_point(curr_v, throttle_norm)
                x_vals.append(curr_v)
                thrusts.append(pt["thrust"])
                powers.append(pt["power"])
                currents.append(pt["current"])
                rpms.append(pt["rpm"])
                eta_tots.append(pt["eta_sys"])
                eta_props.append(pt["eta_p"])
                eta_mots.append(pt["eta_m"])
                sweep_rows.append({
                    "x_val": curr_v,
                    "x_label": "Airspeed (m/s)",
                    "rpm": pt["rpm"],
                    "thrust": pt["thrust"],
                    "power": pt["power"],
                    "current": pt["current"],
                    "eta_sys": pt["eta_sys"],
                    "eta_p": pt["eta_p"],
                    "eta_m": pt["eta_m"],
                    "j": pt["j"],
                    "feasible": pt["feasible"],
                })
                curr_v += v_step

            # Operating point at cruise (~18 m/s or mid)
            cruise_idx = min(len(x_vals) - 1, max(0, int(len(x_vals) * 0.5)))
            cruise_power = max(powers[cruise_idx], 1e-3)
            batt_wh = (total_voltage * capacity_mah / 1000.0)
            endurance_min = (batt_wh * 0.8 / cruise_power) * 60.0

            res = {
                "static_thrust": thrusts[0] if thrusts else 0.0,
                "peak_power": max(powers) if powers else 0.0,
                "peak_current": max(currents) if currents else 0.0,
                "max_rpm": max(rpms) if rpms else 0.0,
                "cruise_thrust": thrusts[cruise_idx] if thrusts else 0.0,
                "cruise_efficiency": eta_tots[cruise_idx] if eta_tots else 0.0,
                "endurance_min": endurance_min,
                "advance_ratio": (x_vals[cruise_idx] / max((rpms[cruise_idx]/60.0) * prop_spec.diameter_m, 1e-3)),
                "prop_efficiency": eta_props[cruise_idx],
                "motor_efficiency": eta_mots[cruise_idx],
                "voltage_loaded": total_voltage - currents[cruise_idx] * 0.02,
                "sweep_table": sweep_rows,
                "motor_max_current": motor_spec.current_max_a,
            }

            if charts_dock and hasattr(charts_dock, "plot_sweep_results"):
                charts_dock.plot_sweep_results(
                    x_label="Airspeed (m/s)",
                    x_values=x_vals,
                    thrust_n=thrusts,
                    power_w=powers,
                    current_a=currents,
                    rpm=rpms,
                    eta_total=eta_tots,
                    eta_prop=eta_props,
                    eta_motor=eta_mots,
                )
            if results_dock and hasattr(results_dock, "set_results"):
                results_dock.set_results(res)

        elif mode == "throttle_sweep":
            v_fixed = float(params.get("airspeed", 15.0))
            t_min = float(params.get("t_min", 10.0))
            t_max = float(params.get("t_max", 100.0))
            t_step = max(float(params.get("t_step", 5.0)), 1.0)

            x_vals = []
            thrusts = []
            powers = []
            currents = []
            rpms = []
            eta_tots = []
            eta_props = []
            eta_mots = []
            sweep_rows = []

            curr_t = t_min
            while curr_t <= t_max + 1e-4:
                pt = solve_point(v_fixed, curr_t / 100.0)
                x_vals.append(curr_t)
                thrusts.append(pt["thrust"])
                powers.append(pt["power"])
                currents.append(pt["current"])
                rpms.append(pt["rpm"])
                eta_tots.append(pt["eta_sys"])
                eta_props.append(pt["eta_p"])
                eta_mots.append(pt["eta_m"])
                sweep_rows.append({
                    "x_val": curr_t,
                    "x_label": "Throttle (%)",
                    "rpm": pt["rpm"],
                    "thrust": pt["thrust"],
                    "power": pt["power"],
                    "current": pt["current"],
                    "eta_sys": pt["eta_sys"],
                    "eta_p": pt["eta_p"],
                    "eta_m": pt["eta_m"],
                    "j": pt["j"],
                    "feasible": pt["feasible"],
                })
                curr_t += t_step

            cruise_idx = len(x_vals) - 1
            cruise_power = max(powers[cruise_idx], 1e-3)
            batt_wh = (total_voltage * capacity_mah / 1000.0)
            endurance_min = (batt_wh * 0.8 / cruise_power) * 60.0

            res = {
                "static_thrust": thrusts[-1] if thrusts else 0.0,
                "peak_power": max(powers) if powers else 0.0,
                "peak_current": max(currents) if currents else 0.0,
                "max_rpm": max(rpms) if rpms else 0.0,
                "cruise_thrust": thrusts[cruise_idx] if thrusts else 0.0,
                "cruise_efficiency": eta_tots[cruise_idx] if eta_tots else 0.0,
                "endurance_min": endurance_min,
                "advance_ratio": (v_fixed / max((rpms[cruise_idx]/60.0) * prop_spec.diameter_m, 1e-3)),
                "prop_efficiency": eta_props[cruise_idx],
                "motor_efficiency": eta_mots[cruise_idx],
                "voltage_loaded": total_voltage - currents[cruise_idx] * 0.02,
                "sweep_table": sweep_rows,
                "motor_max_current": motor_spec.current_max_a,
            }

            if charts_dock and hasattr(charts_dock, "plot_sweep_results"):
                charts_dock.plot_sweep_results(
                    x_label="Throttle (%)",
                    x_values=x_vals,
                    thrust_n=thrusts,
                    power_w=powers,
                    current_a=currents,
                    rpm=rpms,
                    eta_total=eta_tots,
                    eta_prop=eta_props,
                    eta_motor=eta_mots,
                )
            if results_dock and hasattr(results_dock, "set_results"):
                results_dock.set_results(res)

        elif mode == "operating_point":
            v_val = float(params.get("airspeed", 18.0))
            t_val = float(params.get("throttle", 75.0))
            pt = solve_point(v_val, t_val / 100.0)

            cruise_power = max(pt["power"], 1e-3)
            batt_wh = (total_voltage * capacity_mah / 1000.0)
            endurance_min = (batt_wh * 0.8 / cruise_power) * 60.0

            sweep_rows = [{
                "x_val": v_val,
                "x_label": "Airspeed (m/s)",
                "rpm": pt["rpm"],
                "thrust": pt["thrust"],
                "power": pt["power"],
                "current": pt["current"],
                "eta_sys": pt["eta_sys"],
                "eta_p": pt["eta_p"],
                "eta_m": pt["eta_m"],
                "j": pt["j"],
                "feasible": pt["feasible"],
            }]

            res = {
                "static_thrust": pt["thrust"],
                "peak_power": pt["power"],
                "peak_current": pt["current"],
                "max_rpm": pt["rpm"],
                "cruise_thrust": pt["thrust"],
                "cruise_efficiency": pt["eta_sys"],
                "endurance_min": endurance_min,
                "advance_ratio": pt["j"],
                "prop_efficiency": pt["eta_p"],
                "motor_efficiency": pt["eta_m"],
                "voltage_loaded": total_voltage - pt["current"] * 0.02,
                "sweep_table": sweep_rows,
                "motor_max_current": motor_spec.current_max_a,
            }
            if charts_dock and hasattr(charts_dock, "clear_charts"):
                charts_dock.clear_charts()
            if results_dock and hasattr(results_dock, "set_results"):
                results_dock.set_results(res)

        # Check overall feasibility and alert user with PyThrust diagnosis
        peak_curr = res.get("peak_current", 0.0) if "res" in locals() and res else 0.0
        peak_pwr = res.get("peak_power", 0.0) if "res" in locals() and res else 0.0
        max_curr_limit = motor_spec.current_max_a
        max_pwr_limit = float(motor_params.get("max_power") or 0.0)

        if peak_curr > max_curr_limit:
            over_pct = ((peak_curr / max(max_curr_limit, 1e-3)) - 1.0) * 100.0
            self.show_alert(
                severity="danger",
                title="Motor Current Limit Exceeded",
                message=(
                    f"PyThrust Warning: Peak current draw ({peak_curr:.1f} A) exceeds "
                    f"the motor continuous rating ({max_curr_limit:.1f} A) by {over_pct:.0f}%. "
                    f"The propeller ({diameter_in:.1f}×{pitch_in:.1f}) is overloading the motor at this battery voltage."
                ),
            )
        elif max_pwr_limit > 0 and peak_pwr > max_pwr_limit:
            over_pct = ((peak_pwr / max_pwr_limit) - 1.0) * 100.0
            self.show_alert(
                severity="warning",
                title="Motor Power Limit Exceeded",
                message=(
                    f"PyThrust Warning: Peak electrical power ({peak_pwr:.1f} W) exceeds "
                    f"the motor maximum power rating ({max_pwr_limit:.1f} W) by {over_pct:.0f}%."
                ),
            )
        else:
            self.show_alert(
                severity="success",
                title="Operating Point Feasible",
                message=f"PyThrust: All operating points are within safe motor limits (Peak: {peak_curr:.1f} A / Max: {max_curr_limit:.1f} A).",
            )

    # Helper Table Methods
    @classmethod
    def _property_table(cls, definitions: list[tuple[str, str]]) -> QTableWidget:
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
        cls, table: QTableWidget, definitions: list[tuple[str, str]]
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
            val_item = QTableWidgetItem()
            table.setItem(row, 1, val_item)
        cls._fit_table_height(table, len(definitions))

    def _set_property_combo(
        self,
        table: QTableWidget,
        key: str,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Callable[[str], None],
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
        on_changed: Callable[[str], None],
    ) -> None:
        item = table.item(row, column)
        if item is not None:
            item.setText("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        combo = QComboBox(table)
        combo.setFont(QApplication.font())
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        combo.view().setProperty("tableComboPopup", True)
        combo.view().setFont(QApplication.font())
        for option_value, label in options:
            combo.addItem(label, option_value)
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(
            lambda _index, editor=combo, callback=on_changed: callback(
                str(editor.currentData())
            )
        )
        table.setCellWidget(row, column, combo)

    @staticmethod
    def _set_table_combo_selection(table: QTableWidget, key: str, value: str) -> None:
        for row in range(table.rowCount()):
            if PropulsionControlsDock._property_key(table, row) == key:
                combo = table.cellWidget(row, 1)
                if isinstance(combo, QComboBox):
                    idx = combo.findData(value)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                return

    @staticmethod
    def _get_table_combo_value(table: QTableWidget, key: str) -> str:
        for row in range(table.rowCount()):
            if PropulsionControlsDock._property_key(table, row) == key:
                combo = table.cellWidget(row, 1)
                if isinstance(combo, QComboBox):
                    return str(combo.currentData() or "")
                item = table.item(row, 1)
                return item.text() if item else ""
        return ""

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
    def _property_value(table: QTableWidget, key: str) -> str:
        for row in range(table.rowCount()):
            if PropulsionControlsDock._property_key(table, row) == key:
                item = table.item(row, 1)
                return item.text().strip() if item else ""
        return ""

    @staticmethod
    def _property_value_by_row(table: QTableWidget, row: int) -> str:
        item = table.item(row, 1)
        return item.text().strip() if item else ""

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
