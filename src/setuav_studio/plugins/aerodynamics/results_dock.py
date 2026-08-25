"""Selected aerodynamic analysis summary and detail tables."""

from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.buttons import refresh_button_role, set_native_button
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.property_tables import ContentFitTableWidget, PropertyTableMixin

from .analysis_store import (
    EXTENSION_ID,
    RESULT_SELECTION_KIND,
    delete_analysis_entry,
    load_analysis_result,
)
from .engine.base import AeroResult, SweepType
from .engine.stability_models import MARGINAL_STATIC_MARGIN_PERCENT

SUMMARY_ROWS = [
    ("solver_engine", "Analysis Pipeline"),
    ("analysis_method", "Analysis Method"),
    ("sweep", "Sweep"),
    ("control_channel", "Control Channel"),
    ("control_effectiveness", "Channel Effectiveness"),
    ("control_linearity", "Channel Linearity"),
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
    """Show the aerodynamic result selected in the project tree."""

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
        self._current_result: AeroResult | None = None
        self._current_result_id: str | None = None
        self._init_ui()

        self._api.subscribe("aerodynamics.analysis_completed", self.display_results)
        self._api.on_project_changed(self._on_project_changed)
        self._api.on_selection_changed(self._on_selection_changed)

    @property
    def current_result(self) -> AeroResult | None:
        return self._current_result

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.tab_widget = QTabWidget(self)

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

        self.tab_widget.addTab(detail_page, "Detailed")
        main_layout.addWidget(self.tab_widget, 1)

        button_panel = QWidget(self)
        button_layout = QHBoxLayout(button_panel)
        button_layout.setContentsMargins(6, 4, 6, 6)
        self.delete_result_button = QPushButton(" Delete Result", button_panel)
        set_native_button(self.delete_result_button, "fa6s.trash")
        self.delete_result_button.setToolTip("Delete the selected project analysis result")
        self.delete_result_button.setEnabled(False)
        self.delete_result_button.clicked.connect(self._delete_selected_result)
        button_layout.addWidget(self.delete_result_button)
        button_layout.addStretch(1)
        self.btn_export_csv = QPushButton(" Export CSV", button_panel)
        set_native_button(self.btn_export_csv, "fa6s.file-csv")
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_csv.setEnabled(False)
        button_layout.addWidget(self.btn_export_csv)
        main_layout.addWidget(button_panel)

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
        if sweep_type == SweepType.MULTI_GRID:
            return "Alpha × Beta Grid"
        if sweep_type == SweepType.DUAL_ALPHA_BETA:
            return "Alpha + Beta Sweep"
        if sweep_type == SweepType.BETA:
            return "Beta Sweep"
        if sweep_type == SweepType.CONTROL_DEFLECTION:
            return f"{cond.sweep_variable.replace('_', ' ').title()} Channel Analysis"
        if len(result.polar_points) <= 1:
            return "Single Point"
        return "Alpha Sweep"

    def display_results(self, result: AeroResult) -> None:
        """Display a newly completed (possibly not yet persisted) result."""
        if not isinstance(result, AeroResult):
            return
        self._current_result_id = None
        self._show_result(result)

    def _on_selection_changed(self, selection: object | None) -> None:
        if not isinstance(selection, dict) or selection.get("kind") != RESULT_SELECTION_KIND:
            self.clear_results()
            return
        analysis_id = str(selection.get("analysis_id") or "")
        result = load_analysis_result(self._api.current_project, analysis_id)
        if result is None:
            self.clear_results()
            return
        self._current_result_id = analysis_id
        self._show_result(result)

    def _delete_selected_result(self) -> None:
        analysis_id = self._current_result_id
        project = self._api.current_project
        if not analysis_id or project is None or project.read_only:
            return
        self._api.edit_project_extension(
            EXTENSION_ID,
            "Delete aerodynamic analysis result",
            lambda extension: delete_analysis_entry(extension, analysis_id),
        )
        self._api.set_selection(None)
        self._api.show_status("Deleted aerodynamic analysis result", "success", 3000)

    def _show_result(self, result: AeroResult) -> None:
        self._current_result = result
        self._populate_summary(result)
        self._populate_details(result)
        self.btn_export_csv.setEnabled(bool(result.polar_points))
        project = self._api.current_project
        self.delete_result_button.setEnabled(
            self._current_result_id is not None and project is not None and not project.read_only
        )
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

        if cond.sweep_type == SweepType.MULTI_GRID:
            sweep_range = (
                f"α {cond.sweep_min:+g}…{cond.sweep_max:+g}° ({cond.sweep_steps}); "
                f"β {cond.secondary_min:+g}…{cond.secondary_max:+g}° "
                f"({cond.secondary_steps})"
            )
        elif cond.sweep_type == SweepType.DUAL_ALPHA_BETA:
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
            "convergence": f"{valid_count}/{total_points} ({valid_count / total_points * 100:.1f}%)"
            if total_points
            else "N/A",
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
            "oswald_e": f"{result.oswald_efficiency:.3f}"
            if result.oswald_efficiency is not None
            else "N/A",
        }

        metrics.update(self._control_analysis_metrics(result))
        metrics.update(self._stability_metrics(result))
        for key, _label in SUMMARY_ROWS:
            self._set_property_value(self.summary_table, key, metrics.get(key, "-"))

    @staticmethod
    def _control_analysis_metrics(result: AeroResult) -> dict[str, str]:
        analysis = result.control_analysis
        if analysis is None:
            return {}
        derivatives = analysis.derivatives_per_deg
        primary_coefficient = {
            "elevator": "Cm",
            "aileron": "Cl",
            "rudder": "Cn",
            "flap": "CL",
        }.get(analysis.channel, "Cm")
        derivative_text = " | ".join(
            f"d{name}/dδ={derivatives.get(name, 0.0):+.5f}/deg"
            for name in ("CL", "CD", "Cm", "CY", "Cl", "Cn")
        )
        return {
            "control_channel": (
                f"{analysis.channel.title()} · "
                f"{analysis.deflection_min_deg:+g}…{analysis.deflection_max_deg:+g}° · "
                f"{analysis.sample_count} points"
            ),
            "control_effectiveness": derivative_text,
            "control_linearity": (
                f"{primary_coefficient} R²="
                f"{analysis.linearity_r2.get(primary_coefficient, 0.0):.4f}"
            ),
        }

    @staticmethod
    def _stability_metrics(result: AeroResult) -> dict[str, str]:
        sd = result.stability_derivatives
        if sd is None:
            error = result.raw.get("stability_error")
            return {
                "stability_method": f"FAILED — {error}" if error else "N/A",
            }

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

        static_margin = float(getattr(sd, "static_margin", 0.0))
        pitch_stable = bool(getattr(sd, "is_pitch_stable", False)) and static_margin > 0.0
        pitch_damped = bool(getattr(sd, "is_pitch_damped", False))
        if not pitch_stable:
            pitch_status = "UNSTABLE"
        elif static_margin < MARGINAL_STATIC_MARGIN_PERCENT:
            pitch_status = "MARGINAL"
        elif pitch_damped:
            pitch_status = "STABLE (Damped)"
        else:
            pitch_status = "STABLE"
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
            "np_x": f"{getattr(sd, 'x_np') * 1000.0:.1f} mm ({getattr(sd, 'x_np'):.4f} m)"
            if hasattr(sd, "x_np")
            else "-",
            "static_margin": f"{getattr(sd, 'static_margin'):+.2f} % MAC"
            if hasattr(sd, "static_margin")
            else "-",
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
                control_text = (
                    ", ".join(
                        f"{name} {value:+.1f}°"
                        for name, value in sorted(point.control_deflections.items())
                    )
                    or "—"
                )
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
        if self._current_result is None and self._current_result_id is None:
            return
        self._current_result = None
        self._current_result_id = None
        self._clear_tables()
        self.delete_result_button.setEnabled(False)
        self._api.publish("aerodynamics.result_selected", None)

    def _on_project_changed(self, _project: object) -> None:
        self.clear_results()

    def _export_csv(self) -> None:
        if self._current_result is None:
            return
        summary_selected = self.tab_widget.currentIndex() == 0
        table: QTableWidget = self.summary_table if summary_selected else self.detail_table
        suffix = "summary" if summary_selected else "detailed"
        analysis_tag = (self._current_result_id or "current")[:8]
        default_name = f"aerodynamic_analysis_{analysis_tag}_{suffix}.csv"
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
                writer.writerow(
                    [
                        table.horizontalHeaderItem(column).text()
                        for column in range(table.columnCount())
                    ]
                )
                for row in range(table.rowCount()):
                    writer.writerow(
                        [
                            table.item(row, column).text()
                            if table.item(row, column) is not None
                            else ""
                            for column in range(table.columnCount())
                        ]
                    )
            self._api.show_status(f"Exported {default_name} to {path}", "success")
        except Exception as error:
            self._api.show_status(f"CSV Export failed: {error}", "error")

    def update_theme_style(self) -> None:
        self.tab_widget.setTabIcon(0, get_icon("fa6s.chart-simple"))
        self.tab_widget.setTabIcon(1, get_icon("fa6s.table"))
        refresh_button_role(self.delete_result_button)
        refresh_button_role(self.btn_export_csv)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._api.unsubscribe("aerodynamics.analysis_completed", self.display_results)
        self._api.remove_project_listener(self._on_project_changed)
        self._api.remove_selection_listener(self._on_selection_changed)
        super().closeEvent(event)
