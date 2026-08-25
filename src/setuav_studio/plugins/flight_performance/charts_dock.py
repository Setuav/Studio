"""Flight Performance Envelope Charts Dock hosting 4 performance curves in a 2x2 grid with infeasible region shading."""
from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCharts import (
    QAreaSeries,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)

from setuav_studio.plugin_system import StudioAPI
from .engine.models import FlightEnvelopeResult


class SinglePerformanceChartWidget(QWidget):
    """Sub-chart widget providing themed QtCharts plotting capabilities with dual-axis & infeasible region shading."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._overlay_refs: list[Any] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.chart = QChart()
        self.chart.setTitle(title)
        self.chart.setTitleFont(QFont("Inter", 9, QFont.Weight.Bold))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chart.legend().setFont(QFont("Inter", 8))
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.setMargins(QChart.margins(self.chart))

        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.view)

        self.update_theme_style()

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
        self.chart.legend().setLabelBrush(dim_col)

        for axis in list(self.chart.axes()):
            if isinstance(axis, QValueAxis):
                axis.setTitleBrush(dim_col)
                axis.setLabelsBrush(dim_col)
                if axis.isGridLineVisible():
                    axis.setGridLineColor(grid_col)
                axis.setMinorGridLineColor(grid_col)
                axis.setLinePenColor(dim_col)

        for series in self.chart.series():
            if isinstance(series, QLineSeries):
                role = series.property("themeColorRole")
                if isinstance(role, str) and role:
                    pen = series.pen()
                    pen.setColor(QColor(chart_color(role)))
                    series.setPen(pen)

    def _get_theme_colors(self) -> tuple[QColor, QColor]:
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        dim_col = QColor(tok.get("text_dim", "#555555" if is_light else "#888888"))
        grid_col = QColor(tok.get("grid", "#e2e4e8" if is_light else "#2d2d35"))
        return grid_col, dim_col

    def clear(self) -> None:
        self._overlay_refs.clear()
        self.chart.removeAllSeries()
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)

    def series(self) -> list:
        return self.chart.series()

    def axes(self) -> list:
        return self.chart.axes()

    def _create_axis(
        self,
        title: str,
        dim_col: QColor,
        grid_col: QColor,
        show_grid: bool = True,
    ) -> QValueAxis:
        axis = QValueAxis()
        axis.setTitleText(title)
        axis.setTitleBrush(dim_col)
        axis.setTitleFont(QFont("Inter", 8))
        axis.setLabelsBrush(dim_col)
        axis.setLabelsFont(QFont("Inter", 8))
        axis.setGridLineVisible(show_grid)
        axis.setGridLineColor(grid_col)
        axis.setMinorGridLineColor(grid_col)
        axis.setLinePenColor(dim_col)
        return axis

    def plot_dual_curves(
        self,
        x_vals: Sequence[float],
        y1_vals: Sequence[float],
        y1_label: str,
        y1_unit: str,
        y1_color_role: str,
        y2_vals: Sequence[float] | None = None,
        y2_label: str = "",
        y2_unit: str = "",
        y2_color_role: str = "",
        x_label: str = "Airspeed (m/s)",
        feasible_mask: Sequence[bool] | None = None,
        same_axis: bool = False,
    ) -> None:
        self.clear()
        if not x_vals or not y1_vals:
            return

        from setuav_studio.ui.theme import chart_color
        grid_col, dim_col = self._get_theme_colors()

        x_min, x_max = float(min(x_vals)), float(max(x_vals))
        if x_min == x_max:
            x_max += 1.0

        axis_x = self._create_axis(x_label, dim_col, grid_col, show_grid=True)
        axis_x.setRange(x_min, x_max)
        self.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

        # Primary series (Y1) bounds
        y1_valid = [v for v in y1_vals if v is not None]
        y1_min = float(min(y1_valid)) if y1_valid else 0.0
        y1_max = float(max(y1_valid)) if y1_valid else 1.0

        if same_axis and y2_vals:
            y2_valid = [v for v in y2_vals if v is not None]
            if y2_valid:
                y1_min = min(y1_min, float(min(y2_valid)))
                y1_max = max(y1_max, float(max(y2_valid)))

        if y1_min == y1_max:
            y1_max += 1.0

        title_y1 = f"{y1_label} ({y1_unit})" if y1_unit and not same_axis else (f"Power ({y1_unit})" if same_axis and y1_unit else y1_label)
        axis_y1 = self._create_axis(title_y1, dim_col, grid_col, show_grid=True)
        pad_y1 = max((y1_max - y1_min) * 0.05, 0.05)
        y1_min_bound = max(0.0, y1_min - pad_y1)
        y1_max_bound = y1_max + pad_y1
        axis_y1.setRange(y1_min_bound, y1_max_bound)
        self.chart.addAxis(axis_y1, Qt.AlignmentFlag.AlignLeft)

        # Infeasible Shaded Overlay (Semi-transparent red band)
        if feasible_mask is not None and len(feasible_mask) == len(x_vals):
            infeasible_spans: list[tuple[float, float]] = []
            span_start: float | None = None

            for x, is_feas in zip(x_vals, feasible_mask):
                if not is_feas and span_start is None:
                    span_start = float(x)
                elif is_feas and span_start is not None:
                    infeasible_spans.append((span_start, float(x)))
                    span_start = None
            if span_start is not None:
                infeasible_spans.append((span_start, float(x_vals[-1])))

            for x_start, x_end in infeasible_spans:
                upper = QLineSeries()
                upper.append(float(x_start), float(y1_max_bound))
                upper.append(float(x_end), float(y1_max_bound))

                lower = QLineSeries()
                lower.append(float(x_start), float(y1_min_bound))
                lower.append(float(x_end), float(y1_min_bound))

                area = QAreaSeries(upper, lower)
                area.setName("Infeasible")
                area.setBrush(QBrush(QColor(235, 55, 55, 38)))
                area.setPen(QPen(QColor(235, 55, 55, 90), 1, Qt.PenStyle.DashLine))

                self.chart.addSeries(area)
                area.attachAxis(axis_x)
                area.attachAxis(axis_y1)

                self._overlay_refs.extend([upper, lower, area])

        # Draw Primary Series Curve
        s1 = QLineSeries()
        s1.setName(y1_label)
        s1.setProperty("themeColorRole", y1_color_role)
        pen1 = QPen(QColor(chart_color(y1_color_role)), 2.2)
        s1.setPen(pen1)
        for x, y in zip(x_vals, y1_vals):
            if y is not None:
                s1.append(QPointF(float(x), float(y)))

        self.chart.addSeries(s1)
        s1.attachAxis(axis_x)
        s1.attachAxis(axis_y1)

        # Secondary series (Y2)
        if y2_vals and any(v is not None for v in y2_vals):
            s2 = QLineSeries()
            s2.setName(y2_label)
            s2.setProperty("themeColorRole", y2_color_role)
            pen2 = QPen(QColor(chart_color(y2_color_role)), 2.0)
            s2.setPen(pen2)
            for x, y in zip(x_vals, y2_vals):
                if y is not None:
                    s2.append(QPointF(float(x), float(y)))

            self.chart.addSeries(s2)
            s2.attachAxis(axis_x)

            if same_axis:
                s2.attachAxis(axis_y1)
            else:
                y2_valid = [v for v in y2_vals if v is not None]
                y2_min = float(min(y2_valid)) if y2_valid else 0.0
                y2_max = float(max(y2_valid)) if y2_valid else 1.0
                if y2_min == y2_max:
                    y2_max += 1.0

                title_y2 = f"{y2_label} ({y2_unit})" if y2_unit else y2_label
                axis_y2 = self._create_axis(title_y2, dim_col, grid_col, show_grid=False)
                pad_y2 = max((y2_max - y2_min) * 0.05, 0.05)
                y2_min_bound = max(0.0, y2_min - pad_y2)
                y2_max_bound = y2_max + pad_y2
                axis_y2.setRange(y2_min_bound, y2_max_bound)
                self.chart.addAxis(axis_y2, Qt.AlignmentFlag.AlignRight)
                s2.attachAxis(axis_y2)

        # Hide any area series from legend cleanly
        for marker in self.chart.legend().markers():
            series = marker.series()
            if isinstance(series, QAreaSeries):
                marker.setVisible(False)


class PerformanceChartsDock(QWidget):
    """Right-dock widget hosting all 4 flight performance charts in a 2x2 grid."""

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("flight_performance.charts_widget")
        self._api = api

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)

        # 4 Sub-charts
        self.chart_power = SinglePerformanceChartWidget("Power Required vs Available", self)
        self.chart_climb = SinglePerformanceChartWidget("Climb Performance (ROC & Climb Angle)", self)
        self.chart_mission = SinglePerformanceChartWidget("Mission Range & Endurance", self)
        self.chart_electrical = SinglePerformanceChartWidget("Electrical Power & Throttle", self)

        # Main Vertical Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(4)

        # Top Row Horizontal Splitter (Power | Climb)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.setHandleWidth(4)
        self.top_splitter.addWidget(self.chart_power)
        self.top_splitter.addWidget(self.chart_climb)

        # Bottom Row Horizontal Splitter (Mission | Electrical)
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.bottom_splitter.setChildrenCollapsible(False)
        self.bottom_splitter.setHandleWidth(4)
        self.bottom_splitter.addWidget(self.chart_mission)
        self.bottom_splitter.addWidget(self.chart_electrical)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)

        self.main_splitter.splitterMoved.connect(self._save_splitter_state)
        self.top_splitter.splitterMoved.connect(self._save_splitter_state)
        self.bottom_splitter.splitterMoved.connect(self._save_splitter_state)

        main_layout.addWidget(self.main_splitter)
        self._restore_splitter_state()

        if self._api:
            self._api.subscribe("flight_performance.analysis_completed", self.set_results)

    def _save_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        settings.setValue("flight_charts/main_splitter", self.main_splitter.saveState())
        settings.setValue("flight_charts/top_splitter", self.top_splitter.saveState())
        settings.setValue("flight_charts/bottom_splitter", self.bottom_splitter.saveState())

    def _restore_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        ms = settings.value("flight_charts/main_splitter")
        ts = settings.value("flight_charts/top_splitter")
        bs = settings.value("flight_charts/bottom_splitter")
        if ms:
            self.main_splitter.restoreState(ms)
        if ts:
            self.top_splitter.restoreState(ts)
        if bs:
            self.bottom_splitter.restoreState(bs)

    def update_theme_style(self) -> None:
        self.chart_power.update_theme_style()
        self.chart_climb.update_theme_style()
        self.chart_mission.update_theme_style()
        self.chart_electrical.update_theme_style()

    def set_results(self, result: FlightEnvelopeResult) -> None:
        """Plot all 4 flight performance curves from the analysis result."""
        if not result or not result.curves or not result.curves.velocities:
            return

        c = result.curves
        v_list = c.velocities
        feas_list = c.feasible
        propulsion_available = result.propulsion_available

        # 1. Chart 1 (Top-Left): Power Required vs Available (Both in Watts -> shared axis)
        self.chart_power.plot_dual_curves(
            x_vals=v_list,
            y1_vals=c.power_required,
            y1_label="Power Required (P_req)",
            y1_unit="W",
            y1_color_role="blue",
            y2_vals=c.power_available if propulsion_available else None,
            y2_label="Power Available (P_avail)",
            y2_unit="W",
            y2_color_role="orange",
            x_label="Airspeed (m/s)",
            feasible_mask=feas_list,
            same_axis=True,
        )

        # 2. Chart 2 (Top-Right): Climb Performance (ROC & Climb Angle)
        self.chart_climb.plot_dual_curves(
            x_vals=v_list,
            y1_vals=c.rate_of_climb if propulsion_available else [],
            y1_label="Rate of Climb (ROC)",
            y1_unit="m/s",
            y1_color_role="green",
            y2_vals=c.climb_angle_deg if propulsion_available else None,
            y2_label="Climb Angle (γ)",
            y2_unit="°",
            y2_color_role="teal",
            x_label="Airspeed (m/s)",
            feasible_mask=feas_list,
            same_axis=False,
        )

        # 3. Chart 3 (Bottom-Left): Mission Range & Endurance
        self.chart_mission.plot_dual_curves(
            x_vals=v_list,
            y1_vals=c.range_km if propulsion_available else [],
            y1_label="Range",
            y1_unit="km",
            y1_color_role="blue",
            y2_vals=c.endurance_hours if propulsion_available else None,
            y2_label="Endurance",
            y2_unit="h",
            y2_color_role="magenta",
            x_label="Airspeed (m/s)",
            feasible_mask=feas_list,
            same_axis=False,
        )

        # 4. Chart 4 (Bottom-Right): Electrical Power & Throttle
        self.chart_electrical.plot_dual_curves(
            x_vals=v_list,
            y1_vals=c.electrical_power if propulsion_available else [],
            y1_label="Electrical Power (P_elec)",
            y1_unit="W",
            y1_color_role="red",
            y2_vals=c.throttle_pct if propulsion_available else None,
            y2_label="Throttle",
            y2_unit="%",
            y2_color_role="orange",
            x_label="Airspeed (m/s)",
            feasible_mask=feas_list,
            same_axis=False,
        )
