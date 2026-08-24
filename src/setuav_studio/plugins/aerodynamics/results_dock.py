"""Aerodynamic analysis history and selected-result tables."""
from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.buttons import refresh_button_role, set_native_button
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.property_tables import ContentFitTableWidget, PropertyTableMixin

from .engine.base import AeroResult, SweepType


SUMMARY_ROWS = [
    ("solver_engine", "Analysis Pipeline"),
    ("analysis_method", "Analysis Method"),
    ("sweep", "Sweep"),
    ("points", "Result Points"),
    ("convergence", "Convergence"),
    ("cl_max", "Max Lift (CL_max)"),
    ("cl_max_alpha", "α at Sweep CL_max"),
    ("cd_min", "Min Drag (CD_min)"),
    ("ld_max", "Max Efficiency (L/D_max)"),
    ("ld_max_alpha", "Best Glide AoA (α_L/D)"),
    ("cd_ind_cruise", "Induced Drag (CD_i @ L/D)"),
    ("cd_prof_cruise", "Profile Drag (CD_p @ L/D)"),
    ("drag_ratio", "Drag Ratio (CD_i / CD_p)"),
    ("velocity", "Airspeed"),
    ("altitude", "Altitude (MSL)"),
    ("mach", "Mach Number (M)"),
    ("dynamic_pressure", "Dynamic Pressure (q)"),
    ("reynolds", "Reynolds Number (Re)"),
    ("ref_span", "Ref Wingspan (b)"),
    ("ref_area", "Ref Wing Area (S)"),
    ("ref_ar", "Aspect Ratio (AR)"),
    ("ref_mac", "Mean Aerodynamic Chord (MAC)"),
    ("ref_cg", "Reference CG"),
    ("oswald_e", "Oswald Efficiency (e)"),
    ("stability_method", "Stability Solver"),
    ("cla", "Lift Slope (CL_α)"),
    ("cma", "Pitch Stiffness (Cm_α)"),
    ("cmq", "Pitch Damping (Cm_q)"),
    ("pitch_status", "Longitudinal Status"),
    ("np_x", "Neutral Point (X_np)"),
    ("static_margin", "Static Margin (SM)"),
    ("clb", "Dihedral Effect (Cl_β)"),
    ("cnb", "Directional Stability (Cn_β)"),
    ("cyb", "Sideforce Slope (CY_β)"),
    ("clp", "Roll Damping (Cl_p)"),
    ("cnr", "Yaw Damping (Cn_r)"),
    ("lat_dir_status", "Lateral-Directional Status"),
    ("elevator_trim", "Elevator Trim (δ_e)"),
    ("alpha_trim_neutral", "Trim AoA (α @ δ_e=0)"),
    ("cm_de", "Elevator Control Power (Cm_δe)"),
    ("cl_da", "Aileron Control Power (Cl_δa)"),
    ("cn_dr", "Rudder Control Power (Cn_δr)"),
]


class AeroResultsDock(PropertyTableMixin, QWidget):
    """Keep analysis results and expose one selected result to the workspace."""

    table_headers = ("Metric", "Value")
    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False
    table_max_visible_rows = None
    table_scroll_policy_off = True

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.results_widget")
        self._api = api
        self._results: list[AeroResult] = []
        self._current_result: AeroResult | None = None
        self._init_ui()

        self._api.subscribe("aerodynamics.analysis_completed", self.display_results)
        self._api.on_project_changed(self._on_project_changed)

    @property
    def current_result(self) -> AeroResult | None:
        return self._current_result

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)

        list_panel = QWidget(splitter)
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(4, 4, 4, 2)
        list_layout.setSpacing(3)
        list_header = QHBoxLayout()
        list_header.setContentsMargins(0, 0, 0, 0)
        list_header.addWidget(QLabel("Analysis Results", list_panel))
        list_header.addStretch(1)
        self.delete_result_button = QToolButton(list_panel)
        self.delete_result_button.setAutoRaise(True)
        self.delete_result_button.setIcon(get_icon("fa6s.trash"))
        self.delete_result_button.setToolTip("Delete selected analysis result")
        self.delete_result_button.setEnabled(False)
        self.delete_result_button.clicked.connect(self._delete_selected_result)
        list_header.addWidget(self.delete_result_button)
        list_layout.addLayout(list_header)

        self.results_list = QListWidget(list_panel)
        self.results_list.setObjectName("aerodynamics.analysis_results_list")
        self.results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_list.setAlternatingRowColors(True)
        self.results_list.currentRowChanged.connect(self._on_result_selected)
        list_layout.addWidget(self.results_list)
        self.delete_result_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self.results_list)
        self.delete_result_shortcut.activated.connect(self._delete_selected_result)
        splitter.addWidget(list_panel)

        self.tab_widget = QTabWidget(splitter)

        summary_page = QWidget(self.tab_widget)
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(4, 4, 4, 4)
        summary_layout.setSpacing(0)
        self.summary_table = self._property_table(SUMMARY_ROWS)
        summary_layout.addWidget(self.summary_table)
        summary_layout.addStretch(1)

        summary_scroll = QScrollArea(self.tab_widget)
        summary_scroll.setWidgetResizable(True)
        summary_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        summary_scroll.setWidget(summary_page)
        self.tab_widget.addTab(summary_scroll, "Summary")

        detail_page = QWidget(self.tab_widget)
        detail_layout = QVBoxLayout(detail_page)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(0)
        self.detail_table = self._create_detail_table()
        self.detail_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        detail_layout.addWidget(self.detail_table)

        button_panel = QWidget(detail_page)
        button_layout = QHBoxLayout(button_panel)
        button_layout.setContentsMargins(6, 4, 6, 6)
        self.btn_export_csv = QPushButton(" Export CSV", button_panel)
        set_native_button(self.btn_export_csv, "fa6s.file-csv")
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_csv.setEnabled(False)
        button_layout.addWidget(self.btn_export_csv)
        detail_layout.addWidget(button_panel)

        self.tab_widget.addTab(detail_page, "Detailed")
        splitter.addWidget(self.tab_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([130, 520])
        main_layout.addWidget(splitter)

        self._clear_tables()

    @staticmethod
    def _create_detail_table() -> ContentFitTableWidget:
        headers = [
            "α (deg)",
            "β (deg)",
            "Controls",
            "CL",
            "CD",
            "CD_ind",
            "CD_prof",
            "Cm",
            "L/D",
            "CX",
            "CY",
            "CZ",
            "Cl",
            "Cn",
            "Lift (N)",
            "Drag (N)",
            "Status",
        ]
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

    @staticmethod
    def _sweep_label(result: AeroResult) -> str:
        cond = result.condition
        sweep_type = cond.sweep_type
        if sweep_type == SweepType.DUAL_ALPHA_BETA:
            return "Alpha + Beta Sweep"
        if sweep_type == SweepType.BETA:
            return "Beta Sweep"
        if sweep_type == SweepType.CONTROL_DEFLECTION:
            return f"{cond.sweep_variable.replace('_', ' ').title()} Sweep"
        if len(result.polar_points) <= 1:
            return "Single Point"
        return "Alpha Sweep"

    @classmethod
    def _result_label(cls, result: AeroResult, number: int) -> str:
        custom_name = result.raw.get("analysis_name") if isinstance(result.raw, dict) else None
        name = str(custom_name).strip() if custom_name else cls._sweep_label(result)
        method = result.method.value.replace("_", " ").upper()
        return f"{number:02d}  {name} · {method} · {len(result.polar_points)} pts"

    def display_results(self, result: AeroResult) -> None:
        """Append a completed analysis and make it the active result."""
        if not isinstance(result, AeroResult):
            return
        result_index = len(self._results)
        self._results.append(result)

        item = QListWidgetItem(self._result_label(result, result_index + 1))
        item.setData(Qt.ItemDataRole.UserRole, result_index)
        item.setToolTip(
            f"{result.engine_name} / {result.method.value}\n"
            f"{self._sweep_label(result)}\n"
            f"{len(result.polar_points)} result point(s)"
        )
        self.results_list.addItem(item)
        self.results_list.setCurrentItem(item)
        if self._current_result is not result:
            self._select_result(result_index)

    def _on_result_selected(self, row: int) -> None:
        self.delete_result_button.setEnabled(row >= 0)
        if row < 0:
            self._current_result = None
            self._clear_tables()
            self._api.publish("aerodynamics.result_selected", None)
            return
        item = self.results_list.item(row)
        result_index = int(item.data(Qt.ItemDataRole.UserRole)) if item is not None else row
        self._select_result(result_index)

    def _delete_selected_result(self) -> None:
        row = self.results_list.currentRow()
        if not 0 <= row < len(self._results):
            return

        self.results_list.blockSignals(True)
        try:
            self.results_list.takeItem(row)
            del self._results[row]
            for item_row in range(row, self.results_list.count()):
                item = self.results_list.item(item_row)
                item.setData(Qt.ItemDataRole.UserRole, item_row)
                item.setText(self._result_label(self._results[item_row], item_row + 1))
        finally:
            self.results_list.blockSignals(False)

        if self._results:
            next_row = min(row, len(self._results) - 1)
            self.results_list.blockSignals(True)
            try:
                self.results_list.setCurrentRow(next_row)
            finally:
                self.results_list.blockSignals(False)
            self.delete_result_button.setEnabled(True)
            self._select_result(next_row)
        else:
            self._current_result = None
            self._clear_tables()
            self.delete_result_button.setEnabled(False)
            self._api.publish("aerodynamics.result_selected", None)

    def _select_result(self, result_index: int) -> None:
        if not 0 <= result_index < len(self._results):
            return
        result = self._results[result_index]
        self._current_result = result
        self._populate_summary(result)
        self._populate_details(result)
        self.btn_export_csv.setEnabled(bool(result.polar_points))
        self._api.publish("aerodynamics.result_selected", result)

    def _populate_summary(self, result: AeroResult) -> None:
        ref = result.reference
        cond = result.condition
        points = result.polar_points
        valid_points = [point for point in points if point.converged]
        best_point = max(valid_points, key=lambda point: point.cl_over_cd) if valid_points else None
        total_points = len(points)
        valid_count = len(valid_points)
        aspect_ratio = ref.b_ref**2 / ref.s_ref if ref.s_ref > 0 else 0.0

        cd_i = best_point.cd_induced if best_point is not None else None
        cd_p = best_point.cd_profile if best_point is not None else None
        if cd_i is not None and cd_p is not None and cd_p > 1e-6 and best_point is not None:
            total_drag = max(best_point.cd, 1e-6)
            drag_ratio = (
                f"{cd_i / cd_p:.2f} "
                f"({cd_i / total_drag * 100:.0f}% Ind / {cd_p / total_drag * 100:.0f}% Prof)"
            )
        else:
            drag_ratio = "N/A"

        if cond.sweep_type == SweepType.DUAL_ALPHA_BETA:
            sweep_range = (
                f"α {cond.alpha_min:+g}…{cond.alpha_max:+g}° ({cond.alpha_steps}); "
                f"β {cond.beta_min:+g}…{cond.beta_max:+g}° ({cond.beta_steps})"
            )
        elif len(points) <= 1:
            sweep_range = f"α {cond.alpha:+g}°, β {cond.beta:+g}°"
        else:
            sweep_range = (
                f"{self._sweep_label(result)}: "
                f"{cond.sweep_min:+g}…{cond.sweep_max:+g}° ({cond.sweep_steps})"
            )

        metrics = {
            "solver_engine": result.engine_name,
            "analysis_method": result.method.value.replace("_", " ").title(),
            "sweep": sweep_range,
            "points": str(total_points),
            "convergence": f"{valid_count}/{total_points} ({valid_count / total_points * 100:.1f}%)" if total_points else "N/A",
            "cl_max": f"{result.cl_max:.4f}",
            "cl_max_alpha": f"{result.cl_max_alpha:.2f}°",
            "cd_min": f"{result.cd_min:.5f}",
            "ld_max": f"{result.ld_max:.2f}",
            "ld_max_alpha": f"{result.ld_max_alpha:.2f}°",
            "cd_ind_cruise": f"{cd_i:.5f}" if cd_i is not None else "N/A",
            "cd_prof_cruise": f"{cd_p:.5f}" if cd_p is not None else "N/A",
            "drag_ratio": drag_ratio,
            "velocity": f"{cond.velocity:.2f} m/s",
            "altitude": f"{cond.altitude:.1f} m",
            "mach": f"{result.mach:.3f}",
            "dynamic_pressure": f"{result.dynamic_pressure:.1f} Pa",
            "reynolds": f"{result.reynolds:,.0f}" if result.reynolds > 0 else "N/A",
            "ref_span": f"{ref.b_ref * 1000.0:.1f} mm ({ref.b_ref:.3f} m)",
            "ref_area": f"{ref.s_ref * 1e4:.1f} cm² ({ref.s_ref:.4f} m²)",
            "ref_ar": f"{aspect_ratio:.2f}",
            "ref_mac": f"{ref.c_ref * 1000.0:.1f} mm",
            "ref_cg": f"[{ref.xyz_ref[0] * 1000.0:.1f}, {ref.xyz_ref[1] * 1000.0:.1f}, {ref.xyz_ref[2] * 1000.0:.1f}] mm",
            "oswald_e": f"{result.oswald_efficiency:.3f}" if result.oswald_efficiency is not None else "N/A",
        }

        metrics.update(self._stability_metrics(result))
        for key, _label in SUMMARY_ROWS:
            self._set_property_value(self.summary_table, key, metrics.get(key, "-"))

    @staticmethod
    def _stability_metrics(result: AeroResult) -> dict[str, str]:
        sd = result.stability_derivatives
        if sd is None:
            return {}

        def derivative(rad_name: str, deg_name: str) -> str:
            if not hasattr(sd, rad_name):
                return "-"
            return f"{getattr(sd, rad_name):.3f} /rad ({getattr(sd, deg_name):.4f} /deg)"

        def control_metric(tag: str, attribute: str) -> str:
            control = (getattr(sd, "controls", {}) or {}).get(tag)
            if control is None:
                return "N/A"
            value = getattr(control, attribute)
            method = getattr(control, "derivative_method", "finite_difference")
            step = getattr(control, "perturbation_deg", 2.0)
            if method == "finite_difference":
                return f"{value:+.4f} /deg (FD ±{step:g}°)"
            return f"{value:+.4f} /deg ({method})"

        pitch_stable = bool(getattr(sd, "is_pitch_stable", False))
        pitch_damped = bool(getattr(sd, "is_pitch_damped", False))
        pitch_status = "STABLE (Damped)" if pitch_stable and pitch_damped else ("STABLE" if pitch_stable else "UNSTABLE")
        trim = getattr(sd, "elevator_trim", None)
        trim_reasons = tuple(getattr(sd, "trim_invalid_reasons", ()) or ())
        trim_value = (
            f"{trim.delta_e_trim:+.2f}° (CL={trim.cl_trim:.3f})"
            if trim
            else "N/A" + (f" — {'; '.join(trim_reasons)}" if trim_reasons else "")
        )
        return {
            "stability_method": f"{getattr(sd, 'solver_method', 'unknown')} / {getattr(sd, 'rate_derivative_convention', 'normalized_body_rates')}",
            "cla": derivative("c_L_alpha_rad", "c_L_alpha_deg"),
            "cma": derivative("c_m_alpha_rad", "c_m_alpha_deg"),
            "cmq": f"{getattr(sd, 'c_m_q'):.3f}" if hasattr(sd, "c_m_q") else "-",
            "pitch_status": pitch_status,
            "np_x": f"{getattr(sd, 'x_np') * 1000.0:.1f} mm ({getattr(sd, 'x_np'):.4f} m)" if hasattr(sd, "x_np") else "-",
            "static_margin": f"{getattr(sd, 'static_margin'):+.2f} % MAC" if hasattr(sd, "static_margin") else "-",
            "clb": derivative("c_l_beta_rad", "c_l_beta_deg"),
            "cnb": derivative("c_n_beta_rad", "c_n_beta_deg"),
            "cyb": derivative("c_Y_beta_rad", "c_Y_beta_deg"),
            "clp": f"{getattr(sd, 'c_l_p'):.3f}" if hasattr(sd, "c_l_p") else "-",
            "cnr": f"{getattr(sd, 'c_n_r'):.3f}" if hasattr(sd, "c_n_r") else "-",
            "lat_dir_status": (
                f"{'Roll-Stable' if getattr(sd, 'is_roll_stable', True) else 'Roll-Unstable'} | "
                f"{'Yaw-Stable' if getattr(sd, 'is_yaw_stable', True) else 'Yaw-Unstable'}"
            ),
            "elevator_trim": trim_value,
            "alpha_trim_neutral": f"{trim.alpha_trim_neutral:+.2f}°" if trim else "N/A",
            "cm_de": control_metric("elevator", "c_m_delta"),
            "cl_da": control_metric("aileron", "c_l_delta"),
            "cn_dr": control_metric("rudder", "c_n_delta"),
        }

    def _populate_details(self, result: AeroResult) -> None:
        points = result.polar_points
        self.detail_table.setUpdatesEnabled(False)
        self.detail_table.blockSignals(True)
        try:
            self.detail_table.setRowCount(len(points))
            for row, point in enumerate(points):
                control_text = ", ".join(
                    f"{name} {value:+.1f}°"
                    for name, value in sorted(point.control_deflections.items())
                ) or "—"
                values = [
                    f"{point.alpha:+.2f}",
                    f"{point.beta:+.2f}",
                    control_text,
                    f"{point.cl:.4f}",
                    f"{point.cd:.5f}",
                    f"{point.cd_induced:.5f}" if point.cd_induced is not None else "—",
                    f"{point.cd_profile:.5f}" if point.cd_profile is not None else "—",
                    f"{point.cm:+.4f}",
                    f"{point.cl_over_cd:.2f}",
                    f"{point.cx:+.4f}",
                    f"{point.cy:+.4f}",
                    f"{point.cz:+.4f}",
                    f"{point.cl_roll:+.5f}",
                    f"{point.cn:+.5f}",
                    f"{point.lift:.3f}",
                    f"{point.drag:.3f}",
                    "OK" if point.converged else f"FAILED: {point.notes}",
                ]
                for column, value in enumerate(values):
                    self.detail_table.setItem(row, column, QTableWidgetItem(value))
            self.detail_table.fit_columns_to_viewport()
        finally:
            self.detail_table.blockSignals(False)
            self.detail_table.setUpdatesEnabled(True)

    def _clear_tables(self) -> None:
        for key, _label in SUMMARY_ROWS:
            self._set_property_value(self.summary_table, key, "-")
        self.detail_table.setRowCount(0)
        self.btn_export_csv.setEnabled(False)

    def clear_results(self) -> None:
        self.results_list.blockSignals(True)
        try:
            self.results_list.clear()
        finally:
            self.results_list.blockSignals(False)
        self._results.clear()
        self._current_result = None
        self._clear_tables()
        self._api.publish("aerodynamics.result_selected", None)

    def _on_project_changed(self, _project: object) -> None:
        self.clear_results()

    def _export_csv(self) -> None:
        if self._current_result is None:
            return
        summary_selected = self.tab_widget.currentIndex() == 0
        table: QTableWidget = self.summary_table if summary_selected else self.detail_table
        suffix = "summary" if summary_selected else "detailed"
        current_row = max(self.results_list.currentRow() + 1, 1)
        default_name = f"aerodynamic_analysis_{current_row:02d}_{suffix}.csv"
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Aerodynamic Results",
            default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow([
                    table.horizontalHeaderItem(column).text()
                    for column in range(table.columnCount())
                ])
                for row in range(table.rowCount()):
                    writer.writerow([
                        table.item(row, column).text() if table.item(row, column) is not None else ""
                        for column in range(table.columnCount())
                    ])
            self._api.show_status(f"Exported {default_name} to {path}", "success")
        except Exception as error:
            self._api.show_status(f"CSV Export failed: {error}", "error")

    def update_theme_style(self) -> None:
        self.tab_widget.setTabIcon(0, get_icon("fa6s.chart-simple"))
        self.tab_widget.setTabIcon(1, get_icon("fa6s.table"))
        self.delete_result_button.setIcon(get_icon("fa6s.trash"))
        refresh_button_role(self.btn_export_csv)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._api.unsubscribe("aerodynamics.analysis_completed", self.display_results)
        self._api.remove_project_listener(self._on_project_changed)
        super().closeEvent(event)
