"""Aerodynamic Analysis Controls dock widget."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox
from setuav_studio.ui.property_tables import PropertyTableMixin
from setuav_studio.ui.theme import tokens

from .engine.base import (
    AeroEngine,
    AeroResult,
    AnalysisMethod,
    FlightCondition,
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

        self._create_engine_section()
        self._create_conditions_section()
        self._create_sweep_section()
        self._create_actions_section()

        self._content_layout.addStretch(1)

    def set_result_callback(self, callback: Callable[[AeroResult], None]) -> None:
        self._on_result_callback = callback

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
            icon_label.setPixmap(get_icon(icon_name).pixmap(14, 14))
            h_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        h_layout.addWidget(title_label)
        h_layout.addStretch(1)

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_engine_section(self) -> None:
        layout = self._create_section("Engine Configuration", "fa6s.gears")

        self.engine_table = self._property_table([
            ("engine", "Engine"),
            ("method", "Solver Method"),
        ])

        # Engine Combo
        self.combo_engine = QComboBox()
        for name in self._engines:
            self.combo_engine.addItem(name)
        self.combo_engine.currentIndexChanged.connect(self._on_engine_changed)

        # Method Combo
        self.combo_method = QComboBox()
        self.combo_method.addItem("AeroBuildup", AnalysisMethod.AERO_BUILDUP)
        self.combo_method.addItem("Vortex Lattice Method (VLM)", AnalysisMethod.VLM)
        self.combo_method.setCurrentIndex(0)
        self.combo_method.currentIndexChanged.connect(self._on_method_changed)

        self.engine_table.setCellWidget(0, 1, self.combo_engine)
        self.engine_table.setCellWidget(1, 1, self.combo_method)

        layout.addWidget(self.engine_table)

        # Single-sentence note
        self.lbl_solver_note = QLabel()
        self.lbl_solver_note.setWordWrap(True)
        self.lbl_solver_note.setStyleSheet("QLabel { color: #888898; font-size: 11px; padding: 2px 2px; }")
        layout.addWidget(self.lbl_solver_note)

        self._on_engine_changed()
        self._on_method_changed()

    def _on_engine_changed(self) -> None:
        pass

    def _on_method_changed(self) -> None:
        method = self.combo_method.currentData()
        if method == AnalysisMethod.AERO_BUILDUP:
            self.lbl_solver_note.setText(
                "Includes viscous profile drag, stall separation (CL,max), and wave drag."
            )
        elif method == AnalysisMethod.VLM:
            self.lbl_solver_note.setText(
                "Inviscid 3D potential flow (linear lift slope, no stall modeling)."
            )
        else:
            self.lbl_solver_note.setText("")

    def _create_conditions_section(self) -> None:
        layout = self._create_section("Flight Conditions", "fa6s.wind")

        self.conditions_table = self._property_table([
            ("velocity", "Airspeed (V)"),
            ("altitude", "Altitude (MSL)"),
            ("ref_alpha", "Reference AoA (α)"),
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

        self.conditions_table.setCellWidget(0, 1, self.spin_velocity)
        self.conditions_table.setCellWidget(1, 1, self.spin_altitude)
        self.conditions_table.setCellWidget(2, 1, self.spin_ref_alpha)

        layout.addWidget(self.conditions_table)

    def _create_sweep_section(self) -> None:
        layout = self._create_section("Polar Sweep Range", "fa6s.arrows-left-right")

        self.sweep_table = self._property_table([
            ("mode", "Analysis Mode"),
            ("alpha_min", "AoA Start (α_min)"),
            ("alpha_max", "AoA End (α_max)"),
            ("alpha_steps", "Step Count (N)"),
        ])

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Polar Sweep (α-range)")
        self.combo_mode.addItem("Single Point (Ref AoA)")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        self.spin_alpha_min = NumericSpinBox()
        self.spin_alpha_min.setRange(-30.0, 10.0)
        self.spin_alpha_min.setValue(-10.0)
        self.spin_alpha_min.setSuffix(" °")

        self.spin_alpha_max = NumericSpinBox()
        self.spin_alpha_max.setRange(0.0, 45.0)
        self.spin_alpha_max.setValue(18.0)
        self.spin_alpha_max.setSuffix(" °")

        self.spin_alpha_steps = NumericSpinBox()
        self.spin_alpha_steps.setDecimals(0)
        self.spin_alpha_steps.setRange(3, 100)
        self.spin_alpha_steps.setValue(29)

        self.sweep_table.setCellWidget(0, 1, self.combo_mode)
        self.sweep_table.setCellWidget(1, 1, self.spin_alpha_min)
        self.sweep_table.setCellWidget(2, 1, self.spin_alpha_max)
        self.sweep_table.setCellWidget(3, 1, self.spin_alpha_steps)

        layout.addWidget(self.sweep_table)

    def _on_mode_changed(self) -> None:
        is_sweep = self.combo_mode.currentIndex() == 0
        self.spin_alpha_min.setEnabled(is_sweep)
        self.spin_alpha_max.setEnabled(is_sweep)
        self.spin_alpha_steps.setEnabled(is_sweep)

    def _create_actions_section(self) -> None:
        layout = self._create_section("Actions", "fa6s.play")

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)

        self.btn_run = QPushButton(" Run")
        self.btn_run.setIcon(get_icon("fa6s.play"))
        self.btn_run.clicked.connect(self.run_analysis)
        btn_layout.addWidget(self.btn_run)

        self.btn_save_config = QPushButton(" Save Configuration")
        self.btn_save_config.setIcon(get_icon("fa6s.floppy-disk"))
        self.btn_save_config.clicked.connect(self._save_configuration)
        btn_layout.addWidget(self.btn_save_config)

        layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def run_analysis(self) -> None:
        if self._is_running:
            return

        engine_name = self.combo_engine.currentText()
        engine = self._engines.get(engine_name)
        if not engine or not engine.is_available():
            QMessageBox.warning(
                self,
                "Engine Not Available",
                f"{engine_name} is not available or required dependencies are missing.\n"
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

        # Build FlightCondition
        is_sweep = self.combo_mode.currentIndex() == 0
        condition = FlightCondition(
            velocity=float(self.spin_velocity.value()),
            altitude=float(self.spin_altitude.value()),
            alpha=float(self.spin_ref_alpha.value()),
            alpha_min=float(self.spin_alpha_min.value()),
            alpha_max=float(self.spin_alpha_max.value()),
            alpha_steps=int(self.spin_alpha_steps.value()) if is_sweep else 1,
        )

        method = self.combo_method.currentData() or AnalysisMethod.AERO_BUILDUP

        self._is_running = True
        self.btn_run.setEnabled(False)
        self.progress_bar.setValue(10)
        self.progress_bar.setVisible(True)
        self._api.show_status("Running aerodynamic analysis in background...", "info")

        worker = AnalysisWorker(
            engine=engine,
            components=components,
            condition=condition,
            method=method,
        )
        worker.signals.finished.connect(self._on_analysis_finished)
        worker.signals.error.connect(self._on_analysis_error)
        worker.signals.progress.connect(self._on_analysis_progress)

        QThreadPool.globalInstance().start(worker)

    def _on_analysis_progress(self, current: int, total: int, msg: str) -> None:
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
        if msg:
            self._api.show_status(msg, "info")

    def _on_analysis_finished(self, result: AeroResult) -> None:
        self._is_running = False
        self.btn_run.setEnabled(True)
        self.progress_bar.setVisible(False)
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
        self.progress_bar.setVisible(False)
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
            "type": f"org.setuav.{self.combo_engine.currentText().lower()}:steady-aero",
            "plugin": {
                "id": "org.setuav.studio.aerodynamics",
                "version": "^0.1.0",
            },
            "settings": {
                "velocity": {"value": float(self.spin_velocity.value()), "unit": "m/s"},
                "altitude": {"value": float(self.spin_altitude.value()), "unit": "m"},
                "angle_of_attack": {"value": float(self.spin_ref_alpha.value()), "unit": "deg"},
                "method": str(self.combo_method.currentData().value if self.combo_method.currentData() else "aero_buildup"),
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
