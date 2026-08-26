"""Aerodynamic Analysis Controls dock widget."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QCloseEvent, QFont
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
from setuav_studio.ui.buttons import refresh_button_role, set_button_role, set_native_button
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox
from setuav_studio.ui.property_tables import PropertyTableMixin
from setuav_studio.ui.theme import tokens

from .engine.aerosandbox_engine import AeroSandboxEngine
from .engine.base import (
    AeroEngine,
    AeroResult,
    AnalysisMethod,
    FlightCondition,
    SweepType,
    control_channels_for_components,
)
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
        self._on_solver_changed()
        self._create_actions_section()

        self._content_layout.addStretch(1)
        self._api.on_project_changed(self._on_project_changed)
        self._api.on_project_content_changed(self._on_project_changed)
        self._refresh_control_channels()

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
        layout = self._create_section("Solver & Mesh", "fa6s.gears")

        self.engine_table = self._property_table(
            [
                ("solver", "Solver Engine"),
                ("span_res", "Spanwise Panels"),
                ("chord_res", "Chordwise Panels"),
                ("spacing", "Panel Spacing"),
            ]
        )

        self.combo_solver = QComboBox()
        self.combo_solver.addItem("AeroBuildup (Default)", AnalysisMethod.AERO_BUILDUP)
        self.combo_solver.addItem("Vortex Lattice Method (VLM)", AnalysisMethod.VLM)
        self.combo_solver.addItem("Lifting Line Theory (LLT)", AnalysisMethod.LIFTING_LINE)

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

        self.combo_solver.currentIndexChanged.connect(self._on_solver_changed)

        self.engine_table.setCellWidget(0, 1, self.combo_solver)
        self.engine_table.setCellWidget(1, 1, self.spin_span_res)
        self.engine_table.setCellWidget(2, 1, self.spin_chord_res)
        self.engine_table.setCellWidget(3, 1, self.combo_spacing)

        layout.addWidget(self.engine_table)

    def _on_solver_changed(self) -> None:
        method = self.combo_solver.currentData()
        uses_span_mesh = method in {
            AnalysisMethod.VLM,
            AnalysisMethod.LIFTING_LINE,
        }
        self.engine_table.setRowHidden(1, not uses_span_mesh)
        self.engine_table.setRowHidden(2, method != AnalysisMethod.VLM)
        self.engine_table.setRowHidden(3, not uses_span_mesh)

        self.spin_span_res.setMaximum(50)
        if hasattr(self, "combo_mode"):
            self.combo_mode.setEnabled(True)

    def _create_conditions_section(self) -> None:
        layout = self._create_section("Flight Conditions", "fa6s.wind")

        self.conditions_table = self._property_table(
            [
                ("velocity", "Airspeed (V)"),
                ("altitude", "Altitude (MSL)"),
                ("ref_alpha", "Reference AoA (α)"),
                ("ref_beta", "Sideslip Angle (β)"),
            ]
        )

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
        layout = self._create_section("Parametric Analysis", "fa6s.arrows-left-right")

        self.sweep_table = self._property_table(
            [
                ("mode", "Sweep Mode"),
                ("ctrl_surface", "Control Channel"),
                ("sweep_min", "Primary Start"),
                ("sweep_max", "Primary End"),
                ("sweep_steps", "Primary Steps"),
                ("sec_min", "Secondary Start"),
                ("sec_max", "Secondary End"),
                ("sec_steps", "Secondary Steps"),
            ]
        )

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Alpha + Beta (Dual)", SweepType.DUAL_ALPHA_BETA)
        self.combo_mode.addItem("Alpha x Beta (Grid)", SweepType.MULTI_GRID)
        self.combo_mode.addItem("Alpha Sweep", SweepType.ALPHA)
        self.combo_mode.addItem("Beta Sweep", SweepType.BETA)
        self.combo_mode.addItem("Control Channel Analysis", SweepType.CONTROL_DEFLECTION)
        self.combo_mode.addItem("Single Point", None)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        self.combo_ctrl = QComboBox()
        self._available_control_channels: tuple[str, ...] = ()

        self.spin_sweep_min = NumericSpinBox()
        self.spin_sweep_min.setRange(-100.0, 100.0)
        self.spin_sweep_min.setValue(-10.0)
        self.spin_sweep_min.setSuffix(" °")

        self.spin_sweep_max = NumericSpinBox()
        self.spin_sweep_max.setRange(-100.0, 100.0)
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
        sweep_type = self.combo_mode.currentData()
        is_sweep = sweep_type is not None
        for widget in (
            self.spin_sweep_min,
            self.spin_sweep_max,
            self.spin_sweep_steps,
        ):
            widget.setEnabled(is_sweep)

        is_control = sweep_type == SweepType.CONTROL_DEFLECTION
        self.combo_ctrl.setEnabled(is_control and bool(self._available_control_channels))
        self.sweep_table.setRowHidden(1, not is_control)

        is_alpha_beta = sweep_type in (
            SweepType.DUAL_ALPHA_BETA,
            SweepType.MULTI_GRID,
        )
        for row in (5, 6, 7):
            self.sweep_table.setRowHidden(row, not is_alpha_beta)

        if is_alpha_beta:
            self._configure_alpha_beta_sweep(sweep_type)
        elif sweep_type == SweepType.ALPHA:
            self._configure_primary_sweep("Alpha", -10.0, 18.0, 29)
        elif sweep_type == SweepType.BETA:
            self._configure_primary_sweep("Beta", -15.0, 15.0, 31)
        elif is_control:
            self._configure_primary_sweep("Deflection", -20.0, 20.0, 21)

    def _configure_alpha_beta_sweep(self, sweep_type: object) -> None:
        self._set_sweep_labels("Alpha", "Beta")
        self._set_angle_suffixes(include_secondary=True)
        if sweep_type == SweepType.MULTI_GRID:
            self._set_primary_sweep_values(-8.0, 16.0, 13)
            self._set_secondary_sweep_values(-10.0, 10.0, 5)
        else:
            self._set_primary_sweep_values(-10.0, 18.0, 29)
            self._set_secondary_sweep_values(-12.0, 12.0, 13)

    def _configure_primary_sweep(
        self,
        label: str,
        minimum: float,
        maximum: float,
        steps: int,
    ) -> None:
        self._set_sweep_labels(label)
        self._set_angle_suffixes(include_secondary=False)
        self._set_primary_sweep_values(minimum, maximum, steps)

    def _set_sweep_labels(
        self,
        primary: str,
        secondary: str | None = None,
    ) -> None:
        labels = {
            2: f"{primary} Start",
            3: f"{primary} End",
            4: f"{primary} Steps",
        }
        if secondary is not None:
            labels.update(
                {
                    5: f"{secondary} Start",
                    6: f"{secondary} End",
                    7: f"{secondary} Steps",
                }
            )
        for row, text in labels.items():
            item = self.sweep_table.item(row, 0)
            if item is not None:
                item.setText(text)

    def _set_angle_suffixes(self, *, include_secondary: bool) -> None:
        self.spin_sweep_min.setSuffix(" °")
        self.spin_sweep_max.setSuffix(" °")
        if include_secondary:
            self.spin_sec_min.setSuffix(" °")
            self.spin_sec_max.setSuffix(" °")

    def _set_primary_sweep_values(
        self,
        minimum: float,
        maximum: float,
        steps: int,
    ) -> None:
        self.spin_sweep_min.setValue(minimum)
        self.spin_sweep_max.setValue(maximum)
        self.spin_sweep_steps.setValue(steps)

    def _set_secondary_sweep_values(
        self,
        minimum: float,
        maximum: float,
        steps: int,
    ) -> None:
        self.spin_sec_min.setValue(minimum)
        self.spin_sec_max.setValue(maximum)
        self.spin_sec_steps.setValue(steps)

    def _on_project_changed(self, _project: object) -> None:
        self._refresh_control_channels()

    def _refresh_control_channels(self) -> None:
        project = self._api.current_project
        components = (
            project.data.get("components", [])
            if project is not None and isinstance(project.data, dict)
            else []
        )
        channels = control_channels_for_components(components)
        current = self.combo_ctrl.currentData()
        labels = {
            "elevator": "Elevator",
            "aileron": "Aileron",
            "rudder": "Rudder",
            "flap": "Flap",
        }
        self.combo_ctrl.blockSignals(True)
        self.combo_ctrl.clear()
        for channel in channels:
            self.combo_ctrl.addItem(labels[channel], channel)
        if not channels:
            self.combo_ctrl.addItem("No control channels", None)
        elif current in channels:
            self.combo_ctrl.setCurrentIndex(self.combo_ctrl.findData(current))
        self.combo_ctrl.blockSignals(False)
        self._available_control_channels = channels
        self.combo_ctrl.setEnabled(
            self.combo_mode.currentData() == SweepType.CONTROL_DEFLECTION and bool(channels)
        )

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
        sweep = self._resolve_sweep(sweep_data)
        if sweep is None:
            return
        sweep_type, sweep_var, secondary_var = sweep

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
            alpha_min=s_min
            if sweep_type in (SweepType.ALPHA, SweepType.DUAL_ALPHA_BETA, SweepType.MULTI_GRID)
            else -10.0,
            alpha_max=s_max
            if sweep_type in (SweepType.ALPHA, SweepType.DUAL_ALPHA_BETA, SweepType.MULTI_GRID)
            else 18.0,
            alpha_steps=s_steps
            if sweep_type in (SweepType.ALPHA, SweepType.DUAL_ALPHA_BETA, SweepType.MULTI_GRID)
            else 1,
            beta_min=sec_min
            if sweep_type in (SweepType.DUAL_ALPHA_BETA, SweepType.MULTI_GRID)
            else (s_min if sweep_type == SweepType.BETA else -15.0),
            beta_max=sec_max
            if sweep_type in (SweepType.DUAL_ALPHA_BETA, SweepType.MULTI_GRID)
            else (s_max if sweep_type == SweepType.BETA else 15.0),
            beta_steps=sec_steps
            if sweep_type in (SweepType.DUAL_ALPHA_BETA, SweepType.MULTI_GRID)
            else (s_steps if sweep_type == SweepType.BETA else 1),
        )

        method = self.combo_solver.currentData() or AnalysisMethod.AERO_BUILDUP

        settings = {
            "spanwise_resolution": int(self.spin_span_res.value()),
            "chordwise_resolution": int(self.spin_chord_res.value()),
            "spanwise_spacing": str(self.combo_spacing.currentData() or "cosine"),
            "chordwise_spacing": str(self.combo_spacing.currentData() or "cosine"),
            "include_wave_drag": True,
        }

        self._is_running = True
        self.btn_run.setEnabled(False)
        self._api.report_progress(1, 100, "Aerodynamics")
        self._api.show_status("Running aerodynamic analysis in background...", "info")

        self._worker = AnalysisWorker(
            engine=engine,
            components=components,
            condition=condition,
            method=method,
            settings=settings,
        )
        self._worker.signals.finished.connect(self._on_analysis_finished)
        self._worker.signals.error.connect(self._on_analysis_error)
        self._worker.signals.progress.connect(self._on_analysis_progress)

        QThreadPool.globalInstance().start(self._worker)

    def _resolve_sweep(self, value: object) -> tuple[SweepType, str, str | None] | None:
        if value in {SweepType.MULTI_GRID, SweepType.DUAL_ALPHA_BETA}:
            return value, "alpha", "beta"
        if value == SweepType.BETA:
            return SweepType.BETA, "beta", None
        if value == SweepType.CONTROL_DEFLECTION:
            self._refresh_control_channels()
            if not self._available_control_channels:
                QMessageBox.warning(
                    self,
                    "Missing Control Channel",
                    "The aircraft geometry does not provide an elevator, aileron, rudder, or flap channel.",
                )
                return None
            return SweepType.CONTROL_DEFLECTION, str(self.combo_ctrl.currentData()), None
        return SweepType.ALPHA, "alpha", None

    def _on_analysis_progress(self, current: int, total: int, msg: str) -> None:
        self._api.report_progress(current, total, msg or "Solving")

    def _on_analysis_finished(self, result: AeroResult) -> None:
        self._is_running = False
        self._worker = None
        self.btn_run.setEnabled(True)
        self._api.clear_progress()
        stability_error = result.raw.get("stability_error")
        if result.failed_point_count or stability_error:
            issues: list[str] = []
            if result.failed_point_count:
                issues.append(
                    f"{result.failed_point_count}/{len(result.polar_points)} point(s) failed"
                )
            if stability_error:
                issues.append("stability calculation failed")
            self._api.show_status(
                f"Aerodynamic analysis completed with warnings: {', '.join(issues)}",
                "warning",
            )
        else:
            self._api.show_status(
                f"Aerodynamic analysis complete: CL_max={result.cl_max:.2f} @ {result.cl_max_alpha:.1f}°, "
                f"L/D_max={result.ld_max:.1f}",
                "success",
            )

        if self._on_result_callback:
            self._on_result_callback(result)

    def _on_analysis_error(self, err_msg: str) -> None:
        self._is_running = False
        self._worker = None
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
                "method": "aero_buildup",
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

    def closeEvent(self, event: QCloseEvent) -> None:
        self._api.remove_project_listener(self._on_project_changed)
        self._api.remove_project_content_listener(self._on_project_changed)
        super().closeEvent(event)
