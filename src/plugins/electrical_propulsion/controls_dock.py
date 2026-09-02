"""Propulsion Analysis Controls dock widget."""

from __future__ import annotations

import logging
import math
from typing import Any

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from pythrust.propellers.database import PropellerEntry
from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec

from setuav_studio.ui.icons import get_icon, set_label_icon
from setuav_studio.ui.widget.button import refresh_button_role, set_button_role, set_native_button
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio_sdk import StudioAPI, StudioEvents

from .database import get_propeller_database
from .engine.solver import PropulsionSolverEngine
from .worker import PropulsionWorker

logger = logging.getLogger(__name__)


class PropulsionControlsDock(PropertyTableMixin, QWidget):
    """Clean controls and configuration dock for Propulsion Analysis."""

    table_combo_strict_find = True

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._loading = False
        self._is_running = False
        self._current_mode = "airspeed_sweep"
        self._alert_severity = "success"

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

        self._section_icons: list[tuple[QLabel, str]] = []
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

    def update_theme_style(self) -> None:
        for lbl, name in self._section_icons:
            set_label_icon(lbl, name)
        if hasattr(self, "run_button"):
            refresh_button_role(self.run_button)
        if hasattr(self, "reset_button"):
            refresh_button_role(self.reset_button)
        if hasattr(self, "alert_box") and self.alert_box.isVisible():
            self.show_alert(
                self._alert_severity,
                self.alert_title.text(),
                self.alert_message.text(),
            )

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
            set_label_icon(icon_label, icon_name)
            icon_label.setFixedSize(14, 14)
            self._section_icons.append((icon_label, icon_name))
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_system_section(self) -> None:
        layout = self._create_section("Target System", "fa6s.bolt")
        self.system_table = self._property_table(
            [
                ("assembly", "Assembly"),
                ("motor_info", "Motor"),
                ("propeller_info", "Propeller"),
                ("battery_info", "Battery"),
            ]
        )
        layout.addWidget(self.system_table)

    def _create_mode_section(self) -> None:
        layout = self._create_section("Analysis Mode", "fa6s.sliders")
        self.mode_table = self._property_table(
            [
                ("mode", "Mode"),
            ]
        )
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
        self.atmosphere_table = self._property_table(
            [
                ("altitude", "Altitude"),
                ("temperature", "Temperature"),
                ("density", "Air Density"),
            ]
        )
        self.atmosphere_table.cellChanged.connect(self._on_atmosphere_cell_changed)
        self._set_property_value(self.atmosphere_table, "altitude", "0.0")
        self._set_property_value(self.atmosphere_table, "temperature", "15.0")
        self._set_property_value(self.atmosphere_table, "density", "1.225", editable=False)
        layout.addWidget(self.atmosphere_table)

    def _create_battery_state_section(self) -> None:
        layout = self._create_section("Battery State", "fa6s.battery-half")
        self.battery_state_table = self._property_table(
            [
                ("soc", "State of Charge"),
            ]
        )
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
        set_button_role(self.run_button, "primary", "fa6s.play")
        self.run_button.setFixedHeight(28)
        self.run_button.clicked.connect(self._on_run_analysis)
        actions_layout.addWidget(self.run_button, 2)

        self.reset_button = QPushButton("Reset", self)
        set_native_button(self.reset_button, "fa6s.arrow-rotate-left")
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
        title_font = QFont(self.alert_title.font())
        title_font.setBold(True)
        self.alert_title.setFont(title_font)
        text_layout.addWidget(self.alert_title)

        self.alert_message = QLabel(text_container)
        self.alert_message.setWordWrap(True)
        text_layout.addWidget(self.alert_message)

        alert_layout.addWidget(text_container, 1)
        self._content_layout.addWidget(self.alert_box)

    def show_alert(self, severity: str, title: str, message: str) -> None:
        from setuav_studio.ui.theme import status_color

        self._alert_severity = severity
        if severity in ("warning", "danger", "error"):
            color = status_color("error")
            self.alert_icon.setPixmap(
                get_icon("fa6s.triangle-exclamation", color=color).pixmap(16, 16)
            )
        else:
            color = status_color("success")
            self.alert_icon.setPixmap(get_icon("fa6s.circle-check", color=color).pixmap(16, 16))

        palette = self.alert_title.palette()
        palette.setColor(QPalette.ColorRole.WindowText, color)
        self.alert_title.setPalette(palette)

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
                ("throttle", "Throttle"),
                ("v_min", "Min Airspeed"),
                ("v_max", "Max Airspeed"),
                ("v_step", "Airspeed Step"),
            ]
            self._configure_property_table(self.parameters_table, defs)
            self._set_property_value(self.parameters_table, "throttle", "100")
            self._set_property_value(self.parameters_table, "v_min", "0.0")
            self._set_property_value(self.parameters_table, "v_max", "35.0")
            self._set_property_value(self.parameters_table, "v_step", "1.0")
        elif mode == "throttle_sweep":
            defs = [
                ("airspeed", "Airspeed"),
                ("t_min", "Min Throttle"),
                ("t_max", "Max Throttle"),
                ("t_step", "Throttle Step"),
            ]
            self._configure_property_table(self.parameters_table, defs)
            self._set_property_value(self.parameters_table, "airspeed", "0.0")
            self._set_property_value(self.parameters_table, "t_min", "10")
            self._set_property_value(self.parameters_table, "t_max", "100")
            self._set_property_value(self.parameters_table, "t_step", "5")
        elif mode == "operating_point":
            defs = [
                ("airspeed", "Airspeed"),
                ("throttle", "Throttle"),
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
        self._set_property_value(self.atmosphere_table, "density", f"{density:.3f}", editable=False)
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
            a for a in assemblies if a.get("type") == "org.setuav.core:electric-propulsion-system"
        ]

        if not prop_assemblies:
            self._set_property_value(self.system_table, "assembly", "None", editable=False)
            self._set_property_value(self.system_table, "motor_info", "-", editable=False)
            self._set_property_value(self.system_table, "propeller_info", "-", editable=False)
            self._set_property_value(self.system_table, "battery_info", "-", editable=False)
            self.run_button.setEnabled(False)
            return

        options = [(str(a.get("id")), str(a.get("name") or a.get("id"))) for a in prop_assemblies]
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
        motor_text = (
            f"{motor.get('name') or motor.get('model') or motor.get('id')}" if motor else "-"
        )
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
            s = (
                pack.get("series_count")
                or params.get("cell_count")
                or params.get("series_count", 1)
            )
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
            "temperature": float(
                self._property_value(self.atmosphere_table, "temperature") or 15.0
            ),
            "density": float(self._property_value(self.atmosphere_table, "density") or 1.225),
            "parameters": {
                self._property_key(self.parameters_table, row): self._property_value_by_row(
                    self.parameters_table, row
                )
                for row in range(self.parameters_table.rowCount())
            },
        }

    def _on_run_analysis(self) -> None:
        if self._is_running:
            return

        context = self._build_analysis_context()
        if context is None:
            return

        mode = context["mode"]
        mode_label = {
            "airspeed_sweep": "airspeed sweep",
            "throttle_sweep": "throttle sweep",
            "operating_point": "operating point",
        }.get(mode, mode)

        self._is_running = True
        self.run_button.setEnabled(False)
        self._api.show_status(f"Running {mode_label} in background…", "info", 0)
        self._api.report_progress(0, 100, "Propulsion")

        self._worker = PropulsionWorker(context)
        self._worker.signals.progress.connect(self._on_analysis_progress)
        self._worker.signals.finished.connect(
            lambda res, ctx=context: self._on_analysis_finished(ctx, res)
        )
        self._worker.signals.error.connect(self._on_analysis_error)

        QThreadPool.globalInstance().start(self._worker)

    def _on_analysis_progress(self, current: int, total: int, msg: str) -> None:
        self._api.report_progress(current, total, msg or "Solving")

    def _on_analysis_finished(self, context: dict[str, Any], res: dict[str, Any]) -> None:
        self._is_running = False
        self._worker = None
        self.run_button.setEnabled(True)
        self._api.clear_progress()
        self._render_results(res)
        self._show_feasibility_alert(context, res)

    def _on_analysis_error(self, err_msg: str) -> None:
        self._is_running = False
        self._worker = None
        self.run_button.setEnabled(True)
        self._api.clear_progress()
        self._api.show_status(f"Propulsion analysis failed: {err_msg}", "error", 8000)
        QMessageBox.critical(
            self,
            "Analysis Error",
            f"Propulsion analysis encountered an error:\n\n{err_msg}",
        )

    @staticmethod
    def _arange(start: float, end: float, step: float) -> list[float]:
        values: list[float] = []
        curr = start
        while curr <= end + 1e-4:
            values.append(curr)
            curr += step
        return values

    def _build_analysis_context(self) -> dict[str, Any] | None:
        proj = self._api.current_project
        if not proj:
            return None

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
        r_motor = float(
            motor_params.get("resistance") or motor_params.get("resistance_ohm") or 0.035
        )
        i0 = float(
            motor_params.get("no_load_current") or motor_params.get("no_load_current_a") or 1.2
        )
        i_max = float(motor_params.get("max_current") or motor_params.get("current_max_a") or 45.0)
        motor_spec = MotorSpec(
            kv_rpm_per_v=kv, resistance_ohm=r_motor, no_load_current_a=i0, current_max_a=i_max
        )

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
            prop_entry = self._fallback_propeller(diameter_in, pitch_in, blades)

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

        return {
            "mode": mode,
            "params": params,
            "motor_spec": motor_spec,
            "motor_params": motor_params,
            "prop_spec": prop_spec,
            "prop_entry": prop_entry,
            "total_voltage": total_voltage,
            "capacity_mah": capacity_mah,
            "rho": rho,
            "diameter_in": diameter_in,
            "pitch_in": pitch_in,
        }

    @staticmethod
    def _fallback_propeller(diameter_in: float, pitch_in: float, blades: int) -> PropellerEntry:
        return PropulsionSolverEngine.fallback_propeller(diameter_in, pitch_in, blades)

    def _solve_rpm(self, context: dict[str, Any], v_mps: float, throttle_val: float) -> float:
        return PropulsionSolverEngine.solve_rpm(
            motor_spec=context["motor_spec"],
            prop_spec=context["prop_spec"],
            prop_entry=context["prop_entry"],
            total_voltage=context["total_voltage"],
            rho=context["rho"],
            v_mps=v_mps,
            throttle_val=throttle_val,
        )

    def _solve_point(
        self, context: dict[str, Any], v_mps: float, throttle_val: float
    ) -> dict[str, Any]:
        pt = PropulsionSolverEngine.solve_point(
            motor_spec=context["motor_spec"],
            prop_spec=context["prop_spec"],
            prop_entry=context["prop_entry"],
            total_voltage=context["total_voltage"],
            rho=context["rho"],
            v_mps=v_mps,
            throttle_val=throttle_val,
        )
        return {
            "rpm": pt.rpm,
            "thrust": pt.thrust,
            "power": pt.power,
            "current": pt.current,
            "eta_p": pt.eta_p,
            "eta_m": pt.eta_m,
            "eta_sys": pt.eta_sys,
            "j": pt.j,
            "feasible": pt.feasible,
        }

    def _render_results(self, res: dict[str, Any]) -> None:
        # Decoupled event emission via StudioAPI Event Bus
        self._api.publish(StudioEvents.PROPULSION_RESULTS_UPDATED, res)
        self._api.publish(
            StudioEvents.PROPULSION_PLOT_SWEEP,
            {
                "x_label": res.get("x_label", ""),
                "x_values": res.get("x_values", []),
                "thrust_n": res.get("thrust_n", []),
                "power_w": res.get("power_w", []),
                "current_a": res.get("current_a", []),
                "rpm": res.get("rpm", []),
                "eta_total": res.get("eta_total", []),
                "eta_prop": res.get("eta_prop", []),
                "eta_motor": res.get("eta_motor", []),
                "clear_charts": res.get("clear_charts", False),
            },
        )
        self._api.clear_progress()

    def run_sweep(self, context: dict[str, Any]) -> dict[str, Any]:
        res = PropulsionSolverEngine.run_airspeed_sweep(
            context,
            progress_callback=self._api.report_progress,
        )
        self._render_results(res)
        return res

    def run_throttle(self, context: dict[str, Any]) -> dict[str, Any]:
        res = PropulsionSolverEngine.run_throttle_sweep(
            context,
            progress_callback=self._api.report_progress,
        )
        self._render_results(res)
        return res

    def run_operating_point(self, context: dict[str, Any]) -> dict[str, Any]:
        res = PropulsionSolverEngine.run_operating_point(
            context,
            progress_callback=self._api.report_progress,
        )
        self._render_results(res)
        return res

    def _show_feasibility_alert(self, context: dict[str, Any], res: dict[str, Any]) -> None:
        motor_spec = context["motor_spec"]
        motor_params = context["motor_params"]

        peak_curr = res.get("peak_current", 0.0)
        peak_pwr = res.get("peak_power", 0.0)
        max_curr_limit = motor_spec.current_max_a
        max_pwr_limit = float(motor_params.get("max_power") or 0.0)

        if peak_curr > max_curr_limit:
            over_pct = ((peak_curr / max(max_curr_limit, 1e-3)) - 1.0) * 100.0
            self._api.show_status(
                f"Current limit exceeded: peak {peak_curr:.1f} A vs "
                f"{max_curr_limit:.1f} A max ({over_pct:.0f}%)",
                "error",
                8000,
            )
            self.show_alert(
                severity="danger",
                title="Motor Current Limit Exceeded",
                message=(
                    f"PyThrust Warning: Peak current draw ({peak_curr:.1f} A) exceeds "
                    f"the motor continuous rating ({max_curr_limit:.1f} A) by {over_pct:.0f}%. "
                    f"The propeller ({context['diameter_in']:.1f}×{context['pitch_in']:.1f}) is overloading the motor at this battery voltage."
                ),
            )
        elif max_pwr_limit > 0 and peak_pwr > max_pwr_limit:
            over_pct = ((peak_pwr / max_pwr_limit) - 1.0) * 100.0
            self._api.show_status(
                f"Power limit exceeded: peak {peak_pwr:.1f} W vs "
                f"{max_pwr_limit:.1f} W max ({over_pct:.0f}%)",
                "warning",
                8000,
            )
            self.show_alert(
                severity="warning",
                title="Motor Power Limit Exceeded",
                message=(
                    f"PyThrust Warning: Peak electrical power ({peak_pwr:.1f} W) exceeds "
                    f"the motor maximum power rating ({max_pwr_limit:.1f} W) by {over_pct:.0f}%."
                ),
            )
        else:
            self._api.show_status(
                f"Analysis complete — feasible, peak {peak_curr:.1f} A "
                f"({max_curr_limit:.1f} A max)",
                "success",
                5000,
            )
            self.show_alert(
                severity="success",
                title="Operating Point Feasible",
                message=f"PyThrust: All operating points are within safe motor limits (Peak: {peak_curr:.1f} A / Max: {max_curr_limit:.1f} A).",
            )  # Helper Table Methods

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
