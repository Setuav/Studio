"""Controls Dock Widget for Flight Performance Analysis using Property Tables."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Qt
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

from plugins.electrical_propulsion.powertrain import (
    Powertrain,
    PowertrainError,
    build_powertrain,
    find_propulsion_system,
)
from setuav_studio.api import StudioAPI, StudioEvents
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.button import refresh_button_role, set_button_role
from setuav_studio.ui.widget.table import PropertyTableMixin

from .analysis_store import (
    EXTENSION_ID,
    append_analysis_entry,
    get_stored_performance_result,
    make_analysis_entry,
    performance_selection,
)
from .engine.models import FlightEnvelopeResult

_SOC_CELL_VOLTAGE = {"full": 4.20, "nominal": 3.70, "storage": 3.80}


class PerformanceControlsDock(PropertyTableMixin, QWidget):
    """Configuration and execution dock for Flight Performance Envelope Analysis."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("flight_performance.controls_widget")
        self._api = api
        self._is_running = False
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

        self.propulsion_table = self._property_table([("soc", "Battery State (SOC)")])

        self.combo_soc = QComboBox()
        self.combo_soc.addItem("100% Full (4.20 V/cell)", "full")
        self.combo_soc.addItem("Nominal (3.70 V/cell)", "nominal")
        self.combo_soc.addItem("Storage (3.80 V/cell)", "storage")

        self.propulsion_table.setCellWidget(0, 1, self.combo_soc)

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

        self._set_property_value(self.mass_table, "empty_mass", "0.0 g")
        self.spin_payload = self._set_property_spinbox(
            self.mass_table,
            "payload",
            0.0,
            min_val=0.0,
            max_val=100000.0,
            step=10.0,
            decimals=1,
            quantity="mass",
            unit="g",
            on_changed=lambda _v: self._update_takeoff_mass(),
        )
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

        self.spin_alt = self._set_property_spinbox(
            self.atmosphere_table,
            "altitude",
            0.0,
            min_val=-500.0,
            max_val=15000.0,
            step=10.0,
            decimals=1,
            quantity="length",
            unit="m",
            on_changed=lambda _v: self._update_density_preview(),
        )
        self.spin_temp = self._set_property_spinbox(
            self.atmosphere_table,
            "temperature",
            15.0,
            min_val=-50.0,
            max_val=60.0,
            step=1.0,
            decimals=1,
            suffix="°C",
            on_changed=lambda _v: self._update_density_preview(),
        )
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

        self.spin_vmin = self._set_property_spinbox(
            self.sweep_table,
            "v_min",
            8.0,
            min_val=1.0,
            max_val=100.0,
            step=1.0,
            decimals=1,
            quantity="velocity",
            unit="m/s",
        )
        self.spin_vmax = self._set_property_spinbox(
            self.sweep_table,
            "v_max",
            35.0,
            min_val=5.0,
            max_val=200.0,
            step=1.0,
            decimals=1,
            quantity="velocity",
            unit="m/s",
        )
        self.spin_vstep = self._set_property_spinbox(
            self.sweep_table,
            "v_step",
            0.25,
            min_val=0.05,
            max_val=5.0,
            step=0.05,
            decimals=2,
            quantity="velocity",
            unit="m/s",
        )
        self.spin_stall_margin = self._set_property_spinbox(
            self.sweep_table,
            "stall_margin",
            1.15,
            min_val=1.0,
            max_val=2.0,
            step=0.05,
            decimals=2,
            suffix="×",
        )

        layout.addWidget(self.sweep_table)

    def _create_actions_section(self) -> None:
        section = QWidget()
        layout = QHBoxLayout(section)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(6)

        self.btn_run = QPushButton("Run Analysis", self)
        set_button_role(self.btn_run, "primary", "fa6s.play")
        self.btn_run.clicked.connect(self._on_run_analysis)
        layout.addWidget(self.btn_run, 2)

        self.btn_cancel = QPushButton("Cancel", self)
        set_button_role(self.btn_cancel, "destructive", "mdi6.close-circle")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_analysis)
        layout.addWidget(self.btn_cancel, 1)

        self._content_layout.addWidget(section)

    def update_theme_style(self) -> None:
        for lbl, name in self._section_icons:
            set_label_icon(lbl, name)
        if hasattr(self, "btn_run"):
            refresh_button_role(self.btn_run)
        if hasattr(self, "btn_cancel"):
            refresh_button_role(self.btn_cancel)

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
            self._api.publish(StudioEvents.FLIGHT_PERFORMANCE_ANALYSIS_COMPLETED, stored)

    def _on_project_content_changed(self, project: Any) -> None:
        self._refresh_sources()

    def _refresh_sources(self) -> None:
        self._refresh_mass()
        self._update_density_preview()

    def _refresh_mass(self) -> None:
        proj = self._api.project if self._api else None
        if proj is None:
            self._empty_mass_kg = 0.0
            self._set_property_value(self.mass_table, "empty_mass", "0.0 g")
            self._update_takeoff_mass()
            return

        mass_props = proj.mass_properties
        self._empty_mass_kg = float(mass_props.mass_kg) if mass_props.mass_kg > 0 else 0.0
        empty_g = self._empty_mass_kg * 1000.0
        self._set_property_value(self.mass_table, "empty_mass", f"{empty_g:.1f} g")
        self._update_takeoff_mass()

    def _build_analysis_context(self) -> dict[str, Any] | None:
        proj = self._api.project if self._api else None
        if not proj:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return None

        # Takeoff Mass in kg = (Empty Mass (g) + Payload (g)) / 1000.0
        if self._empty_mass_kg <= 0.0:
            QMessageBox.warning(
                self,
                "Mass Properties Required",
                "Flight performance analysis requires a valid aircraft mass. "
                "Define component masses first.",
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

        try:
            powertrain = self._powertrain(components)
        except PowertrainError as exc:
            QMessageBox.warning(self, "Propulsion System Invalid", str(exc))
            return None

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
            "powertrain": powertrain,
            "usable_battery_ratio": 0.85,
        }

    def _powertrain(self, components: list[dict[str, Any]]) -> Powertrain | None:
        """Return the project's powertrain at the selected battery state of charge."""
        members = find_propulsion_system(components)
        if members is None:
            return None
        powertrain = build_powertrain(members)
        cells = members.batteries[0].get("parameters", {}).get("cell_count")
        if not isinstance(cells, int) or cells <= 0:
            raise PowertrainError("Battery has no cell count.")
        cell_voltage = _SOC_CELL_VOLTAGE[str(self.combo_soc.currentData())]
        return powertrain.with_battery_voltage(cell_voltage * cells)

    def _on_cancel_analysis(self) -> None:
        if hasattr(self, "_task_handle") and self._task_handle is not None:
            self._task_handle.cancel()

    def _on_run_analysis(self) -> None:
        if self._is_running:
            return

        context = self._build_analysis_context()
        if context is None:
            return

        self._is_running = True
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        if self._api:
            self._api.show_status("Analyzing performance…", "info", 0)
            self._api.report_progress(0, 100, "Performance")

        from .engine.solver import FlightPerformanceSolver

        def run_target(token: Any) -> FlightEnvelopeResult:
            def on_progress(curr: int, total: int, msg: str) -> None:
                token.check_cancelled()
                token.report_progress(curr, total, msg)

            token.report_progress(0, 100, "Starting flight performance analysis...")
            return FlightPerformanceSolver.run_analysis(
                context,
                progress_callback=on_progress,
            )

        self._task_handle = self._api.tasks.submit(
            name="Flight Performance",
            target=run_target,
            on_finished=self._on_analysis_finished,
            on_error=self._on_analysis_error,
            on_progress=lambda p: self._on_analysis_progress(p.current, p.total, p.message),
            on_cancelled=self._on_analysis_cancelled,
        )

    def _on_analysis_progress(self, current: int, total: int, msg: str) -> None:
        if self._api:
            self._api.report_progress(current, total, msg or "Running")

    def _on_analysis_finished(self, result: FlightEnvelopeResult) -> None:
        self._is_running = False
        self._task_handle = None
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        if self._api:
            self._api.clear_progress()
            proj = self._api.project
            entry = None
            if proj and not proj.read_only:
                entry = make_analysis_entry(result)
                self._api.edit_project_extension(
                    EXTENSION_ID,
                    f"Store flight performance analysis: {entry['name']}",
                    lambda ext: append_analysis_entry(ext, entry),
                )

            self._api.publish(StudioEvents.FLIGHT_PERFORMANCE_ANALYSIS_COMPLETED, result)
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

    def _on_analysis_cancelled(self) -> None:
        self._is_running = False
        self._task_handle = None
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if self._api:
            self._api.clear_progress()
            self._api.show_status("Flight performance analysis cancelled by user", "warning", 5000)

    def _on_analysis_error(self, err: object) -> None:
        self._is_running = False
        self._task_handle = None
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        err_msg = str(err)
        if self._api:
            self._api.clear_progress()
            self._api.show_status(f"Flight performance analysis failed: {err_msg}", "error", 8000)

        QMessageBox.critical(
            self,
            "Analysis Error",
            f"Flight performance analysis encountered an error:\n\n{err_msg}",
        )
