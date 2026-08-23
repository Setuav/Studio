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
from .engine.base import AeroResult


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

        if self._api is not None:
            self._api.subscribe("aerodynamics.analysis_completed", self.display_results)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)

        # Tab 1: Summary Metrics
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(4, 4, 4, 4)
        summary_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        summary_layout.setSpacing(6)

        self.summary_table = self._property_table([
            ("solver_engine", "Solver / Method"),
            ("cl_max", "Max Lift Coefficient (CL_max)"),
            ("cl_max_alpha", "AoA @ CL_max (α_stall)"),
            ("cd_min", "Min Drag Coefficient (CD_min)"),
            ("ld_max", "Max L/D"),
            ("ld_max_alpha", "AoA @ Max L/D"),
            ("cd_ind_cruise", "Induced Drag (CD_i @ Max L/D)"),
            ("cd_prof_cruise", "Profile Drag (CD_p @ Max L/D)"),
            ("drag_ratio", "Drag Breakdown (Ind / Prof)"),
            ("ref_span", "Ref. Wingspan (b)"),
            ("ref_area", "Ref. Wing Area (S)"),
            ("ref_ar", "Aspect Ratio (AR)"),
            ("ref_mac", "Mean Aero Chord (MAC)"),
            ("mach", "Mach Number (M)"),
            ("dynamic_pressure", "Dynamic Pressure (q_inf)"),
            ("reynolds", "Reynolds Number (Re)"),
            ("oswald_e", "Oswald Efficiency (e)"),
        ])
        summary_layout.addWidget(self.summary_table)
        summary_layout.addStretch(1)

        self.tabs.addTab(summary_tab, get_icon("fa6s.chart-simple"), "Summary")

        # Tab 2: Detailed Polar Table
        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        detail_layout.setSpacing(4)

        self.detail_table = self._create_detail_table()
        detail_layout.addWidget(self.detail_table)

        self.tabs.addTab(detail_tab, get_icon("fa6s.table"), "Polar Table")

        layout.addWidget(self.tabs, 1)

        # Bottom Bar with Export CSV Button (Bottom-Right)
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 2, 4, 2)
        bottom_bar.addStretch(1)

        self.btn_export_csv = QPushButton(" Export CSV", self)
        set_native_button(self.btn_export_csv, "export_csv")
        self.btn_export_csv.setToolTip("Export aerodynamic summary and polar table to CSV")
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_csv.setEnabled(False)
        bottom_bar.addWidget(self.btn_export_csv)

        layout.addLayout(bottom_bar)
        self.clear_results()

    def _create_detail_table(self) -> QTableWidget:
        headers = [
            "AoA α (°)",
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
        self.detail_table.setRowCount(0)
        self.btn_export_csv.setEnabled(False)

    def display_results(self, result: AeroResult) -> None:
        self._current_result = result
        ref = result.reference
        points = result.polar_points

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

        points = result.polar_points
        self.detail_table.setRowCount(len(points))

        for row, pt in enumerate(points):
            self.detail_table.setItem(row, 0, QTableWidgetItem(f"{pt.alpha:+.2f}"))
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
