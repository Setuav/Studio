"""Controls Dock Widget for Flight Performance Analysis using Property Tables."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec

from plugins.electrical_propulsion.database import get_propeller_database
from plugins.electrical_propulsion.engine.solver import PropulsionSolverEngine
from plugins.weight_balance.engine.solver import WeightBalanceSolver
from setuav_studio.ui.buttons import refresh_button_role, set_button_role
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox
from setuav_studio.ui.property_tables import PropertyTableMixin
from setuav_studio_sdk import StudioAPI

from .analysis_store import (
    EXTENSION_ID,
    append_analysis_entry,
    get_stored_performance_result,
    make_analysis_entry,
    performance_selection,
)
from .engine.models import FlightEnvelopeResult
from .worker import FlightPerformanceWorker


class PerformanceControlsDock(PropertyTableMixin, QWidget):
    """Configuration and execution dock for Flight Performance Envelope Analysis."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("flight_performance.controls_widget")
        self._api = api
        self._is_running = False
        self._worker: FlightPerformanceWorker | None = None
        self._empty_mass_kg = 0.0
        self._current_density = 1.225
        self._section_icons: list[tuple[QLabel, str]] = []

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

        # Build property table sections
        self._create_propulsion_section()
        self._create_mass_section()
        self._create_atmosphere_section()
        self._create_sweep_section()
        self._create_actions_section()

        self._content_layout.addStretch(1)

        # Wire events
        if self._api:
            self._api.on_project_changed(self._on_project_changed)
            self._api.on_project_content_changed(self._on_project_content_changed)
            self._api.subscribe("weight_balance.analysis_completed", self._on_wb_completed)

        self._refresh_sources()

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(6)

        if icon_name:
            icon_label = QLabel()
            set_label_icon(icon_label, icon_name)
            self._section_icons.append((icon_label, icon_name))
            h_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        h_layout.addWidget(title_label)
        h_layout.addStretch(1)

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_propulsion_section(self) -> None:
        layout = self._create_section("Propulsion System", "fa6s.bolt")

        self.propulsion_table = self._property_table(
            [
                ("assembly", "Assembly"),
                ("soc", "Battery State (SOC)"),
            ]
        )

        self.combo_assembly = QComboBox()
        self.combo_soc = QComboBox()
        self.combo_soc.addItem("100% Full (4.20 V/cell)", "full")
        self.combo_soc.addItem("Nominal (3.70 V/cell)", "nominal")
        self.combo_soc.addItem("Storage (3.80 V/cell)", "storage")

        self.propulsion_table.setCellWidget(0, 1, self.combo_assembly)
        self.propulsion_table.setCellWidget(1, 1, self.combo_soc)

        layout.addWidget(self.propulsion_table)

    def _create_mass_section(self) -> None:
        layout = self._create_section("Aircraft Mass & Payload", "fa6s.scale-balanced")

        self.mass_table = self._property_table(
            [
                ("empty_mass", "Empty Mass"),
                ("payload", "Payload"),
                ("tow", "Takeoff Weight"),
            ]
        )

        self.spin_payload = NumericSpinBox(quantity="mass", suffix="g")
        self.spin_payload.setRange(0.0, 100000.0)
        self.spin_payload.setValue(0.0)
        self.spin_payload.setDecimals(1)
        self.spin_payload.setSingleStep(10.0)
        self.spin_payload.valueChanged.connect(self._update_takeoff_mass)

        self._set_property_value(self.mass_table, "empty_mass", "0.0 g")
        self.mass_table.setCellWidget(1, 1, self.spin_payload)
        self._set_property_value(self.mass_table, "tow", "0.0 g")

        layout.addWidget(self.mass_table)

    def _create_atmosphere_section(self) -> None:
        layout = self._create_section("Atmosphere & Environment", "fa6s.cloud-sun")

        self.atmosphere_table = self._property_table(
            [
                ("altitude", "Altitude"),
                ("temperature", "Temperature"),
                ("density", "Air Density"),
            ]
        )

        self.spin_alt = NumericSpinBox(quantity="length", suffix="m")
        self.spin_alt.setRange(-500.0, 15000.0)
        self.spin_alt.setValue(0.0)
        self.spin_alt.valueChanged.connect(self._update_density_preview)

        self.spin_temp = NumericSpinBox(suffix="°C")
        self.spin_temp.setRange(-50.0, 60.0)
        self.spin_temp.setValue(15.0)
        self.spin_temp.valueChanged.connect(self._update_density_preview)

        self.atmosphere_table.setCellWidget(0, 1, self.spin_alt)
        self.atmosphere_table.setCellWidget(1, 1, self.spin_temp)
        self._set_property_value(self.atmosphere_table, "density", "1.2250 kg/m³")

        layout.addWidget(self.atmosphere_table)

    def _create_sweep_section(self) -> None:
        layout = self._create_section("Velocity Sweep Envelope", "fa6s.arrows-left-right")

        self.sweep_table = self._property_table(
            [
                ("v_min", "Min Speed"),
                ("v_max", "Max Speed"),
                ("v_step", "Speed Step"),
                ("stall_margin", "Stall Margin"),
            ]
        )

        self.spin_vmin = NumericSpinBox(quantity="velocity", suffix="m/s")
        self.spin_vmin.setRange(1.0, 100.0)
        self.spin_vmin.setValue(8.0)

        self.spin_vmax = NumericSpinBox(quantity="velocity", suffix="m/s")
        self.spin_vmax.setRange(5.0, 200.0)
        self.spin_vmax.setValue(35.0)

        self.spin_vstep = NumericSpinBox(quantity="velocity", suffix="m/s")
        self.spin_vstep.setRange(0.05, 5.0)
        self.spin_vstep.setValue(0.25)
        self.spin_vstep.setDecimals(2)
        self.spin_vstep.setSingleStep(0.05)

        self.spin_stall_margin = NumericSpinBox(suffix="×")
        self.spin_stall_margin.setRange(1.0, 2.0)
        self.spin_stall_margin.setValue(1.15)
        self.spin_stall_margin.setDecimals(2)
        self.spin_stall_margin.setSingleStep(0.05)

        self.sweep_table.setCellWidget(0, 1, self.spin_vmin)
        self.sweep_table.setCellWidget(1, 1, self.spin_vmax)
        self.sweep_table.setCellWidget(2, 1, self.spin_vstep)
        self.sweep_table.setCellWidget(3, 1, self.spin_stall_margin)

        layout.addWidget(self.sweep_table)

    def _create_actions_section(self) -> None:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(4, 8, 4, 4)

        self.btn_run = QPushButton("Run Flight Performance Analysis", self)
        set_button_role(self.btn_run, "primary", "fa6s.play")
        self.btn_run.clicked.connect(self._on_run_analysis)
        layout.addWidget(self.btn_run)

        self._content_layout.addWidget(section)

    def update_theme_style(self) -> None:
        for lbl, name in self._section_icons:
            set_label_icon(lbl, name)
        if hasattr(self, "btn_run"):
            refresh_button_role(self.btn_run)

    def _update_takeoff_mass(self) -> None:
        empty_g = self._empty_mass_kg * 1000.0
        tow_g = empty_g + self.spin_payload.value()
        self._set_property_value(self.mass_table, "tow", f"{tow_g:.1f} g")

    def _update_density_preview(self) -> None:
        alt_m = self.spin_alt.value()
        temp_c = self.spin_temp.value()
        t_k = 273.15 + temp_c

        p0 = 101325.0
        if alt_m <= 11000.0:
            p_alt = p0 * ((1.0 - 0.0065 * alt_m / 288.15) ** 5.2561)
        else:
            p_alt = p0 * 0.22336 * math.exp(-0.0001577 * (alt_m - 11000.0))

        rho_calc = p_alt / (287.058 * t_k)
        self._current_density = max(0.1, min(rho_calc, 2.0))
        self._set_property_value(
            self.atmosphere_table, "density", f"{self._current_density:.4f} kg/m³"
        )

    def _on_project_changed(self, project: Any) -> None:
        self._refresh_sources()
        stored = get_stored_performance_result(project)
        if stored is not None and self._api:
            self._api.publish("flight_performance.analysis_completed", stored)

    def _on_project_content_changed(self, project: Any) -> None:
        self._refresh_sources()

    def _on_wb_completed(self, wb_result: Any) -> None:
        if wb_result and hasattr(wb_result, "total") and hasattr(wb_result.total, "mass_kg"):
            self._empty_mass_kg = float(wb_result.total.mass_kg)
            empty_g = self._empty_mass_kg * 1000.0
            self._set_property_value(self.mass_table, "empty_mass", f"{empty_g:.1f} g")
            self._update_takeoff_mass()

    def _refresh_sources(self) -> None:
        self._refresh_assemblies()
        self._refresh_mass()
        self._update_density_preview()

    def _refresh_assemblies(self) -> None:
        self.combo_assembly.blockSignals(True)
        self.combo_assembly.clear()
        proj = self._api.current_project if self._api else None
        if proj:
            assemblies = proj.data.get("assemblies", [])
            for a in assemblies:
                if (
                    a.get("type")
                    in {
                        "org.setuav.core:electric-propulsion-system",
                        "org.setuav.core:propulsion-system",
                    }
                    or "propulsion" in str(a.get("type", "")).lower()
                ):
                    self.combo_assembly.addItem(a.get("name", a.get("id")), a.get("id"))

        if self.combo_assembly.count() == 0:
            self.combo_assembly.addItem("Default / Isolated Components", "default")

        self.combo_assembly.blockSignals(False)

    def _refresh_mass(self) -> None:
        proj = self._api.current_project if self._api else None
        if not proj:
            self._empty_mass_kg = 0.0
            self._set_property_value(self.mass_table, "empty_mass", "0.0 g")
            self._update_takeoff_mass()
            return

        try:
            wb_solver = WeightBalanceSolver()
            wb_res = wb_solver.evaluate(proj)
            if wb_res and wb_res.total.mass_kg > 0:
                self._empty_mass_kg = float(wb_res.total.mass_kg)
                empty_g = self._empty_mass_kg * 1000.0
                self._set_property_value(self.mass_table, "empty_mass", f"{empty_g:.1f} g")
                self._update_takeoff_mass()
                return
        except Exception:
            pass

        comps = proj.data.get("components", [])
        total_g = sum(
            float(c.get("parameters", {}).get("mass", 0.0)) for c in comps if isinstance(c, dict)
        )
        self._empty_mass_kg = total_g / 1000.0 if total_g > 0 else 0.0
        empty_g = self._empty_mass_kg * 1000.0
        self._set_property_value(self.mass_table, "empty_mass", f"{empty_g:.1f} g")
        self._update_takeoff_mass()

    def _build_analysis_context(self) -> dict[str, Any] | None:
        proj = self._api.current_project if self._api else None
        if not proj:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return None

        # Takeoff Mass in kg = (Empty Mass (g) + Payload (g)) / 1000.0
        if self._empty_mass_kg <= 0.0:
            QMessageBox.warning(
                self,
                "Mass Properties Required",
                "Flight performance analysis requires a valid aircraft mass. "
                "Define component masses or run Weight Balance first.",
            )
            return None
        mass_g = (self._empty_mass_kg * 1000.0) + self.spin_payload.value()
        mass_kg = mass_g / 1000.0

        rho = self._current_density
        altitude = self.spin_alt.value()
        v_min = self.spin_vmin.value()
        v_max = self.spin_vmax.value()
        v_step = self.spin_vstep.value()
        stall_margin = self.spin_stall_margin.value()

        components = [c for c in proj.data.get("components", []) if isinstance(c, dict)]

        # Aerodynamic source (automated via AeroBuildup Engine)
        auto_run_aero = True
        polar_cl: list[float] | None = None
        polar_cd: list[float] | None = None
        area_m2: float = 0.50
        cl_max: float = 1.20
        cd_min: float = 0.035
        ld_max: float = 12.0

        # Propulsion components
        assembly_id = self.combo_assembly.currentData()
        assemblies = proj.data.get("assemblies", [])
        motor_comp, prop_comp, bat_comp = self._propulsion_components(
            components, assemblies, assembly_id
        )

        motor_spec: MotorSpec | None = None
        if motor_comp:
            m_params = motor_comp.get("parameters", {})
            kv = float(m_params.get("kv") or m_params.get("kv_rpm_per_v") or 900.0)
            r_motor = float(m_params.get("resistance") or m_params.get("resistance_ohm") or 0.035)
            i0 = float(m_params.get("no_load_current") or m_params.get("no_load_current_a") or 1.2)
            i_max = float(m_params.get("max_current") or m_params.get("current_max_a") or 45.0)
            motor_spec = MotorSpec(
                kv_rpm_per_v=kv, resistance_ohm=r_motor, no_load_current_a=i0, current_max_a=i_max
            )

        prop_spec: PropellerSpec | None = None
        prop_entry = None
        if prop_comp:
            p_params = prop_comp.get("parameters", {})
            d_raw = float(p_params.get("diameter_m") or p_params.get("diameter") or 0.3302)
            p_raw = float(p_params.get("pitch_m") or p_params.get("pitch") or 0.1651)
            diameter_m = d_raw / 1000.0 if d_raw > 2.0 else d_raw
            pitch_m = p_raw / 1000.0 if p_raw > 2.0 else p_raw
            diameter_in = diameter_m / 0.0254
            pitch_in = pitch_m / 0.0254
            blades = int(p_params.get("blades") or p_params.get("blade_count") or 2)

            prop_spec = PropellerSpec(diameter_m=diameter_m, pitch_m=pitch_m, blade_count=blades)
            prop_db = get_propeller_database()
            prop_name = str(prop_comp.get("name") or prop_comp.get("model") or "")
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
                prop_entry = PropulsionSolverEngine.fallback_propeller(
                    diameter_in, pitch_in, blades
                )

        bat_capacity_mah: float | None = None
        bat_voltage: float | None = None
        if bat_comp:
            b_params = bat_comp.get("parameters", {})
            pack = b_params.get("pack", {})
            cells = int(pack.get("series_count") or b_params.get("cell_count") or 4)
            bat_capacity_mah = float(pack.get("capacity") or b_params.get("capacity") or 5000.0)
            soc_choice = self.combo_soc.currentData()
            v_cell = 4.20 if soc_choice == "full" else (3.70 if soc_choice == "nominal" else 3.80)
            bat_voltage = v_cell * cells

        return {
            "project": proj,
            "components": components,
            "auto_run_aero": auto_run_aero,
            "altitude": altitude,
            "mass_kg": mass_kg,
            "area_m2": area_m2,
            "air_density": rho,
            "cl_max": cl_max,
            "cd_min": cd_min,
            "ld_max": ld_max,
            "v_min": v_min,
            "v_max": v_max,
            "v_step": v_step,
            "stall_margin": stall_margin,
            "polar_cl": polar_cl,
            "polar_cd": polar_cd,
            "motor_spec": motor_spec,
            "prop_spec": prop_spec,
            "prop_entry": prop_entry,
            "battery_capacity_mah": bat_capacity_mah,
            "battery_voltage": bat_voltage,
            "usable_battery_ratio": 0.85,
        }

    @staticmethod
    def _propulsion_components(
        components: list[dict[str, Any]], assemblies: list[Any], assembly_id: object
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        assembly = next(
            (
                item
                for item in assemblies
                if isinstance(item, dict) and item.get("id") == assembly_id
            ),
            None,
        )
        if assembly is not None:
            members = assembly.get("members")
            members = members if isinstance(members, dict) else {}
            by_id = {item.get("id"): item for item in components}
            motors = members.get("motors") or []
            propulsors = members.get("propulsors") or []
            return (
                by_id.get(motors[0]) if motors else None,
                by_id.get(propulsors[0]) if propulsors else None,
                by_id.get(members.get("battery")),
            )

        motor = propulsor = battery = None
        for component in components:
            component_type = str(component.get("type", ""))
            if "motor" in component_type and motor is None:
                motor = component
            elif ("propeller" in component_type or "rotor" in component_type) and propulsor is None:
                propulsor = component
            elif "battery" in component_type and battery is None:
                battery = component
        return motor, propulsor, battery

    def _on_run_analysis(self) -> None:
        if self._is_running:
            return

        context = self._build_analysis_context()
        if context is None:
            return

        self._is_running = True
        self.btn_run.setEnabled(False)
        if self._api:
            self._api.show_status("Analyzing performance…", "info", 0)
            self._api.report_progress(0, 100, "Performance")

        self._worker = FlightPerformanceWorker(context)
        self._worker.signals.progress.connect(self._on_analysis_progress)
        self._worker.signals.finished.connect(self._on_analysis_finished)
        self._worker.signals.error.connect(self._on_analysis_error)

        QThreadPool.globalInstance().start(self._worker)

    def _on_analysis_progress(self, current: int, total: int, msg: str) -> None:
        if self._api:
            self._api.report_progress(current, total, msg or "Running")

    def _on_analysis_finished(self, result: FlightEnvelopeResult) -> None:
        self._is_running = False
        self._worker = None
        self.btn_run.setEnabled(True)

        if self._api:
            self._api.clear_progress()
            proj = self._api.current_project
            entry = None
            if proj and not proj.read_only:
                entry = make_analysis_entry(result)
                self._api.edit_project_extension(
                    EXTENSION_ID,
                    f"Store flight performance analysis: {entry['name']}",
                    lambda ext: append_analysis_entry(ext, entry),
                )

            self._api.publish("flight_performance.analysis_completed", result)
            if entry is not None:
                self._api.set_selection(performance_selection(str(entry["id"])))

            m = result.metrics
            o = result.optimal_speeds
            self._api.show_status(
                f"Coupled Performance complete: V_stall={m.stall_speed:.1f} m/s, "
                f"V_cruise={o.best_range:.1f} m/s, Max Range={m.max_range_km:.1f} km, "
                f"ROC_max={m.max_rate_of_climb:.2f} m/s",
                "success",
                8000,
            )

    def _on_analysis_error(self, err_msg: str) -> None:
        self._is_running = False
        self._worker = None
        self.btn_run.setEnabled(True)
        if self._api:
            self._api.clear_progress()
            self._api.show_status(f"Flight performance analysis failed: {err_msg}", "error", 8000)

        QMessageBox.critical(
            self,
            "Analysis Error",
            f"Flight performance analysis encountered an error:\n\n{err_msg}",
        )
