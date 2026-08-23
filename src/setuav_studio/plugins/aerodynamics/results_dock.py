"""Aerodynamic Analysis Results dock widget."""
from __future__ import annotations

import csv
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.buttons import refresh_button_role, set_native_button
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.property_tables import ContentFitTableWidget, PropertyTableMixin
from setuav_studio.ui.theme import tokens
from .engine.base import AeroResult, SweepType


class AeroResultsDock(PropertyTableMixin, QWidget):
    """Aerodynamic analysis results dock displaying summary metrics and polar table."""

    table_headers = ("Metric", "Value")
    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.results_widget")
        self._api = api
        self._tokens = tokens()
        self._current_result: AeroResult | None = None
        self._init_ui()

        if self._api is not None:
            self._api.subscribe("aerodynamics.analysis_completed", self.display_results)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Tab widget for Summary vs Detailed Data Table
        self.tab_widget = QTabWidget()

        # Tab 1: Summary Key Performance Indicators
        self.summary_tab = QWidget()
        sum_layout = QVBoxLayout(self.summary_tab)
        sum_layout.setContentsMargins(4, 4, 4, 4)
        sum_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        sum_layout.setSpacing(6)

        self.summary_table = self._property_table([
            ("solver_engine", "Analysis Pipeline"),
            ("cl_max", "Max Lift (CL_max)"),
            ("cl_max_alpha", "Stall Angle (α_stall)"),
            ("cd_min", "Min Drag (CD_min)"),
            ("ld_max", "Max Efficiency (L/D_max)"),
            ("ld_max_alpha", "Best Glide AoA (α_L/D)"),
            ("cd_ind_cruise", "Induced Drag (CD_i @ L/D)"),
            ("cd_prof_cruise", "Profile Drag (CD_p @ L/D)"),
            ("drag_ratio", "Drag Ratio (CD_i / CD_p)"),
            ("ref_span", "Ref Wingspan (b)"),
            ("ref_area", "Ref Wing Area (S)"),
            ("ref_ar", "Aspect Ratio (AR)"),
            ("ref_mac", "Mean Aerodyn Chord (MAC)"),
            ("mach", "Mach Number (M)"),
            ("dynamic_pressure", "Dynamic Pressure (q)"),
            ("reynolds", "Reynolds Number (Re)"),
            ("oswald_e", "Oswald Efficiency (e)"),
        ])
        sum_layout.addWidget(self.summary_table)
        sum_layout.addStretch(1)

        sum_scroll = QScrollArea()
        sum_scroll.setWidgetResizable(True)
        sum_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        sum_scroll.setWidget(self.summary_tab)
        self.tab_widget.addTab(sum_scroll, "Summary")

        # Tab 2: Stability & Trim Metrics
        self.stability_tab = QWidget()
        stab_layout = QVBoxLayout(self.stability_tab)
        stab_layout.setContentsMargins(4, 4, 4, 4)
        stab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        stab_layout.setSpacing(6)

        self.stability_table = self._property_table([
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
            ("elevator_trim", "Elevator Trim (δ_e @ Cruise)"),
            ("alpha_trim_neutral", "Trim AoA (α @ δ_e=0)"),
            ("cm_de", "Elevator Control Power (Cm_δe)"),
            ("cl_da", "Aileron Control Power (Cl_δa)"),
            ("cn_dr", "Rudder Control Power (Cn_δr)"),
        ])
        stab_layout.addWidget(self.stability_table)
        stab_layout.addStretch(1)

        stab_scroll = QScrollArea()
        stab_scroll.setWidgetResizable(True)
        stab_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        stab_scroll.setWidget(self.stability_tab)
        self.tab_widget.addTab(stab_scroll, "Stability & Trim")

        # Tab 3: Detailed Polar Table
        self.detail_tab = QWidget()
        det_layout = QVBoxLayout(self.detail_tab)
        det_layout.setContentsMargins(0, 0, 0, 0)
        det_layout.setSpacing(0)

        self.detail_table = self._create_detail_table()
        self.detail_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        det_layout.addWidget(self.detail_table)

        # Export CSV Button Container with slight margin
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(6, 4, 6, 6)
        btn_layout.setSpacing(0)
        self.btn_export_csv = QPushButton(" Export Polar Data (CSV)")
        set_native_button(self.btn_export_csv, "fa6s.file-csv")
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_csv.setEnabled(False)
        btn_layout.addWidget(self.btn_export_csv)
        det_layout.addWidget(btn_container)

        self.tab_widget.addTab(self.detail_tab, "Polar Table")

        main_layout.addWidget(self.tab_widget)

    def _create_detail_table(self) -> ContentFitTableWidget:
        headers = [
            "α (deg)",
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
        ]
        table = ContentFitTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
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

    def clear_results(self) -> None:
        self._current_result = None
        for key in (
            "solver_engine", "cl_max", "cl_max_alpha", "cd_min",
            "ld_max", "ld_max_alpha", "cd_ind_cruise", "cd_prof_cruise",
            "drag_ratio", "ref_span", "ref_area", "ref_ar", "ref_mac",
            "mach", "dynamic_pressure", "reynolds", "oswald_e",
        ):
            self._set_property_value(self.summary_table, key, "-")

        for key in (
            "cla", "cma", "cmq", "pitch_status", "np_x", "static_margin",
            "clb", "cnb", "cyb", "clp", "cnr", "lat_dir_status",
            "elevator_trim", "alpha_trim_neutral", "cm_de", "cl_da", "cn_dr",
        ):
            self._set_property_value(self.stability_table, key, "-")

        self.detail_table.setRowCount(0)
        self.btn_export_csv.setEnabled(False)

    def display_results(self, result: AeroResult) -> None:
        self._current_result = result
        ref = result.reference
        points = result.polar_points
        cond = result.condition
        sweep_type = cond.sweep_type if cond else SweepType.ALPHA
        sweep_var = cond.sweep_variable if cond else "alpha"

        ar = (ref.b_ref ** 2 / ref.s_ref) if ref.s_ref > 0 else 0.0
        oswald_str = f"{result.oswald_efficiency:.3f}" if result.oswald_efficiency is not None else "N/A"

        best_pt = max(points, key=lambda p: p.cl_over_cd) if points else None
        cd_i_str = f"{best_pt.cd_induced:.5f}" if best_pt else "-"
        cd_p_str = f"{best_pt.cd_profile:.5f}" if best_pt else "-"
        if best_pt and best_pt.cd_profile > 1e-6:
            tot_d = max(best_pt.cd, 1e-6)
            ratio_str = f"{best_pt.cd_induced / best_pt.cd_profile:.2f} ({best_pt.cd_induced / tot_d * 100:.0f}% Ind / {best_pt.cd_profile / tot_d * 100:.0f}% Prof)"
        else:
            ratio_str = "N/A"

        metrics = {
            "solver_engine": f"{result.engine_name}",
            "cl_max": f"{result.cl_max:.4f}",
            "cl_max_alpha": f"{result.cl_max_alpha:.2f}°",
            "cd_min": f"{result.cd_min:.5f}",
            "ld_max": f"{result.ld_max:.2f}",
            "ld_max_alpha": f"{result.ld_max_alpha:.2f}°",
            "cd_ind_cruise": cd_i_str,
            "cd_prof_cruise": cd_p_str,
            "drag_ratio": ratio_str,
            "ref_span": f"{ref.b_ref * 1000.0:.1f} mm ({ref.b_ref:.3f} m)",
            "ref_area": f"{ref.s_ref * 1e4:.1f} cm² ({ref.s_ref:.4f} m²)",
            "ref_ar": f"{ar:.2f}",
            "ref_mac": f"{ref.c_ref * 1000.0:.1f} mm",
            "mach": f"{result.mach:.3f}",
            "dynamic_pressure": f"{result.dynamic_pressure:.1f} Pa",
            "reynolds": f"{result.reynolds:,.0f}" if result.reynolds > 0 else "N/A",
            "oswald_e": oswald_str,
        }
        for key, val in metrics.items():
            self._set_property_value(self.summary_table, key, val)

        # Populate Stability & Trim tab
        sd = result.stability_derivatives
        if sd is not None:
            cla_val = f"{sd.c_L_alpha_rad:.3f} /rad ({sd.c_L_alpha_deg:.4f} /deg)" if hasattr(sd, "c_L_alpha_rad") else "-"
            cma_val = f"{sd.c_m_alpha_rad:.3f} /rad ({sd.c_m_alpha_deg:.4f} /deg)" if hasattr(sd, "c_m_alpha_rad") else "-"
            cmq_val = f"{sd.c_m_q:.3f}" if hasattr(sd, "c_m_q") else "-"
            p_stat = ("STABLE (Damped)" if getattr(sd, "is_pitch_stable", False) and getattr(sd, "is_pitch_damped", False) else
                      ("STABLE" if getattr(sd, "is_pitch_stable", False) else "UNSTABLE"))
            npx_val = f"{sd.x_np * 1000.0:.1f} mm ({sd.x_np:.4f} m)" if hasattr(sd, "x_np") else "-"
            sm_val = f"{sd.static_margin:+.2f} % MAC" if hasattr(sd, "static_margin") else "-"
            clb_val = f"{sd.c_l_beta_rad:.3f} /rad ({sd.c_l_beta_deg:.4f} /deg)" if hasattr(sd, "c_l_beta_rad") else "-"
            cnb_val = f"{sd.c_n_beta_rad:.3f} /rad ({sd.c_n_beta_deg:.4f} /deg)" if hasattr(sd, "c_n_beta_rad") else "-"
            cyb_val = f"{sd.c_Y_beta_rad:.3f} /rad ({sd.c_Y_beta_deg:.4f} /deg)" if hasattr(sd, "c_Y_beta_rad") else "-"
            clp_val = f"{sd.c_l_p:.3f}" if hasattr(sd, "c_l_p") else "-"
            cnr_val = f"{sd.c_n_r:.3f}" if hasattr(sd, "c_n_r") else "-"
            lat_stat = f"{'Roll-Stable' if getattr(sd, 'is_roll_stable', True) else 'Roll-Unstable'} | {'Yaw-Stable' if getattr(sd, 'is_yaw_stable', True) else 'Yaw-Unstable'}"

            trim_obj = getattr(sd, "elevator_trim", None)
            de_trim_str = f"{trim_obj.delta_e_trim:+.2f}° (CL={trim_obj.cl_trim:.3f})" if trim_obj else "N/A"
            a_trim_str = f"{trim_obj.alpha_trim_neutral:+.2f}°" if trim_obj else "N/A"

            ctrls = getattr(sd, "controls", {}) or {}
            cm_de_str = f"{ctrls['elevator'].c_m_delta:+.4f} /deg" if "elevator" in ctrls else "N/A"
            cl_da_str = f"{ctrls['aileron'].c_l_delta:+.4f} /deg" if "aileron" in ctrls else "N/A"
            cn_dr_str = f"{ctrls['rudder'].c_n_delta:+.4f} /deg" if "rudder" in ctrls else "N/A"

            stab_metrics = {
                "cla": cla_val,
                "cma": cma_val,
                "cmq": cmq_val,
                "pitch_status": p_stat,
                "np_x": npx_val,
                "static_margin": sm_val,
                "clb": clb_val,
                "cnb": cnb_val,
                "cyb": cyb_val,
                "clp": clp_val,
                "cnr": cnr_val,
                "lat_dir_status": lat_stat,
                "elevator_trim": de_trim_str,
                "alpha_trim_neutral": a_trim_str,
                "cm_de": cm_de_str,
                "cl_da": cl_da_str,
                "cn_dr": cn_dr_str,
            }
            for k, v in stab_metrics.items():
                self._set_property_value(self.stability_table, k, v)

        # Set dynamic column 0 header based on sweep variable
        if sweep_type == SweepType.BETA:
            col0_header = "β (deg)"
        elif sweep_type == SweepType.CONTROL_DEFLECTION:
            col0_header = f"δ_{sweep_var} (deg)"
        elif sweep_type == SweepType.VELOCITY:
            col0_header = "V (m/s)"
        elif sweep_type == SweepType.ALTITUDE:
            col0_header = "h (m)"
        else:
            col0_header = "α (deg)"

        headers = [
            col0_header,
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
        ]
        self.detail_table.setHorizontalHeaderLabels(headers)
        self.detail_table.setRowCount(len(points))

        for row, pt in enumerate(points):
            if sweep_type == SweepType.BETA:
                v0_str = f"{pt.beta:+.2f}"
            elif sweep_type == SweepType.CONTROL_DEFLECTION:
                v0_str = f"{pt.control_deflections.get(sweep_var, 0.0):+.2f}"
            elif sweep_type == SweepType.VELOCITY:
                v0_str = f"{pt.velocity:.2f}"
            elif sweep_type == SweepType.ALTITUDE:
                v0_str = f"{pt.altitude:.0f}"
            else:
                v0_str = f"{pt.alpha:+.2f}"

            self.detail_table.setItem(row, 0, QTableWidgetItem(v0_str))
            self.detail_table.setItem(row, 1, QTableWidgetItem(f"{pt.cl:.4f}"))
            self.detail_table.setItem(row, 2, QTableWidgetItem(f"{pt.cd:.5f}"))
            self.detail_table.setItem(row, 3, QTableWidgetItem(f"{pt.cd_induced:.5f}"))
            self.detail_table.setItem(row, 4, QTableWidgetItem(f"{pt.cd_profile:.5f}"))
            self.detail_table.setItem(row, 5, QTableWidgetItem(f"{pt.cm:+.4f}"))
            self.detail_table.setItem(row, 6, QTableWidgetItem(f"{pt.cl_over_cd:.2f}"))
            self.detail_table.setItem(row, 7, QTableWidgetItem(f"{pt.cx:+.4f}"))
            self.detail_table.setItem(row, 8, QTableWidgetItem(f"{pt.cy:+.4f}"))
            self.detail_table.setItem(row, 9, QTableWidgetItem(f"{pt.cz:+.4f}"))
            self.detail_table.setItem(row, 10, QTableWidgetItem(f"{pt.cl_roll:+.5f}"))
            self.detail_table.setItem(row, 11, QTableWidgetItem(f"{pt.cn:+.5f}"))

        self.detail_table.fit_columns_to_viewport()
        self.btn_export_csv.setEnabled(len(points) > 0)

    def _export_csv(self) -> None:
        if not self._current_result:
            return

        is_summary = (self.tabs.currentIndex() == 0)
        default_name = "aerodynamic_summary.csv" if is_summary else "aerodynamic_polar.csv"
        dialog_title = "Export Aerodynamic Summary to CSV" if is_summary else "Export Aerodynamic Polar Table to CSV"

        path, _ = QFileDialog.getSaveFileName(
            self,
            dialog_title,
            default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                if is_summary:
                    writer.writerow(["Metric", "Value"])
                    for row in range(self.summary_table.rowCount()):
                        k_item = self.summary_table.item(row, 0)
                        v_item = self.summary_table.item(row, 1)
                        if k_item and v_item:
                            writer.writerow([k_item.text(), v_item.text()])
                else:
                    headers = [
                        "AoA_deg",
                        "Beta_deg",
                        "CL",
                        "CD",
                        "CD_ind",
                        "CD_prof",
                        "CD_wave",
                        "Cm",
                        "L_over_D",
                        "CX",
                        "CY",
                        "CZ",
                        "Cl_roll",
                        "Cn_yaw",
                        "Lift_N",
                        "Drag_N",
                        "Sideforce_N",
                        "Fx_b_N",
                        "Fy_b_N",
                        "Fz_b_N",
                        "Mx_b_Nm",
                        "My_b_Nm",
                        "Mz_b_Nm",
                    ]
                    writer.writerow(headers)

                    for pt in self._current_result.polar_points:
                        fm = pt.forces_moments
                        writer.writerow([
                            f"{pt.alpha:.4f}",
                            f"{pt.beta:.4f}",
                            f"{pt.cl:.6f}",
                            f"{pt.cd:.6f}",
                            f"{pt.cd_induced:.6f}",
                            f"{pt.cd_profile:.6f}",
                            f"{pt.cd_wave:.6f}",
                            f"{pt.cm:.6f}",
                            f"{pt.cl_over_cd:.4f}",
                            f"{pt.cx:.6f}",
                            f"{pt.cy:.6f}",
                            f"{pt.cz:.6f}",
                            f"{pt.cl_roll:.6f}",
                            f"{pt.cn:.6f}",
                            f"{pt.lift:.4f}",
                            f"{pt.drag:.4f}",
                            f"{pt.sideforce:.4f}",
                            f"{fm.fx_b:.4f}" if fm else "",
                            f"{fm.fy_b:.4f}" if fm else "",
                            f"{fm.fz_b:.4f}" if fm else "",
                            f"{fm.mx_b:.4f}" if fm else "",
                            f"{fm.my_b:.4f}" if fm else "",
                            f"{fm.mz_b:.4f}" if fm else "",
                        ])

            self._api.show_status(f"Exported {default_name} to {path}", "success")
        except Exception as err:
            self._api.show_status(f"CSV Export failed: {err}", "error")

    def update_theme_style(self) -> None:
        self.tabs.setTabIcon(0, get_icon("fa6s.chart-simple"))
        self.tabs.setTabIcon(1, get_icon("fa6s.table"))
        if hasattr(self, "btn_export_csv"):
            refresh_button_role(self.btn_export_csv)
