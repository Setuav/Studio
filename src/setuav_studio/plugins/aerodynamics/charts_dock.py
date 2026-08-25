"""Unified Aerodynamic Performance Charts Dock hosting all 4 curves simultaneously."""

from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCharts import (
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QCloseEvent, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI

from .engine.base import AeroResult, PolarPoint, SweepType


class SingleChartWidget(QWidget):
    """Sub-chart widget providing themed QtCharts plotting capabilities."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.chart = QChart()
        self.chart.setTitle(title)
        self.chart.setTitleFont(QFont("Inter", 9, QFont.Weight.Bold))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.legend().setVisible(False)
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.setMargins(QChart.margins(self.chart))

        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.view)

        self.update_theme_style()

    def setTitle(self, title: str) -> None:
        self.chart.setTitle(title)

    def update_theme_style(self) -> None:
        from setuav_studio.ui.theme import chart_color, is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        text_col = QColor(tok.get("text", "#1e1e1e" if is_light else "#e0e0e0"))
        dim_col = QColor(tok.get("text_dim", "#666666" if is_light else "#888888"))
        bg_col = QColor(tok.get("surface", "#ffffff" if is_light else "#1e1e1e"))
        plot_bg_col = QColor(tok.get("plot", "#ffffff" if is_light else "#141414"))
        grid_col = QColor(tok.get("grid", "#e0e0e0" if is_light else "#333333"))
        border_col = QColor(tok.get("border", "#dddddd" if is_light else "#282828"))

        self.chart.setTitleBrush(text_col)
        self.chart.setBackgroundBrush(bg_col)
        self.chart.setBackgroundPen(QPen(border_col))
        self.chart.setPlotAreaBackgroundBrush(plot_bg_col)
        self.chart.setDropShadowEnabled(False)
        legend = self.chart.legend()
        if hasattr(legend, "setLabelColor"):
            legend.setLabelColor(text_col)

        for axis in list(self.chart.axes()):
            if isinstance(axis, QValueAxis):
                axis.setTitleBrush(dim_col)
                axis.setLabelsBrush(dim_col)
                axis.setGridLineColor(grid_col)
                axis.setMinorGridLineColor(grid_col)
                axis.setLinePenColor(dim_col)

        for series in self.chart.series():
            role = series.property("themeColorRole")
            if isinstance(role, str) and role:
                pen = series.pen()
                pen.setColor(QColor(chart_color(role)))
                series.setPen(pen)

    def clear(self) -> None:
        self.chart.removeAllSeries()
        self.chart.legend().setVisible(False)
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)

    def series(self) -> list:
        return self.chart.series()

    def axes(self) -> list:
        return self.chart.axes()

    def _create_axis(self, title: str = "") -> QValueAxis:
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        dim_col = QColor(tok.get("text_dim", "#555555" if is_light else "#888888"))
        grid_col = QColor(tok.get("grid", "#e2e4e8" if is_light else "#2d2d35"))

        axis = QValueAxis()
        if title:
            axis.setTitleText(title)
            axis.setTitleBrush(dim_col)
            axis.setTitleFont(QFont("Inter", 8))
        axis.setLabelsBrush(dim_col)
        axis.setLabelsFont(QFont("Inter", 8))
        axis.setGridLineColor(grid_col)
        axis.setMinorGridLineColor(grid_col)
        axis.setLinePenColor(dim_col)
        return axis

    @staticmethod
    def _padded_range(values: Sequence[float]) -> tuple[float, float]:
        """Return a readable range without distorting small coefficient axes.

        A fixed padding (for example 0.5) is excessive for aerodynamic
        coefficients and makes an entirely positive drag curve appear to have
        negative CD values.  Use a relative margin instead and keep a
        positive-only/negative-only range anchored at zero when appropriate.
        """
        lo = float(min(values))
        hi = float(max(values))
        span = hi - lo
        pad = max(span * 0.05, 1e-6)
        if span <= 1e-12:
            pad = max(abs(lo) * 0.05, 1e-3)

        lower = lo - pad
        upper = hi + pad
        if lo >= 0.0:
            lower = max(0.0, lower)
        elif hi <= 0.0:
            upper = min(0.0, upper)
        return lower, upper

    def plot_single(
        self,
        x_vals: Sequence[float],
        y_vals: Sequence[float],
        name: str,
        color_role: str,
        x_title: str = "",
        y_title: str = "",
    ) -> None:
        self.clear()
        if not x_vals or not y_vals:
            return
        self.chart.legend().setVisible(False)

        series = QLineSeries()
        series.setName(name)
        series.setProperty("themeColorRole", color_role)
        from setuav_studio.ui.theme import chart_color

        pen = QPen(QColor(chart_color(color_role)), 2.5)
        series.setPen(pen)

        for x, y in zip(x_vals, y_vals, strict=True):
            series.append(QPointF(x, y))

        self.chart.addSeries(series)

        axis_x = self._create_axis(x_title)
        axis_x.setRange(*self._padded_range(x_vals))

        axis_y = self._create_axis(y_title)
        axis_y.setRange(*self._padded_range(y_vals))

        self.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

    def plot_multi(
        self,
        curves: list[tuple[Sequence[float], Sequence[float], str, str]],
        x_title: str = "",
        y_title: str = "",
    ) -> None:
        self.clear()
        if not curves:
            return

        axis_x = self._create_axis(x_title)
        axis_y = self._create_axis(y_title)

        self.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        all_x: list[float] = []
        all_y: list[float] = []

        from setuav_studio.ui.theme import chart_color

        for x_vals, y_vals, name, color_role in curves:
            if not x_vals or not y_vals:
                continue
            series = QLineSeries()
            series.setName(name)
            series.setProperty("themeColorRole", color_role)

            # Multi-series plots use a restrained dashed style.  The previous
            # mixed styles (especially DotLine) and visible point markers made
            # dense dual/grid sweeps look like a row of dots rather than curves.
            pen = QPen(QColor(chart_color(color_role)), 1.4)
            pen.setStyle(Qt.PenStyle.DashLine)
            series.setPen(pen)
            if hasattr(series, "setPointsVisible"):
                series.setPointsVisible(False)

            for x, y in zip(x_vals, y_vals, strict=True):
                series.append(QPointF(x, y))

            self.chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)
            all_x.extend(x_vals)
            all_y.extend(y_vals)

        if len(curves) > 1:
            self.chart.legend().setVisible(True)
            self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
            self.chart.legend().setFont(QFont("Inter", 8.5))
        else:
            self.chart.legend().setVisible(False)

        if all_x:
            axis_x.setRange(*self._padded_range(all_x))

        if all_y:
            axis_y.setRange(*self._padded_range(all_y))


CHART_SET_DEFINITIONS: list[tuple[str, str]] = [
    ("alpha_beta_grid", "Alpha × Beta Sweep"),
    ("alpha_beta_lateral", "Alpha × Beta — Lateral"),
    ("control_effectiveness", "Control Effectiveness"),
    ("flight_performance", "Flight Performance"),
    ("longitudinal_stability", "Longitudinal Stability"),
    ("lateral_directional", "Lateral-Directional"),
    ("forces_moments", "Forces & Moments"),
]


class AeroChartsDock(QWidget):
    """Unified dock hosting all 4 aerodynamic charts in a 2x2 grid with dynamic chart set selectors."""

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.charts_widget")
        self._api = api
        self._cached_results: dict[str, AeroResult] = {}
        self._cached_points: dict[str, list[PolarPoint]] = {}

        if self._api is not None:
            self._api.subscribe("aerodynamics.result_selected", self.plot_results)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(2)

        # Top Control Toolbar
        toolbar = QWidget(self)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(4, 2, 4, 2)
        tb_layout.setSpacing(6)

        lbl_mode = QLabel("Chart Set:", toolbar)
        lbl_mode.setStyleSheet("font-weight: 600; font-size: 11px;")
        tb_layout.addWidget(lbl_mode)

        self.combo_view_mode = QComboBox(toolbar)
        self.combo_view_mode.setMinimumWidth(180)
        self.combo_view_mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_view_mode.currentIndexChanged.connect(self._on_view_mode_changed)
        tb_layout.addWidget(self.combo_view_mode)
        tb_layout.addStretch(1)
        main_layout.addWidget(toolbar)

        # 4 Sub-charts with descriptive compact headers
        self.chart_lift = SingleChartWidget("Lift Curve (CL vs α)", self)
        self.chart_polar = SingleChartWidget("Drag Polar (CL vs CD)", self)
        self.chart_moment = SingleChartWidget("Pitching Moment (Cm vs α)", self)
        self.chart_ld = SingleChartWidget("Aerodynamic Efficiency (L/D vs α)", self)

        # Main Vertical Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(4)

        # Top Row Horizontal Splitter (Lift | Polar)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.setHandleWidth(4)
        self.top_splitter.addWidget(self.chart_lift)
        self.top_splitter.addWidget(self.chart_polar)

        # Bottom Row Horizontal Splitter (Moment | Efficiency)
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.bottom_splitter.setChildrenCollapsible(False)
        self.bottom_splitter.setHandleWidth(4)
        self.bottom_splitter.addWidget(self.chart_moment)
        self.bottom_splitter.addWidget(self.chart_ld)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)

        self.main_splitter.splitterMoved.connect(self._save_splitter_state)
        self.top_splitter.splitterMoved.connect(self._save_splitter_state)
        self.bottom_splitter.splitterMoved.connect(self._save_splitter_state)

        main_layout.addWidget(self.main_splitter)
        self._restore_splitter_state()

    def _save_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        settings.setValue("aero_charts/main_splitter", self.main_splitter.saveState())
        settings.setValue("aero_charts/top_splitter", self.top_splitter.saveState())
        settings.setValue("aero_charts/bottom_splitter", self.bottom_splitter.saveState())

    def _restore_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        ms = settings.value("aero_charts/main_splitter")
        if ms:
            self.main_splitter.restoreState(ms)
        ts = settings.value("aero_charts/top_splitter")
        if ts:
            self.top_splitter.restoreState(ts)
        bs = settings.value("aero_charts/bottom_splitter")
        if bs:
            self.bottom_splitter.restoreState(bs)

    def _on_view_mode_changed(self, _index: int) -> None:
        active_key = self.combo_view_mode.currentData()
        if active_key:
            self._render_chart_set(active_key)

    def clear_charts(self) -> None:
        self._cached_results.clear()
        self._cached_points.clear()
        self.combo_view_mode.blockSignals(True)
        self.combo_view_mode.clear()
        self.combo_view_mode.blockSignals(False)
        self.chart_lift.clear()
        self.chart_polar.clear()
        self.chart_moment.clear()
        self.chart_ld.clear()

    def plot_results(self, result: AeroResult | None) -> None:
        if result is None:
            self.clear_charts()
            return

        # A chart set belongs to exactly one selected analysis. Do not retain
        # categories from the previously selected result.
        self._cached_results.clear()
        self._cached_points.clear()
        all_points = [p for p in result.polar_points if p.converged]
        if not all_points:
            self.clear_charts()
            return

        cond = result.condition
        sweep_type = cond.sweep_type if cond else SweepType.ALPHA
        preferred_set = "flight_performance"

        if sweep_type == SweepType.MULTI_GRID:
            self._cached_results["alpha_beta_grid"] = result
            self._cached_points["alpha_beta_grid"] = all_points
            self._cached_results["alpha_beta_lateral"] = result
            self._cached_points["alpha_beta_lateral"] = all_points
            preferred_set = "alpha_beta_grid"

        elif sweep_type == SweepType.DUAL_ALPHA_BETA:
            # 1. Alpha group
            alpha_group = [p for p in all_points if p.raw.get("_sweep_group") == "alpha"]
            if not alpha_group and cond:
                alpha_group = all_points[: int(cond.alpha_steps)]
            alpha_pts = sorted(alpha_group if alpha_group else all_points, key=lambda p: p.alpha)

            # 2. Beta group
            beta_group = [p for p in all_points if p.raw.get("_sweep_group") == "beta"]
            if not beta_group and cond:
                beta_group = all_points[int(cond.alpha_steps) :]
            beta_pts = sorted(beta_group if beta_group else all_points, key=lambda p: p.beta)

            if alpha_pts:
                self._cached_results["flight_performance"] = result
                self._cached_points["flight_performance"] = alpha_pts
                self._cached_results["longitudinal_stability"] = result
                self._cached_points["longitudinal_stability"] = alpha_pts
                self._cached_results["forces_moments"] = result
                self._cached_points["forces_moments"] = alpha_pts

            if beta_pts:
                self._cached_results["lateral_directional"] = result
                self._cached_points["lateral_directional"] = beta_pts

            preferred_set = "flight_performance"

        elif sweep_type == SweepType.BETA:
            beta_pts = sorted(all_points, key=lambda p: p.beta)
            self._cached_results["lateral_directional"] = result
            self._cached_points["lateral_directional"] = beta_pts
            self._cached_results["forces_moments"] = result
            self._cached_points["forces_moments"] = beta_pts
            preferred_set = "lateral_directional"

        elif sweep_type == SweepType.CONTROL_DEFLECTION:
            ctrl_k = cond.sweep_variable if cond else ""
            ctrl_pts = sorted(all_points, key=lambda p: p.control_deflections.get(ctrl_k, 0.0))
            self._cached_results["control_effectiveness"] = result
            self._cached_points["control_effectiveness"] = ctrl_pts
            preferred_set = "control_effectiveness"

        else:
            # ALPHA sweep
            alpha_pts = sorted(all_points, key=lambda p: p.alpha)
            self._cached_results["flight_performance"] = result
            self._cached_points["flight_performance"] = alpha_pts
            self._cached_results["longitudinal_stability"] = result
            self._cached_points["longitudinal_stability"] = alpha_pts
            self._cached_results["forces_moments"] = result
            self._cached_points["forces_moments"] = alpha_pts
            preferred_set = "flight_performance"

        self._refresh_combobox_and_render(preferred_set=preferred_set)

    def _refresh_combobox_and_render(self, preferred_set: str | None = None) -> None:
        curr_key = self.combo_view_mode.currentData()
        target_key = (
            preferred_set if (preferred_set and preferred_set in self._cached_results) else curr_key
        )

        self.combo_view_mode.blockSignals(True)
        self.combo_view_mode.clear()

        for key, label in CHART_SET_DEFINITIONS:
            points = self._cached_points.get(key) or []
            if key == "drag_breakdown" and not all(
                point.cd_induced is not None and point.cd_profile is not None for point in points
            ):
                continue
            if key in self._cached_results and points:
                self.combo_view_mode.addItem(label, key)

        if self.combo_view_mode.count() == 0:
            self.combo_view_mode.blockSignals(False)
            self.clear_charts()
            return

        idx = self.combo_view_mode.findData(target_key)
        if idx < 0:
            idx = 0
        self.combo_view_mode.setCurrentIndex(idx)
        self.combo_view_mode.blockSignals(False)

        active_key = self.combo_view_mode.currentData()
        if active_key:
            self._render_chart_set(active_key)

    def _render_chart_set(self, key: str) -> None:
        if key not in self._cached_results or key not in self._cached_points:
            self.clear_charts()
            return

        result = self._cached_results[key]
        points = self._cached_points[key]
        if not points:
            self.clear_charts()
            return

        cond = result.condition
        sweep_type = cond.sweep_type if cond else SweepType.ALPHA

        if sweep_type == SweepType.MULTI_GRID and key in {
            "alpha_beta_grid",
            "alpha_beta_lateral",
        }:
            self._render_alpha_beta_grid(
                result,
                points,
                lateral=(key == "alpha_beta_lateral"),
            )
            return

        # Determine X axis values & label for this specific dataset
        if key == "lateral_directional":
            if any(not math.isclose(p.beta, points[0].beta, abs_tol=1e-2) for p in points):
                x_vals = [p.beta for p in points]
                x_label = "β (°)"
            elif sweep_type == SweepType.CONTROL_DEFLECTION:
                ctrl_k = cond.sweep_variable if cond else "Control"
                x_vals = [p.control_deflections.get(ctrl_k, 0.0) for p in points]
                x_label = f"{ctrl_k.capitalize()} δ (°)"
            else:
                x_vals = [p.beta for p in points]
                x_label = "β (°)"
        else:
            if sweep_type == SweepType.BETA:
                x_vals = [p.beta for p in points]
                x_label = "β (°)"
            elif sweep_type == SweepType.CONTROL_DEFLECTION:
                ctrl_k = cond.sweep_variable if cond else "Control"
                x_vals = [p.control_deflections.get(ctrl_k, 0.0) for p in points]
                x_label = f"{ctrl_k.capitalize()} δ (°)"
            else:
                x_vals = [p.alpha for p in points]
                x_label = "α (°)"

        self.setUpdatesEnabled(False)
        try:
            # Dynamic pressure is constant for the supported fixed-speed,
            # fixed-altitude sweeps, so it carries no information as a curve.
            self.chart_ld.setVisible(key != "forces_moments")

            if key == "control_effectiveness":
                channel = cond.sweep_variable if cond else "control"
                response_sets = {
                    "elevator": (
                        ("Cm", [p.cm for p in points], "orange"),
                        ("CL", [p.cl for p in points], "blue"),
                        ("CD", [p.cd for p in points], "green"),
                        ("L/D", [p.cl_over_cd for p in points], "magenta"),
                    ),
                    "aileron": (
                        ("Cl", [p.cl_roll for p in points], "green"),
                        ("Cn", [p.cn for p in points], "orange"),
                        ("CY", [p.cy for p in points], "blue"),
                        ("CD", [p.cd for p in points], "magenta"),
                    ),
                    "rudder": (
                        ("Cn", [p.cn for p in points], "orange"),
                        ("CY", [p.cy for p in points], "blue"),
                        ("Cl", [p.cl_roll for p in points], "green"),
                        ("CD", [p.cd for p in points], "magenta"),
                    ),
                    "flap": (
                        ("CL", [p.cl for p in points], "blue"),
                        ("CD", [p.cd for p in points], "green"),
                        ("Cm", [p.cm for p in points], "orange"),
                        ("L/D", [p.cl_over_cd for p in points], "magenta"),
                    ),
                }
                responses = response_sets.get(channel, response_sets["elevator"])
                for chart, (coefficient, values, color) in zip(
                    (self.chart_lift, self.chart_polar, self.chart_moment, self.chart_ld),
                    responses,
                    strict=True,
                ):
                    chart.setVisible(True)
                    chart.setTitle(f"{channel.title()} Effectiveness ({coefficient} vs {x_label})")
                    chart.plot_single(
                        x_vals,
                        values,
                        coefficient,
                        color,
                        x_label,
                        coefficient,
                    )

            elif key == "longitudinal_stability":
                self.chart_lift.setTitle(f"Pitching Moment (Cm vs {x_label})")
                self.chart_lift.plot_single(
                    x_vals, [p.cm for p in points], "Cm", "orange", x_label, "Cm"
                )

                self.chart_polar.setTitle("Moment-Lift Polar (Cm vs CL) [Slope = -SM]")
                self.chart_polar.plot_single(
                    [p.cl for p in points], [p.cm for p in points], "Cm-CL", "blue", "CL", "Cm"
                )

                self.chart_moment.setTitle(f"Normal Force Coefficient (CZ vs {x_label})")
                self.chart_moment.plot_single(
                    x_vals, [p.cz for p in points], "CZ", "magenta", x_label, "CZ"
                )

                my_vals = [
                    p.forces_moments.my_b
                    if (p.forces_moments and hasattr(p.forces_moments, "my_b"))
                    else (
                        p.cm * p.dynamic_pressure * result.reference.s_ref * result.reference.c_ref
                    )
                    for p in points
                ]
                self.chart_ld.setTitle(f"Dimensional Pitch Moment (My vs {x_label})")
                self.chart_ld.plot_single(x_vals, my_vals, "My (N·m)", "red", x_label, "My (N·m)")

            elif key == "lateral_directional":
                self.chart_lift.setTitle(f"Sideforce Coefficient (CY vs {x_label})")
                self.chart_lift.plot_single(
                    x_vals, [p.cy for p in points], "CY", "blue", x_label, "CY"
                )

                self.chart_polar.setTitle(f"Roll Moment (Cl vs {x_label})")
                self.chart_polar.plot_single(
                    x_vals, [p.cl_roll for p in points], "Cl", "green", x_label, "Cl (Roll)"
                )

                self.chart_moment.setTitle(f"Yaw Moment (Cn vs {x_label})")
                self.chart_moment.plot_single(
                    x_vals, [p.cn for p in points], "Cn", "orange", x_label, "Cn (Yaw)"
                )

                cy_over_cl = [p.cy / max(abs(p.cl), 1e-4) for p in points]
                self.chart_ld.setTitle(f"Lateral Coupling Ratio (CY / CL vs {x_label})")
                self.chart_ld.plot_single(x_vals, cy_over_cl, "CY/CL", "magenta", x_label, "CY/CL")

            elif key == "drag_breakdown":
                self.chart_lift.setTitle(f"Induced Drag Polar (CD_i vs {x_label})")
                self.chart_lift.plot_single(
                    x_vals, [p.cd_induced for p in points], "CD_i", "blue", x_label, "CD_i"
                )

                self.chart_polar.setTitle(f"Profile Drag Polar (CD_p vs {x_label})")
                self.chart_polar.plot_single(
                    x_vals, [p.cd_profile for p in points], "CD_p", "green", x_label, "CD_p"
                )

                self.chart_moment.setTitle(f"Total Drag Polar (CD vs {x_label})")
                self.chart_moment.plot_single(
                    x_vals, [p.cd for p in points], "CD", "orange", x_label, "CD"
                )

                ratios = [p.cd_induced / max(p.cd, 1e-6) * 100.0 for p in points]
                self.chart_ld.setTitle("Induced Drag Share (% of Total Drag)")
                self.chart_ld.plot_single(
                    x_vals, ratios, "% Induced", "magenta", x_label, "% Induced"
                )

            elif key == "forces_moments":
                self.chart_lift.setTitle(f"Total Lift Force (L vs {x_label})")
                self.chart_lift.plot_single(
                    x_vals,
                    [p.forces_moments.lift if p.forces_moments else 0.0 for p in points],
                    "Lift (N)",
                    "blue",
                    x_label,
                    "Lift (N)",
                )

                self.chart_polar.setTitle(f"Total Drag Force (D vs {x_label})")
                self.chart_polar.plot_single(
                    x_vals,
                    [p.forces_moments.drag if p.forces_moments else 0.0 for p in points],
                    "Drag (N)",
                    "red",
                    x_label,
                    "Drag (N)",
                )

                my_vals = [
                    p.forces_moments.my_b
                    if (p.forces_moments and hasattr(p.forces_moments, "my_b"))
                    else (
                        p.cm * p.dynamic_pressure * result.reference.s_ref * result.reference.c_ref
                    )
                    for p in points
                ]
                self.chart_moment.setTitle(f"Pitching Moment (My vs {x_label})")
                self.chart_moment.plot_single(
                    x_vals, my_vals, "My (N·m)", "orange", x_label, "My (N·m)"
                )

                self.chart_ld.clear()

            else:  # flight_performance
                self.chart_lift.setTitle(f"Lift Curve (CL vs {x_label})")
                self.chart_lift.plot_single(
                    x_vals, [p.cl for p in points], "CL", "blue", x_label, "CL"
                )

                if sweep_type in (SweepType.ALPHA, SweepType.DUAL_ALPHA_BETA):
                    self.chart_polar.setTitle("Drag Polar (CL vs CD)")
                    self.chart_polar.plot_single(
                        [p.cd for p in points], [p.cl for p in points], "Polar", "green", "CD", "CL"
                    )
                else:
                    self.chart_polar.setTitle(f"Drag Curve (CD vs {x_label})")
                    self.chart_polar.plot_single(
                        x_vals, [p.cd for p in points], "CD", "green", x_label, "CD"
                    )

                self.chart_moment.setTitle(f"Aerodynamic Efficiency (L/D vs {x_label})")
                self.chart_moment.plot_single(
                    x_vals, [p.cl_over_cd for p in points], "L/D", "magenta", x_label, "L/D"
                )

                loiter_factor = [(max(p.cl, 0.0) ** 1.5) / max(p.cd, 1e-4) for p in points]
                self.chart_ld.setTitle(f"Endurance Factor (CL^1.5 / CD vs {x_label})")
                self.chart_ld.plot_single(
                    x_vals, loiter_factor, "CL^1.5/CD", "orange", x_label, "CL^1.5 / CD"
                )

        except Exception as err:
            import logging

            logging.getLogger(__name__).error(
                "Failed to update aerodynamic charts: %s", err, exc_info=True
            )
        finally:
            self.setUpdatesEnabled(True)

    def _render_alpha_beta_grid(
        self,
        result: AeroResult,
        points: list[PolarPoint],
        *,
        lateral: bool = False,
    ) -> None:
        """Plot one alpha curve per beta grid row.

        The longitudinal set is useful for lift/drag/pitch trends, while the
        lateral set exposes the coefficients that actually respond to beta.
        Keeping them as separate chart sets avoids compressing six different
        coefficients into four plots.
        """
        sweep = result.sweep_result
        beta_values: list[float] = []
        if sweep is not None:
            beta_variable = next(
                (variable for variable in sweep.variables if variable.name == "beta"),
                None,
            )
            if beta_variable is not None:
                beta_values = list(beta_variable.values)
        if not beta_values:
            beta_values = sorted({float(point.beta) for point in points})

        color_roles = ("blue", "green", "orange", "magenta", "red", "cyan")
        grouped_points: list[tuple[float, list[PolarPoint]]] = []
        for beta in beta_values:
            beta_points = sorted(
                (point for point in points if math.isclose(point.beta, beta, abs_tol=1e-6)),
                key=lambda point: point.alpha,
            )
            if beta_points:
                grouped_points.append((beta, beta_points))

        def curves_for(value_getter) -> list[tuple[list[float], list[float], str, str]]:
            curves = []
            for index, (beta, beta_points) in enumerate(grouped_points):
                curves.append(
                    (
                        [point.alpha for point in beta_points],
                        [float(value_getter(point)) for point in beta_points],
                        f"β={beta:+g}°",
                        color_roles[index % len(color_roles)],
                    )
                )
            return curves

        self.setUpdatesEnabled(False)
        try:
            if lateral:
                self.chart_ld.setVisible(True)
                self.chart_lift.setTitle("Sideforce (CY vs α)")
                self.chart_lift.plot_multi(curves_for(lambda point: point.cy), "α (°)", "CY")
                self.chart_polar.setTitle("Roll Moment (Cl vs α)")
                self.chart_polar.plot_multi(curves_for(lambda point: point.cl_roll), "α (°)", "Cl")
                self.chart_moment.setTitle("Yaw Moment (Cn vs α)")
                self.chart_moment.plot_multi(curves_for(lambda point: point.cn), "α (°)", "Cn")
                self.chart_ld.setTitle("Drag (CD vs α)")
                self.chart_ld.plot_multi(curves_for(lambda point: point.cd), "α (°)", "CD")
            else:
                self.chart_ld.setVisible(True)
                self.chart_lift.setTitle("Lift Curve (CL vs α)")
                self.chart_lift.plot_multi(curves_for(lambda point: point.cl), "α (°)", "CL")
                self.chart_polar.setTitle("Drag Curve (CD vs α)")
                self.chart_polar.plot_multi(curves_for(lambda point: point.cd), "α (°)", "CD")
                self.chart_moment.setTitle("Pitching Moment (Cm vs α)")
                self.chart_moment.plot_multi(curves_for(lambda point: point.cm), "α (°)", "Cm")
                self.chart_ld.setTitle("Aerodynamic Efficiency (L/D vs α)")
                self.chart_ld.plot_multi(curves_for(lambda point: point.cl_over_cd), "α (°)", "L/D")
        finally:
            self.setUpdatesEnabled(True)

    def update_theme_style(self) -> None:
        self.chart_lift.update_theme_style()
        self.chart_polar.update_theme_style()
        self.chart_moment.update_theme_style()
        self.chart_ld.update_theme_style()
        active_key = self.combo_view_mode.currentData()
        if active_key:
            self._render_chart_set(active_key)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._api is not None:
            self._api.unsubscribe("aerodynamics.result_selected", self.plot_results)
        super().closeEvent(event)
