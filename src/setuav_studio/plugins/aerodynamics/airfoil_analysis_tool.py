"""Standalone NeuralFoil analysis tool."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.plugins.geometry.engine.airfoil import (
    PRESET_AIRFOILS,
    parse_airfoil_dat,
)
from setuav_studio.ui.buttons import set_button_role, set_native_button
from setuav_studio.ui.numeric_spinbox import NumericSpinBox

from .charts_dock import SingleChartWidget
from .engine.aerosandbox_engine import AeroSandboxEngine, HAS_AEROSANDBOX
@dataclass(frozen=True)
class AirfoilAnalysisRequest:
    airfoil_spec: object
    alpha_min: float
    alpha_max: float
    alpha_steps: int
    reynolds: float
    mach: float
    n_crit: float
    model_size: str


class AirfoilAnalysisWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, request: AirfoilAnalysisRequest) -> None:
        super().__init__()
        self._request = request

    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(self._analyze())
        except Exception as error:
            self.failed.emit(str(error))

    def _analyze(self) -> dict[str, Any]:
        if not HAS_AEROSANDBOX:
            raise RuntimeError(
                "AeroSandbox is not installed. Install the aerodynamics extra first."
            )

        import numpy as native_np
        request = self._request
        alphas = native_np.linspace(
            request.alpha_min,
            request.alpha_max,
            request.alpha_steps,
        )
        airfoil = AeroSandboxEngine()._resolve_airfoil(request.airfoil_spec)

        raw = airfoil.get_aero_from_neuralfoil(
            alpha=alphas,
            Re=request.reynolds,
            mach=request.mach,
            n_crit=request.n_crit,
            model_size=request.model_size,
        )
        raw = dict(raw)
        raw["alpha"] = alphas
        engine_name = f"NeuralFoil ({request.model_size})"

        def vector(key: str, default: float = math.nan) -> list[float]:
            value = raw.get(key)
            if value is None:
                return [default] * len(alphas)
            array = native_np.asarray(value, dtype=float).reshape(-1)
            if len(array) == 1 and len(alphas) > 1:
                array = native_np.repeat(array, len(alphas))
            return [float(item) for item in array]

        alpha_values = vector("alpha")
        cl_values = vector("CL")
        cd_values = vector("CD")
        cm_values = vector("CM")
        top_xtr = vector("Top_Xtr")
        bot_xtr = vector("Bot_Xtr")
        count = min(
            len(alpha_values),
            len(cl_values),
            len(cd_values),
            len(cm_values),
        )

        rows: list[dict[str, float]] = []
        for index in range(count):
            alpha = alpha_values[index]
            cl = cl_values[index]
            cd = cd_values[index]
            cm = cm_values[index]
            if not all(math.isfinite(value) for value in (alpha, cl, cd)):
                continue
            rows.append(
                {
                    "alpha": alpha,
                    "cl": cl,
                    "cd": cd,
                    "cm": cm,
                    "ld": cl / cd if abs(cd) > 1e-12 else math.nan,
                    "top_xtr": top_xtr[index] if index < len(top_xtr) else math.nan,
                    "bot_xtr": bot_xtr[index] if index < len(bot_xtr) else math.nan,
                }
            )

        if not rows:
            raise RuntimeError(f"{engine_name} did not return any converged points.")

        return {
            "engine": engine_name,
            "airfoil": str(getattr(airfoil, "name", "Airfoil")),
            "rows": rows,
        }


class AirfoilAnalysisToolWindow(QDialog):
    """Analyze a standalone airfoil without modifying project geometry."""

    def __init__(
        self,
        api: StudioAPI,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.airfoil_analysis_tool")
        self.setWindowTitle("Airfoil Analysis")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1080, 720)
        self._api = api
        self._thread: QThread | None = None
        self._worker: AirfoilAnalysisWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        controls = QWidget(splitter)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(2, 2, 6, 2)
        controls_layout.setSpacing(8)

        profile_group = QGroupBox("Airfoil", controls)
        profile_form = QFormLayout(profile_group)
        self.airfoil_combo = QComboBox(profile_group)
        self.airfoil_combo.setEditable(True)
        self._populate_airfoils()
        profile_form.addRow("Profile", self.airfoil_combo)
        self.import_button = QPushButton(" Import .dat", profile_group)
        set_native_button(self.import_button, "fa6s.folder-open")
        self.import_button.clicked.connect(self._import_airfoil)
        profile_form.addRow("", self.import_button)
        controls_layout.addWidget(profile_group)

        solver_group = QGroupBox("Solver", controls)
        solver_form = QFormLayout(solver_group)
        solver_form.addRow("Engine", QLabel("NeuralFoil", solver_group))
        self.model_combo = QComboBox(solver_group)
        for model_size in ("small", "medium", "large", "xlarge"):
            self.model_combo.addItem(model_size, model_size)
        self.model_combo.setCurrentText("large")
        solver_form.addRow("Model", self.model_combo)
        controls_layout.addWidget(solver_group)

        condition_group = QGroupBox("Analysis Range", controls)
        condition_form = QFormLayout(condition_group)
        self.alpha_min_spin = self._float_spin(-30.0, 30.0, -8.0, " °")
        self.alpha_max_spin = self._float_spin(-30.0, 30.0, 18.0, " °")
        self.alpha_steps_spin = QSpinBox(condition_group)
        self.alpha_steps_spin.setRange(3, 181)
        self.alpha_steps_spin.setValue(27)
        self.reynolds_spin = self._float_spin(1_000.0, 100_000_000.0, 500_000.0)
        self.reynolds_spin.setDecimals(0)
        self.reynolds_spin.setSingleStep(50_000.0)
        self.mach_spin = self._float_spin(0.0, 0.95, 0.05)
        self.mach_spin.setDecimals(3)
        self.ncrit_spin = self._float_spin(1.0, 14.0, 9.0)
        condition_form.addRow("α minimum", self.alpha_min_spin)
        condition_form.addRow("α maximum", self.alpha_max_spin)
        condition_form.addRow("Points", self.alpha_steps_spin)
        condition_form.addRow("Reynolds", self.reynolds_spin)
        condition_form.addRow("Mach", self.mach_spin)
        condition_form.addRow("Ncrit", self.ncrit_spin)
        controls_layout.addWidget(condition_group)
        controls_layout.addStretch(1)

        self.run_button = QPushButton(" Run Analysis", controls)
        set_button_role(self.run_button, "primary", "fa6s.play")
        self.run_button.clicked.connect(self._run_analysis)
        controls_layout.addWidget(self.run_button)

        self.progress = QProgressBar(controls)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        controls_layout.addWidget(self.progress)

        results_tabs = QTabWidget(splitter)
        curves_page = QWidget(results_tabs)
        curves_layout = QGridLayout(curves_page)
        curves_layout.setContentsMargins(2, 2, 2, 2)
        curves_layout.setSpacing(4)
        self.cl_chart = SingleChartWidget("Lift Curve", curves_page)
        self.polar_chart = SingleChartWidget("Drag Polar", curves_page)
        self.cm_chart = SingleChartWidget("Pitching Moment", curves_page)
        self.ld_chart = SingleChartWidget("Aerodynamic Efficiency", curves_page)
        curves_layout.addWidget(self.cl_chart, 0, 0)
        curves_layout.addWidget(self.polar_chart, 0, 1)
        curves_layout.addWidget(self.cm_chart, 1, 0)
        curves_layout.addWidget(self.ld_chart, 1, 1)
        results_tabs.addTab(curves_page, "Curves")

        self.results_table = QTableWidget(0, 7, results_tabs)
        self.results_table.setHorizontalHeaderLabels(
            ["α (°)", "CL", "CD", "CM", "L/D", "Top Xtr", "Bottom Xtr"]
        )
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setStretchLastSection(True)
        results_tabs.addTab(self.results_table, "Data")

        splitter.addWidget(controls)
        splitter.addWidget(results_tabs)
        splitter.setSizes([290, 790])

        bottom = QHBoxLayout()
        self.status_label = QLabel("Ready", self)
        self.status_label.setStyleSheet("color: palette(mid);")
        bottom.addWidget(self.status_label, 1)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        bottom.addWidget(close_button)
        layout.addLayout(bottom)

    @staticmethod
    def _float_spin(
        minimum: float,
        maximum: float,
        value: float,
        suffix: str = "",
    ) -> NumericSpinBox:
        spin = NumericSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(2)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _populate_airfoils(self) -> None:
        preferred = ("NACA 2412", "NACA 0012", "NACA 4412")
        for name in preferred:
            self.airfoil_combo.addItem(name, name)
        for name, preset in PRESET_AIRFOILS.items():
            if name in preferred:
                continue
            if preset.get("type") == "naca":
                spec: object = str(preset.get("code") or name)
            else:
                points = preset["generator"]()
                spec = {
                    "type": "coordinates",
                    "name": name,
                    "points": [list(point) for point in points],
                }
            self.airfoil_combo.addItem(name, spec)
        self.airfoil_combo.setCurrentText("NACA 2412")

    def _import_airfoil(self) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import Airfoil Coordinates",
            "",
            "Airfoil Files (*.dat *.txt *.cor *.af);;All Files (*)",
        )
        if not file_path:
            return
        path = Path(file_path)
        try:
            name, points = parse_airfoil_dat(
                path.read_text(encoding="utf-8", errors="replace")
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Airfoil Import", str(error))
            return
        label = name or path.stem
        spec = {
            "type": "coordinates",
            "name": label,
            "points": [list(point) for point in points],
        }
        self.airfoil_combo.addItem(label, spec)
        self.airfoil_combo.setCurrentIndex(self.airfoil_combo.count() - 1)

    def _selected_airfoil_spec(self) -> object:
        data = self.airfoil_combo.currentData()
        if self.airfoil_combo.currentIndex() >= 0 and data is not None:
            return deepcopy(data)
        return self.airfoil_combo.currentText().strip() or "NACA 2412"

    def _run_analysis(self) -> None:
        if self._thread is not None:
            return
        if not HAS_AEROSANDBOX:
            QMessageBox.warning(
                self,
                "AeroSandbox Missing",
                "Install the aerodynamics extra before running airfoil analysis.",
            )
            return
        alpha_min = float(self.alpha_min_spin.value())
        alpha_max = float(self.alpha_max_spin.value())
        if alpha_max <= alpha_min:
            QMessageBox.warning(
                self,
                "Invalid Range",
                "Maximum angle of attack must be greater than the minimum.",
            )
            return

        request = AirfoilAnalysisRequest(
            airfoil_spec=self._selected_airfoil_spec(),
            alpha_min=alpha_min,
            alpha_max=alpha_max,
            alpha_steps=int(self.alpha_steps_spin.value()),
            reynolds=float(self.reynolds_spin.value()),
            mach=float(self.mach_spin.value()),
            n_crit=float(self.ncrit_spin.value()),
            model_size=str(self.model_combo.currentData()),
        )
        self.run_button.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Analysis running…")

        thread = QThread(self)
        worker = AirfoilAnalysisWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._analysis_completed)
        worker.failed.connect(self._analysis_failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(object)
    def _analysis_completed(self, result: object) -> None:
        if not isinstance(result, dict):
            self._analysis_failed("Invalid airfoil analysis result")
            return
        rows = result.get("rows")
        if not isinstance(rows, list):
            self._analysis_failed("Airfoil analysis returned no data")
            return
        self._populate_results(rows)
        self.status_label.setText(
            f"{result.get('airfoil', 'Airfoil')} · {result.get('engine', '')} · "
            f"{len(rows)} converged point(s)"
        )
        self._api.show_status("Airfoil analysis complete", "success", 3000)

    @Slot(str)
    def _analysis_failed(self, message: str) -> None:
        self.status_label.setText(f"Analysis failed: {message}")
        self._api.show_status(f"Airfoil analysis failed: {message}", "error", 5000)
        QMessageBox.critical(self, "Airfoil Analysis", message)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.run_button.setEnabled(True)
        self.progress.setVisible(False)

    def _populate_results(self, rows: list[dict[str, float]]) -> None:
        alpha = [row["alpha"] for row in rows]
        cl = [row["cl"] for row in rows]
        cd = [row["cd"] for row in rows]
        cm = [row["cm"] for row in rows]
        ld = [row["ld"] for row in rows]
        self.cl_chart.plot_single(alpha, cl, "CL", "blue", "α (°)", "CL")
        self.polar_chart.plot_single(cd, cl, "Polar", "green", "CD", "CL")
        self.cm_chart.plot_single(alpha, cm, "CM", "orange", "α (°)", "CM")
        self.ld_chart.plot_single(alpha, ld, "L/D", "magenta", "α (°)", "L/D")

        self.results_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row["alpha"],
                row["cl"],
                row["cd"],
                row["cm"],
                row["ld"],
                row["top_xtr"],
                row["bot_xtr"],
            )
            for column, value in enumerate(values):
                text = "—" if not math.isfinite(value) else f"{value:.5g}"
                self.results_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(text),
                )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None:
            self.status_label.setText("Wait for the running analysis to finish.")
            event.ignore()
            return
        super().closeEvent(event)
