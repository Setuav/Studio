"""Aerodynamic Analysis Controls dock widget."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.buttons import refresh_button_role, set_button_role, set_native_button
from setuav_studio.ui.numeric_spinbox import NumericSpinBox
from setuav_studio.ui.property_tables import PropertyTableMixin
from setuav_studio.ui.theme import tokens

from .engine.base import (
    AeroEngine,
    AeroResult,
    AnalysisMethod,
    FlightCondition,
    SweepType,
)
from .engine.aerosandbox_engine import AeroSandboxEngine
from .worker import AnalysisWorker


class AeroControlsDock(PropertyTableMixin, QWidget):
    """Configuration and execution dock for Aerodynamic Analysis."""

    def __init__(
        self,
        api: StudioAPI,
        on_result_callback: Callable[[AeroResult], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.controls_widget")
        self._api = api
        self._tokens = tokens()
        self._on_result_callback = on_result_callback
        self._is_running = False

        # Available engines
        self._engines: dict[str, AeroEngine] = {
            "AeroSandbox": AeroSandboxEngine(),
        }

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
        self._create_engine_section()
        self._create_conditions_section()
        self._create_sweep_section()
        self._create_actions_section()

        self._content_layout.addStretch(1)

    def set_result_callback(self, callback: Callable[[AeroResult], None]) -> None:
        self._on_result_callback = callback

    def update_theme_style(self) -> None:
        for lbl, name in self._section_icons:
            set_label_icon(lbl, name)
        if hasattr(self, "btn_run"):
            refresh_button_role(self.btn_run)
        if hasattr(self, "btn_save_config"):
            refresh_button_role(self.btn_save_config)

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

    def _create_engine_section(self) -> None:
        layout = self._create_section("Mesh & Discretization", "fa6s.gears")

        self.engine_table = self._property_table([
            ("span_res", "Spanwise Panels"),
            ("chord_res", "Chordwise Panels"),
            ("spacing", "Panel Spacing"),
        ])

        self.spin_span_res = NumericSpinBox()
        self.spin_span_res.setDecimals(0)
        self.spin_span_res.setRange(4, 50)
        self.spin_span_res.setValue(12)

        self.spin_chord_res = NumericSpinBox()
        self.spin_chord_res.setDecimals(0)
        self.spin_chord_res.setRange(2, 30)
        self.spin_chord_res.setValue(8)

        self.combo_spacing = QComboBox()
        self.combo_spacing.addItem("Cosine (Tip Clustered)", "cosine")
        self.combo_spacing.addItem("Uniform (Equispaced)", "uniform")

        self.engine_table.setCellWidget(0, 1, self.spin_span_res)
        self.engine_table.setCellWidget(1, 1, self.spin_chord_res)
        self.engine_table.setCellWidget(2, 1, self.combo_spacing)

        layout.addWidget(self.engine_table)

    def _create_conditions_section(self) -> None:
        layout = self._create_section("Flight Conditions", "fa6s.wind")

        self.conditions_table = self._property_table([
            ("velocity", "Airspeed (V)"),
            ("altitude", "Altitude (MSL)"),
            ("ref_alpha", "Reference AoA (α)"),
            ("ref_beta", "Sideslip Angle (β)"),
        ])

        self.spin_velocity = NumericSpinBox()
        self.spin_velocity.setRange(1.0, 300.0)
        self.spin_velocity.setValue(25.0)
        self.spin_velocity.setSuffix(" m/s")

        self.spin_altitude = NumericSpinBox()
        self.spin_altitude.setRange(0.0, 15000.0)
        self.spin_altitude.setValue(0.0)
        self.spin_altitude.setSuffix(" m")

        self.spin_ref_alpha = NumericSpinBox()
        self.spin_ref_alpha.setRange(-20.0, 30.0)
        self.spin_ref_alpha.setValue(2.0)
        self.spin_ref_alpha.setSuffix(" °")

        self.spin_ref_beta = NumericSpinBox()
        self.spin_ref_beta.setRange(-45.0, 45.0)
        self.spin_ref_beta.setValue(0.0)
        self.spin_ref_beta.setSuffix(" °")

        self.conditions_table.setCellWidget(0, 1, self.spin_velocity)
        self.conditions_table.setCellWidget(1, 1, self.spin_altitude)
        self.conditions_table.setCellWidget(2, 1, self.spin_ref_alpha)
        self.conditions_table.setCellWidget(3, 1, self.spin_ref_beta)

        layout.addWidget(self.conditions_table)

    def _create_sweep_section(self) -> None:
        layout = self._create_section("Parametric Sweep Range", "fa6s.arrows-left-right")

        self.sweep_table = self._property_table([
            ("mode", "Sweep Mode"),
            ("ctrl_surface", "Control Surface"),
            ("sweep_min", "Primary Start"),
            ("sweep_max", "Primary End"),
            ("sweep_steps", "Primary Steps"),
            ("sec_min", "Secondary Start"),
            ("sec_max", "Secondary End"),
            ("sec_steps", "Secondary Steps"),
        ])

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Dual Alpha + Beta", SweepType.DUAL_ALPHA_BETA)
        self.combo_mode.addItem("Alpha Sweep", SweepType.ALPHA)
        self.combo_mode.addItem("Beta Sweep", SweepType.BETA)
        self.combo_mode.addItem("Control Deflection Sweep", SweepType.CONTROL_DEFLECTION)
        self.combo_mode.addItem("Airspeed Sweep", SweepType.VELOCITY)
        self.combo_mode.addItem("Altitude Sweep", SweepType.ALTITUDE)
        self.combo_mode.addItem("Single Point", None)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        self.combo_ctrl = QComboBox()
        self.combo_ctrl.addItem("Elevator", "elevator")
        self.combo_ctrl.addItem("Aileron", "aileron")
        self.combo_ctrl.addItem("Rudder", "rudder")
        self.combo_ctrl.addItem("Flap", "flap")

        self.spin_sweep_min = NumericSpinBox()
        self.spin_sweep_min.setRange(-100.0, 20000.0)
        self.spin_sweep_min.setValue(-10.0)
        self.spin_sweep_min.setSuffix(" °")

        self.spin_sweep_max = NumericSpinBox()
        self.spin_sweep_max.setRange(-100.0, 20000.0)
        self.spin_sweep_max.setValue(18.0)
        self.spin_sweep_max.setSuffix(" °")

        self.spin_sweep_steps = NumericSpinBox()
        self.spin_sweep_steps.setDecimals(0)
        self.spin_sweep_steps.setRange(2, 100)
        self.spin_sweep_steps.setValue(29)

        self.spin_sec_min = NumericSpinBox()
        self.spin_sec_min.setRange(-45.0, 45.0)
        self.spin_sec_min.setValue(-12.0)
        self.spin_sec_min.setSuffix(" °")

        self.spin_sec_max = NumericSpinBox()
        self.spin_sec_max.setRange(-45.0, 45.0)
        self.spin_sec_max.setValue(12.0)
        self.spin_sec_max.setSuffix(" °")

        self.spin_sec_steps = NumericSpinBox()
        self.spin_sec_steps.setDecimals(0)
        self.spin_sec_steps.setRange(2, 50)
        self.spin_sec_steps.setValue(13)

        self.sweep_table.setCellWidget(0, 1, self.combo_mode)
        self.sweep_table.setCellWidget(1, 1, self.combo_ctrl)
        self.sweep_table.setCellWidget(2, 1, self.spin_sweep_min)
        self.sweep_table.setCellWidget(3, 1, self.spin_sweep_max)
        self.sweep_table.setCellWidget(4, 1, self.spin_sweep_steps)
        self.sweep_table.setCellWidget(5, 1, self.spin_sec_min)
        self.sweep_table.setCellWidget(6, 1, self.spin_sec_max)
        self.sweep_table.setCellWidget(7, 1, self.spin_sec_steps)

        layout.addWidget(self.sweep_table)
        self._on_mode_changed()

    def _on_mode_changed(self) -> None:
        sweep_data = self.combo_mode.currentData()
        is_sweep = sweep_data is not None

        self.spin_sweep_min.setEnabled(is_sweep)
        self.spin_sweep_max.setEnabled(is_sweep)
        self.spin_sweep_steps.setEnabled(is_sweep)

        is_ctrl = sweep_data == SweepType.CONTROL_DEFLECTION
        self.combo_ctrl.setEnabled(is_ctrl)
        self.sweep_table.setRowHidden(1, not is_ctrl)

        is_dual = sweep_data == SweepType.DUAL_ALPHA_BETA
        self.sweep_table.setRowHidden(5, not is_dual)
        self.sweep_table.setRowHidden(6, not is_dual)
        self.sweep_table.setRowHidden(7, not is_dual)

        # Update labels dynamically
        item_p_min = self.sweep_table.item(2, 0)
        item_p_max = self.sweep_table.item(3, 0)
        item_p_steps = self.sweep_table.item(4, 0)
        item_s_min = self.sweep_table.item(5, 0)
        item_s_max = self.sweep_table.item(6, 0)
        item_s_steps = self.sweep_table.item(7, 0)

        if is_dual:
            if item_p_min:
                item_p_min.setText("Alpha Start")
            if item_p_max:
                item_p_max.setText("Alpha End")
            if item_p_steps:
                item_p_steps.setText("Alpha Steps")
            if item_s_min:
                item_s_min.setText("Beta Start")
            if item_s_max:
                item_s_max.setText("Beta End")
            if item_s_steps:
                item_s_steps.setText("Beta Steps")

            self.spin_sweep_min.setSuffix(" °")
            self.spin_sweep_max.setSuffix(" °")
            self.spin_sec_min.setSuffix(" °")
            self.spin_sec_max.setSuffix(" °")

            self.spin_sweep_min.setValue(-10.0)
            self.spin_sweep_max.setValue(18.0)
            self.spin_sweep_steps.setValue(29)
            self.spin_sec_steps.setValue(13)
            self.spin_sec_min.setValue(-12.0)
            self.spin_sec_max.setValue(12.0)

        elif sweep_data == SweepType.ALPHA:
            if item_p_min:
                item_p_min.setText("Alpha Start")
            if item_p_max:
                item_p_max.setText("Alpha End")
            if item_p_steps:
                item_p_steps.setText("Alpha Steps")
            self.spin_sweep_min.setSuffix(" °")
            self.spin_sweep_max.setSuffix(" °")
            self.spin_sweep_min.setValue(-10.0)
            self.spin_sweep_max.setValue(18.0)
            self.spin_sweep_steps.setValue(29)

        elif sweep_data == SweepType.BETA:
            if item_p_min:
                item_p_min.setText("Beta Start")
            if item_p_max:
                item_p_max.setText("Beta End")
            if item_p_steps:
                item_p_steps.setText("Beta Steps")
            self.spin_sweep_min.setSuffix(" °")
            self.spin_sweep_max.setSuffix(" °")
            self.spin_sweep_min.setValue(-15.0)
            self.spin_sweep_max.setValue(15.0)
            self.spin_sweep_steps.setValue(31)

        elif sweep_data == SweepType.CONTROL_DEFLECTION:
            if item_p_min:
                item_p_min.setText("Deflection Start")
            if item_p_max:
                item_p_max.setText("Deflection End")
            if item_p_steps:
                item_p_steps.setText("Deflection Steps")
            self.spin_sweep_min.setSuffix(" °")
            self.spin_sweep_max.setSuffix(" °")
            self.spin_sweep_min.setValue(-20.0)
            self.spin_sweep_max.setValue(20.0)
            self.spin_sweep_steps.setValue(21)

        elif sweep_data == SweepType.VELOCITY:
            if item_p_min:
                item_p_min.setText("Velocity Start")
            if item_p_max:
                item_p_max.setText("Velocity End")
            if item_p_steps:
                item_p_steps.setText("Velocity Steps")
            self.spin_sweep_min.setSuffix(" m/s")
            self.spin_sweep_max.setSuffix(" m/s")
            self.spin_sweep_min.setValue(10.0)
            self.spin_sweep_max.setValue(45.0)
            self.spin_sweep_steps.setValue(15)

        elif sweep_data == SweepType.ALTITUDE:
            if item_p_min:
                item_p_min.setText("Altitude Start")
            if item_p_max:
                item_p_max.setText("Altitude End")
            if item_p_steps:
                item_p_steps.setText("Altitude Steps")
            self.spin_sweep_min.setSuffix(" m")
            self.spin_sweep_max.setSuffix(" m")
            self.spin_sweep_min.setValue(0.0)
            self.spin_sweep_max.setValue(4000.0)
            self.spin_sweep_steps.setValue(9)

    def _create_actions_section(self) -> None:
        layout = self._create_section("Actions", "fa6s.play")

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)

        self.btn_run = QPushButton(" Run")
        set_button_role(self.btn_run, "primary", "fa6s.play")
        self.btn_run.clicked.connect(self.run_analysis)
        btn_layout.addWidget(self.btn_run)

        self.btn_save_config = QPushButton(" Save Configuration")
        set_native_button(self.btn_save_config, "fa6s.floppy-disk")
        self.btn_save_config.clicked.connect(self._save_configuration)
        btn_layout.addWidget(self.btn_save_config)

        layout.addLayout(btn_layout)

    def run_analysis(self) -> None:
        if self._is_running:
            return

        engine = self._engines.get("AeroSandbox")
        if not engine or not engine.is_available():
            QMessageBox.warning(
                self,
                "Engine Not Available",
                "AeroSandbox is not available or required dependencies are missing.\n"
                "Please run: pip install aerosandbox",
            )
            return

        project = self._api.current_project
        if not project or not project.data:
            QMessageBox.information(
                self,
                "No Project Open",
                "Please open or create a project before running aerodynamic analysis.",
            )
            return

        components = project.data.get("components", [])
        has_lifting_surface = any(
            isinstance(c, dict) and c.get("type") == "org.setuav.core:lifting-surface"
            for c in components
        )
        if not has_lifting_surface:
            QMessageBox.warning(
                self,
                "Missing Lifting Surface",
                "The current project does not contain any 'lifting-surface' components to analyze.",
            )
            return

        # Build FlightCondition with generalized sweep mode
        sweep_data = self.combo_mode.currentData()
        is_sweep = sweep_data is not None

        if sweep_data == SweepType.DUAL_ALPHA_BETA:
            sweep_type = SweepType.DUAL_ALPHA_BETA
            sweep_var = "alpha"
            secondary_var = "beta"
        elif sweep_data == SweepType.ALPHA:
            sweep_type = SweepType.ALPHA
            sweep_var = "alpha"
            secondary_var = None
        elif sweep_data == SweepType.BETA:
            sweep_type = SweepType.BETA
            sweep_var = "beta"
            secondary_var = None
        elif sweep_data == SweepType.CONTROL_DEFLECTION:
            sweep_type = SweepType.CONTROL_DEFLECTION
            sweep_var = str(self.combo_ctrl.currentData() or "elevator")
            secondary_var = None
        elif sweep_data == SweepType.VELOCITY:
            sweep_type = SweepType.VELOCITY
            sweep_var = "velocity"
            secondary_var = None
        elif sweep_data == SweepType.ALTITUDE:
            sweep_type = SweepType.ALTITUDE
            sweep_var = "altitude"
            secondary_var = None
        else:
            sweep_type = SweepType.ALPHA
            sweep_var = "alpha"
            secondary_var = None

        s_min = float(self.spin_sweep_min.value())
        s_max = float(self.spin_sweep_max.value())
        s_steps = int(self.spin_sweep_steps.value()) if is_sweep else 1

        sec_min = float(self.spin_sec_min.value())
        sec_max = float(self.spin_sec_max.value())
        sec_steps = int(self.spin_sec_steps.value())

        condition = FlightCondition(
            velocity=float(self.spin_velocity.value()),
            altitude=float(self.spin_altitude.value()),
            alpha=float(self.spin_ref_alpha.value()),
            beta=float(self.spin_ref_beta.value()),
            sweep_type=sweep_type,
            sweep_variable=sweep_var,
            sweep_min=s_min,
            sweep_max=s_max,
            sweep_steps=s_steps,
            secondary_variable=secondary_var,
            secondary_min=sec_min,
            secondary_max=sec_max,
            secondary_steps=sec_steps,
            alpha_min=s_min if sweep_type in (SweepType.ALPHA, SweepType.DUAL_ALPHA_BETA) else -10.0,
            alpha_max=s_max if sweep_type in (SweepType.ALPHA, SweepType.DUAL_ALPHA_BETA) else 18.0,
            alpha_steps=s_steps if sweep_type in (SweepType.ALPHA, SweepType.DUAL_ALPHA_BETA) else 1,
            beta_min=sec_min if sweep_type == SweepType.DUAL_ALPHA_BETA else (s_min if sweep_type == SweepType.BETA else -15.0),
            beta_max=sec_max if sweep_type == SweepType.DUAL_ALPHA_BETA else (s_max if sweep_type == SweepType.BETA else 15.0),
            beta_steps=sec_steps if sweep_type == SweepType.DUAL_ALPHA_BETA else (s_steps if sweep_type == SweepType.BETA else 1),
        )

        method = AnalysisMethod.COMPREHENSIVE

        settings = {
            "spanwise_resolution": int(self.spin_span_res.value()),
            "chordwise_resolution": int(self.spin_chord_res.value()),
            "spanwise_spacing": str(self.combo_spacing.currentData() or "cosine"),
            "chordwise_spacing": str(self.combo_spacing.currentData() or "cosine"),
            "include_wave_drag": True,
            "compressibility_correction": True,
        }

        self._is_running = True
        self.btn_run.setEnabled(False)
        self._api.report_progress(1, 100, "Aerodynamics")
        self._api.show_status("Running aerodynamic analysis in background...", "info")

        worker = AnalysisWorker(
            engine=engine,
            components=components,
            condition=condition,
            method=method,
            settings=settings,
        )
        worker.signals.finished.connect(self._on_analysis_finished)
        worker.signals.error.connect(self._on_analysis_error)
        worker.signals.progress.connect(self._on_analysis_progress)

        QThreadPool.globalInstance().start(worker)

    def _on_analysis_progress(self, current: int, total: int, msg: str) -> None:
        label = f"Aerodynamics ({msg})" if msg else "Aerodynamics"
        self._api.report_progress(current, total, label)

    def _on_analysis_finished(self, result: AeroResult) -> None:
        self._is_running = False
        self.btn_run.setEnabled(True)
        self._api.clear_progress()
        self._api.show_status(
            f"Aerodynamic analysis complete: CL_max={result.cl_max:.2f} @ {result.cl_max_alpha:.1f}°, "
            f"L/D_max={result.ld_max:.1f}",
            "success",
        )

        if self._on_result_callback:
            self._on_result_callback(result)

    def _on_analysis_error(self, err_msg: str) -> None:
        self._is_running = False
        self.btn_run.setEnabled(True)
        self._api.clear_progress()
        self._api.show_status(f"Aerodynamic analysis failed: {err_msg}", "error")
        QMessageBox.critical(
            self,
            "Analysis Error",
            f"Aerodynamic analysis encountered an error:\n\n{err_msg}",
        )

    def _save_configuration(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Save Analysis Configuration",
            "Configuration Name:",
            text="cruise_aero",
        )
        if not ok or not name.strip():
            return

        clean_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name.strip())

        config_data = {
            "$schema": "https://schemas.setuav.org/core/analysis.schema.json",
            "name": name.strip(),
            "type": "org.setuav.aerosandbox:steady-aero",
            "plugin": {
                "id": "org.setuav.studio.aerodynamics",
                "version": "^0.1.0",
            },
            "settings": {
                "velocity": {"value": float(self.spin_velocity.value()), "unit": "m/s"},
                "altitude": {"value": float(self.spin_altitude.value()), "unit": "m"},
                "angle_of_attack": {"value": float(self.spin_ref_alpha.value()), "unit": "deg"},
                "method": "comprehensive",
            },
        }

        # If project has a folder path, save to analyses/
        project = self._api.current_project
        save_dir = Path.cwd()
        if project and project.file_path:
            save_dir = Path(project.file_path).parent / "analyses"
            save_dir.mkdir(parents=True, exist_ok=True)

        target_file = save_dir / f"{clean_name}.json"
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        self._api.show_status(f"Saved analysis configuration to {target_file}", "success")
